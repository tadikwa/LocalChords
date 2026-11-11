"""A newer LocalChords on GitHub: looked for only when the user allows it, fetched only when asked,
installed or launched only once confirmed. No Qt here: the window runs these in a thread.

What leaves the computer: one anonymous request for the latest release (no token, no identifier,
nothing about the songs), asked at most once a day with its ETag, then the file chosen. A file is
kept only once its size and SHA-256 match both the digest GitHub states for the asset and the
release's SHA256SUMS.txt. That proves the file is the one published on the project's page, not who
published it: the program is not signed, and Windows SmartScreen still has its say. See
docs/MISES-A-JOUR.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__, library

REPO = "tadikwa/LocalChords"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases"
APP_ID = "{C21679FE-1659-4CB0-872C-E0A24C7766C0}"  # installer/LocalChords.iss; never changes
UNINSTALL = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
USER_AGENT = f"LocalChords/{__version__} (https://github.com/{REPO})"
SUMS = "SHA256SUMS.txt"
TIMEOUT = 15
DAY = 24 * 3600
MAX_ANSWER = 1 << 20  # a release's JSON is a few kilobytes
MAX_SUMS = 1 << 16
SPACE_MARGIN_MB = 50
TEMP_FOLDER = "LocalChords-mises-a-jour"
ASSETS = {  # what each way of running LocalChords is updated with, as the CI names it
    "installed": "LocalChords-Setup-{tag}.exe",
    "portable": "LocalChords-{tag}-portable.exe",
    "zip": "LocalChords-{tag}-windows-x64.zip",
}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_HEX = re.compile(r"[0-9a-f]{64}")


class UpdateError(Exception):
    pass


# Versions ------------------------------------------------------------------------------------


def parse_version(text) -> tuple[int, ...] | None:
    """(1, 5, 1) for "v1.5.1"; None for anything else, a pre-release name included."""
    m = re.fullmatch(r"v?(\d{1,4}(?:\.\d{1,4}){0,3})", str(text).strip())
    if not m:
        return None
    parts = tuple(int(x) for x in m.group(1).split("."))
    return parts + (0,) * (4 - len(parts))


def newer(tag: str, current: str = __version__) -> bool:
    a, b = parse_version(tag), parse_version(current)
    return a is not None and b is not None and a > b


# The latest release ----------------------------------------------------------------------------


def release_of(data) -> dict | None:
    """What is used of the API's answer, or None unless it is a published, stable release of this
    project. Asset links must be GitHub's own for this tag: no link is ever made up or followed
    elsewhere."""
    if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease"):
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str) or parse_version(tag) is None or not _NAME.fullmatch(tag):
        return None
    if data.get("html_url") != f"{RELEASES}/tag/{tag}":
        return None
    assets = {}
    for a in data.get("assets") or []:
        if not isinstance(a, dict):
            continue
        name, size, digest = a.get("name"), a.get("size"), a.get("digest")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            continue
        if a.get("browser_download_url") != f"{RELEASES}/download/{tag}/{name}":
            continue
        if not isinstance(size, int) or size <= 0 or a.get("state", "uploaded") != "uploaded":
            continue
        sha = None
        if isinstance(digest, str) and digest.startswith("sha256:"):
            sha = digest[7:].lower() if _HEX.fullmatch(digest[7:].lower()) else None
        assets[name] = {"name": name, "url": a["browser_download_url"], "size": size, "sha256": sha}
    body = data.get("body")
    name = data.get("name")
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "name": name if isinstance(name, str) and name else f"LocalChords {tag}",
        "url": data["html_url"],
        "published": str(data.get("published_at") or "")[:10],
        "body": body[:20000] if isinstance(body, str) else "",
        "assets": assets,
    }


def check(cache, *, force: bool = False, current: str = __version__, opener=None, now=None):
    """(the release when it is newer than this one, else None; the cache to keep).

    The answer is kept a day; `force` (the user asked) asks again, still with the ETag, which
    GitHub does not count against the hourly allowance when nothing changed. Raises UpdateError
    when GitHub cannot be reached or refuses."""
    opener = opener or urllib.request.urlopen
    now = time.time() if now is None else now
    cache = cache if isinstance(cache, dict) else {}
    fresh = "release" in cache and 0 <= now - float(cache.get("checked") or 0) < DAY
    if not (fresh and not force):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if cache.get("etag") and "release" in cache:
            headers["If-None-Match"] = str(cache["etag"])
        try:
            with opener(urllib.request.Request(API, headers=headers), timeout=TIMEOUT) as r:
                raw = r.read(MAX_ANSWER + 1)
                etag = r.headers.get("ETag")
            if len(raw) > MAX_ANSWER:
                raise UpdateError("Réponse de GitHub inattendue.")
            cache = {"checked": now, "etag": etag, "release": release_of(json.loads(raw))}
        except urllib.error.HTTPError as exc:
            if exc.code == 304 and "release" in cache:
                cache = {**cache, "checked": now}
            elif exc.code == 404:  # no release published yet
                cache = {"checked": now, "etag": None, "release": None}
            elif exc.code in (403, 429):
                raise UpdateError(
                    "GitHub limite pour l'instant les vérifications depuis cette connexion. "
                    "Réessayez dans une heure."
                ) from exc
            else:
                raise UpdateError(f"GitHub ne répond pas correctement ({exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError("GitHub est injoignable : pas de connexion à Internet ?") from exc
        except ValueError as exc:
            raise UpdateError("Réponse de GitHub illisible.") from exc
    release = cache.get("release")
    found = release if isinstance(release, dict) and newer(release["tag"], current) else None
    return found, cache


# How this copy of LocalChords runs -----------------------------------------------------------


def installed_location() -> Path | None:
    """Where the installer put LocalChords for this user or all users, from its uninstall entry."""
    try:
        import winreg
    except ImportError:
        return None
    for root, view in (
        (winreg.HKEY_CURRENT_USER, 0),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
    ):
        with (
            contextlib.suppress(OSError),
            winreg.OpenKey(root, UNINSTALL, 0, winreg.KEY_READ | view) as key,
        ):
            value, _kind = winreg.QueryValueEx(key, "InstallLocation")
            if value:
                return Path(value)
    return None


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(a.resolve()) == os.path.normcase(b.resolve())
    except OSError:
        return False


def distribution(exe: Path | None = None, frozen: bool | None = None, location="registry") -> str:
    """Installed only when the installer's entry for this AppId points at this program's folder
    (a copy elsewhere, even under %LOCALAPPDATA%, is not that one); "zip" for the folder build
    (its files beside it in _internal); "portable" for the one-file program; "source" when run
    from the code."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return "source"
    folder = Path(exe or sys.executable).parent
    where = installed_location() if location == "registry" else location
    if where is not None and _same(Path(where), folder):
        return "installed"
    return "zip" if (folder / "_internal").is_dir() else "portable"


def asset_for(release: dict, kind: str) -> dict | None:
    pattern = ASSETS.get(kind)
    return release["assets"].get(pattern.format(tag=release["tag"])) if pattern else None


def destination(kind: str, exe: Path | None = None) -> tuple[Path, str | None]:
    """(the folder for the download, why it cannot be used or None).

    The installer goes to a temporary folder of its own. The portable program goes next to this
    one, so that it finds the same Data folder; the ZIP to Downloads."""
    if kind == "installed":
        return Path(tempfile.gettempdir()) / TEMP_FOLDER, None
    folder = Path(exe or sys.executable).parent if kind == "portable" else Path.home() / "Downloads"
    return folder, library.unwritable(folder)


# Fetching ------------------------------------------------------------------------------------


def _get(url: str, limit: int, opener) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=TIMEOUT) as r:
            if not str(r.geturl()).startswith("https://"):
                raise UpdateError("Téléchargement refusé : la connexion n'est pas chiffrée.")
            raw = r.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub refuse le téléchargement ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("GitHub est injoignable : pas de connexion à Internet ?") from exc
    if len(raw) > limit:
        raise UpdateError("Fichier de sommes de contrôle inattendu.")
    return raw


def parse_sums(text: str) -> dict[str, str]:
    """name: sha256 from the "hash  name" (or "hash *name") lines of sha256sum."""
    out = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](\S.*?)\s*", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def expected_sha256(release: dict, asset: dict, opener=None) -> str:
    """The SHA-256 the file must have: listed in SHA256SUMS.txt, and equal to GitHub's digest
    for the asset. A missing one, or any disagreement, refuses the download."""
    opener = opener or urllib.request.urlopen
    sums = release["assets"].get(SUMS)
    if sums is None:
        raise UpdateError(
            "Cette version n'a pas de fichier SHA256SUMS.txt : impossible de vérifier le "
            "téléchargement, il est refusé."
        )
    raw = _get(sums["url"], MAX_SUMS, opener)
    if sums["sha256"] and hashlib.sha256(raw).hexdigest() != sums["sha256"]:
        raise UpdateError(
            "SHA256SUMS.txt ne correspond pas à celui publié : téléchargement refusé."
        )
    listed = parse_sums(raw.decode("utf-8", "replace")).get(asset["name"])
    if listed is None:
        raise UpdateError(f"{asset['name']} n'est pas dans SHA256SUMS.txt : téléchargement refusé.")
    if not asset["sha256"]:
        raise UpdateError(
            "GitHub ne donne pas l'empreinte de ce fichier : impossible de la comparer à "
            "SHA256SUMS.txt, téléchargement refusé."
        )
    if asset["sha256"] != listed:
        raise UpdateError(
            "Les sommes de contrôle publiées ne concordent pas : téléchargement refusé."
        )
    return listed


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def verified(path: Path, sha256: str, size: int | None = None) -> bool:
    """Whether the file on disk is still exactly the one checked: asked again before any launch."""
    try:
        if size is not None and path.stat().st_size != size:
            return False
        return file_sha256(path) == sha256
    except OSError:
        return False


def _mark_from_internet(path: Path, url: str) -> None:
    """The mark Windows puts on what a browser downloads, so SmartScreen checks it as usual."""
    # FAT32 sticks have no room for it: nothing to mark
    with contextlib.suppress(OSError), open(f"{path}:Zone.Identifier", "w", encoding="ascii") as f:
        f.write(f"[ZoneTransfer]\r\nZoneId=3\r\nReferrerUrl={RELEASES}\r\nHostUrl={url}\r\n")


def download(release: dict, kind: str, folder: Path, task, opener=None) -> dict:
    """Fetch the file for this kind into folder: written as .part, kept under its own name only
    once complete and verified, removed otherwise. Returns what the window keeps of it."""
    opener = opener or urllib.request.urlopen
    asset = asset_for(release, kind)
    if asset is None:
        raise UpdateError(
            f"La version {release['tag']} ne propose pas de fichier pour cette installation."
        )
    if asset["url"] != f"{RELEASES}/download/{release['tag']}/{asset['name']}":
        raise UpdateError("Adresse de téléchargement inattendue : refusé.")  # a cache edited
    task.status = "Vérification des sommes de contrôle…"
    sha = expected_sha256(release, asset, opener)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / asset["name"]
    ready = {"tag": release["tag"], "kind": kind, "path": str(target), "sha256": sha}
    ready["size"] = asset["size"]
    if target.exists() and verified(target, sha, asset["size"]):
        return ready  # already fetched, and intact
    free = library.free_mb(folder)
    need = asset["size"] // 2**20 + SPACE_MARGIN_MB
    if free and free < need:
        raise UpdateError(f"Pas assez de place dans {folder} : {free} Mo libres, {need} Mo requis.")
    part = folder / (asset["name"] + ".part")
    digest, got = hashlib.sha256(), 0
    request = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=TIMEOUT) as r, part.open("wb") as f:
            if not str(r.geturl()).startswith("https://"):
                raise UpdateError("Téléchargement refusé : la connexion n'est pas chiffrée.")
            while chunk := r.read(1 << 20):
                if task.cancelled:
                    raise UpdateError("Téléchargement annulé.")
                got += len(chunk)
                if got > asset["size"]:
                    raise UpdateError("Le fichier reçu est plus gros que celui publié : refusé.")
                f.write(chunk)
                digest.update(chunk)
                task.progress = got / asset["size"]
                task.status = f"{got / 2**20:.0f} / {asset['size'] / 2**20:.0f} Mo"
        if got != asset["size"]:
            raise UpdateError("Téléchargement interrompu avant la fin : réessayez.")
        if digest.hexdigest() != sha:
            raise UpdateError(
                "Le fichier reçu ne correspond pas à celui publié (SHA-256) : il a été supprimé."
            )
        os.replace(part, target)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"GitHub refuse le téléchargement ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Le téléchargement a échoué : {exc}") from exc
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    _mark_from_internet(target, asset["url"])
    return ready


def ready_ok(ready: dict) -> bool:
    """A file kept in the settings as fetched: still named as one of ours, and still there."""
    try:
        path = Path(ready["path"])
        name = ASSETS[ready["kind"]].format(tag=ready["tag"])
        return (
            parse_version(ready["tag"]) is not None
            and re.fullmatch(r"[0-9a-f]{64}", ready["sha256"]) is not None
            and path.name == name
            and path.is_file()
        )
    except (KeyError, TypeError, OSError):
        return False


def clean_parts(folder: Path) -> None:
    """Parts of our own files that a download stopped short left in folder."""
    with contextlib.suppress(OSError):
        for path in folder.glob("LocalChords-*.part"):
            tag = re.search(r"v\d+(?:\.\d+)*", path.name)
            names = {f"{n.format(tag=tag.group())}.part" for n in ASSETS.values()} if tag else ()
            if path.name in names:
                with contextlib.suppress(OSError):
                    path.unlink()


def clean_temp(current: str = __version__, keep: str | None = None) -> None:
    """Remove from our own temporary folder the installers already applied and the parts left
    by an interrupted download. Nothing else, anywhere else, is ever deleted."""
    folder = Path(tempfile.gettempdir()) / TEMP_FOLDER
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        if keep and path.name == keep:
            continue
        m = re.fullmatch(r"LocalChords-Setup-(v[\d.]+)\.exe(\.part)?", path.name)
        if m and (m.group(2) or not newer(m.group(1), current)):
            with contextlib.suppress(OSError):
                path.unlink()
