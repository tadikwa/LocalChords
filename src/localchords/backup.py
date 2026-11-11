"""Library backups (v1.4): one zip file the user keeps for themselves, to find the library again
after a reinstall or on another PC. It holds the projects whole (corrections, chord positions,
lyrics), what the catalog adds (favourites, genres, tags, collections, dates), the preferences, and
the audio if asked. It is a private copy, not a way to share songs: lyrics from an online catalog
can be left out, and stay unexportable once restored. docs/TECHNIQUE.md#la-bibliothèque-v14.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from . import __version__, audio, library
from .catalog import Catalog, CatalogError, audio_state
from .i18n import translate
from .project import EXTENSION, Project, ProjectError

FORMAT = "localchords-backup"
VERSION = 1
MANIFEST = "manifest.json"
CATALOG = "catalog.json"
SETTINGS = "settings.json"
SAFE = re.compile(r"[\w-]{1,80}")  # a project's or recording's name: nothing that leaves its folder


class BackupError(Exception):
    """A backup that could not be written or read; the message is written for the user."""


def _projects() -> list[Path]:
    folder = library.data_dir() / "projects"
    return sorted(folder.glob(f"*{EXTENSION}")) if folder.is_dir() else []


def _audio(catalog: Catalog) -> dict[str, Path]:
    """Each song's recording that can be read now, by song."""
    out = {}
    roots: dict = {}
    for song in catalog.songs():
        if not (song["audio_path"] or song["kept"]):
            continue
        try:
            if audio_state(song["audio_path"], song["kept"], roots) in ("ok", "kept"):
                out[song["id"]] = library.audio_file(
                    {"path": song["audio_path"], "kept": song["kept"]}
                )
        except OSError:
            continue
    return out


def estimate(catalog: Catalog, with_audio: bool) -> dict:
    """Sizes before writing anything: {projects, project_bytes, audio, audio_bytes, songs}."""
    projects = _projects()
    found = _audio(catalog) if with_audio else {}
    ids = {p.stem for p in projects}
    sizes = [p.stat().st_size for p in projects]
    audio_sizes = [p.stat().st_size for sid, p in found.items() if sid in ids]
    return {
        "projects": len(projects),
        "project_bytes": sum(sizes),
        "audio": len(audio_sizes),
        "audio_bytes": sum(audio_sizes),
        "without_audio": len(ids) - len(audio_sizes) if with_audio else 0,
    }


def write(
    target: Path,
    catalog: Catalog,
    *,
    with_audio: bool,
    catalog_lyrics: bool = True,
    progress=None,
    stop=None,
) -> dict:
    """Write the backup to target, whole or not at all: it is built beside it under another name
    and takes its name only once complete. Returns the manifest."""
    projects = _projects()
    found = _audio(catalog) if with_audio else {}
    need = estimate(catalog, with_audio)
    room = library.free_mb(target.parent) * 2**20
    if room < need["project_bytes"] + need["audio_bytes"] + 20 * 2**20:
        raise BackupError(
            translate(
                "Backup", "Pas assez de place sur {parent} : il faut environ {size} Mo."
            ).format(
                parent=target.parent,
                size=(need["project_bytes"] + need["audio_bytes"]) // 2**20 + 20,
            )
        )
    ids = [p.stem for p in projects]
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "created_at": time.time(),
        "program": f"LocalChords {__version__}",
        "private": True,
        "projects": len(projects),
        "audio": 0,
        "catalog_lyrics": catalog_lyrics,
    }
    try:
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".localchords-", suffix=".part")
        os.close(fd)
    except OSError as exc:
        raise BackupError(
            translate("Backup", "Impossible d'écrire dans {parent} : {reason}").format(
                parent=target.parent, reason=exc.strerror or exc
            )
        ) from exc
    total = len(projects) + len(found)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for i, path in enumerate(projects):
                if stop and stop():
                    raise BackupError(translate("Backup", "Sauvegarde annulée."))
                name = f"projects/{path.name}"
                if catalog_lyrics:
                    z.write(path, name)
                else:
                    try:
                        data = Project.load(path).to_dict(shared=True)
                    except ProjectError:
                        # Unreadable here: its lyrics cannot be checked, so it stays out.
                        manifest["left_out"] = [*manifest.get("left_out", []), path.name]
                        manifest["projects"] -= 1
                        continue
                    info = zipfile.ZipInfo.from_file(path, name)  # the project's own date
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, json.dumps(data, ensure_ascii=False, indent=1))
                if progress:
                    progress(i + 1, total, path.stem)
            for i, (sid, path) in enumerate(found.items()):
                if stop and stop():
                    raise BackupError(translate("Backup", "Sauvegarde annulée."))
                if sid not in ids:
                    continue
                # Compressed audio does not shrink: stored as it is, faster.
                z.write(path, f"audio/{sid}{path.suffix.lower()}", zipfile.ZIP_STORED)
                manifest["audio"] += 1
                if progress:
                    progress(len(projects) + i + 1, total, path.name)
            z.writestr(CATALOG, json.dumps(catalog.personal(ids), ensure_ascii=False, indent=1))
            z.writestr(SETTINGS, json.dumps(library.load_settings(), ensure_ascii=False, indent=1))
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
        with zipfile.ZipFile(tmp) as z:  # readable before it counts
            json.loads(z.read(MANIFEST))
        os.replace(tmp, target)
    except BackupError:
        Path(tmp).unlink(missing_ok=True)
        raise
    except (OSError, zipfile.BadZipFile, ValueError, sqlite3.Error, CatalogError) as exc:
        Path(tmp).unlink(missing_ok=True)
        raise BackupError(
            translate("Backup", "La sauvegarde a échoué : {reason}").format(
                reason=getattr(exc, "strerror", None) or exc
            )
        ) from exc
    return manifest


def _open(archive: Path) -> tuple[zipfile.ZipFile, dict]:
    try:
        z = zipfile.ZipFile(archive)
        manifest = json.loads(z.read(MANIFEST))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise BackupError(
            translate("Backup", "« {name} » n'est pas une sauvegarde LocalChords lisible.").format(
                name=archive.name
            )
        ) from exc
    if manifest.get("format") != FORMAT:
        z.close()
        raise BackupError(
            translate("Backup", "« {name} » n'est pas une sauvegarde LocalChords.").format(
                name=archive.name
            )
        )
    if int(manifest.get("version", 0)) > VERSION:
        z.close()
        raise BackupError(
            translate(
                "Backup", "« {name} » vient d'une version plus récente de LocalChords."
            ).format(name=archive.name)
        )
    return z, manifest


def _project_names(z: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    out = {}
    for info in z.infolist():
        name = info.filename
        # Only plain names under projects/: nothing in a backup may write elsewhere.
        if name.startswith("projects/") and name.endswith(EXTENSION) and name.count("/") == 1:
            stem = name[len("projects/") : -len(EXTENSION)]
            if SAFE.fullmatch(stem):
                out[stem] = info
    return out


def inspect(archive: Path) -> dict:
    """What restoring would do, before anything is written: {manifest, new, same, differ, newer}
    where differ lists the songs here that the backup has otherwise, and newer those of them
    whose backup copy is the more recent."""
    z, manifest = _open(archive)
    with z:
        folder = library.data_dir() / "projects"
        new, same, differ, newer = [], [], [], []
        for stem, info in _project_names(z).items():
            here = folder / f"{stem}{EXTENSION}"
            if not here.exists():
                new.append(stem)
                continue
            if _same(here.read_bytes(), z.read(info)):
                same.append(stem)
                continue
            differ.append(stem)
            if time.mktime((*info.date_time, 0, 0, -1)) > here.stat().st_mtime + 2:
                newer.append(stem)
    return {"manifest": manifest, "new": new, "same": same, "differ": differ, "newer": newer}


def restore(
    archive: Path,
    catalog: Catalog,
    *,
    take_newer: bool = False,
    settings: bool = False,
    progress=None,
) -> dict:
    """Bring a backup in without losing anything here.

    A song new here is written; one identical is skipped; one that differs keeps this PC's version
    unless take_newer and the backup's is more recent; either way the version not kept goes to
    restored/<date>/, not away. Audio comes in as copies kept in the library, each checked against
    the analyzed recording. The catalog's personal data merges in (Catalog.merge_personal).
    Returns {written, same, set_aside, audio, aside_folder}."""
    plan = inspect(archive)
    z, manifest = _open(archive)
    data = library.data_dir()
    folder = data / "projects"
    aside = data / "restored" / time.strftime("%Y-%m-%d_%H%M%S")
    report = {
        "written": 0,
        "same": len(plan["same"]),
        "set_aside": 0,
        "audio": 0,
        "aside_folder": None,
    }
    with z:
        names = _project_names(z)
        audio_files = {
            Path(i.filename).stem: i
            for i in z.infolist()
            if i.filename.startswith("audio/") and i.filename.count("/") == 1
            and Path(i.filename).suffix.lower() in audio.AUDIO_EXTENSIONS
        }  # fmt: skip
        try:
            folder.mkdir(parents=True, exist_ok=True)
            todo = plan["new"] + plan["differ"]
            for n, stem in enumerate(todo):
                raw = z.read(names[stem])
                try:
                    project_dict = json.loads(raw)
                except ValueError:
                    continue
                if project_dict.get("format") != "localchords" or not isinstance(
                    project_dict.get("audio"), dict
                ):
                    continue
                here = folder / f"{stem}{EXTENSION}"
                if stem in plan["differ"]:
                    aside.mkdir(parents=True, exist_ok=True)
                    report["aside_folder"] = str(aside)
                    report["set_aside"] += 1
                    if not (take_newer and stem in plan["newer"]):
                        (
                            aside
                            / translate("Backup", "{stem} (sauvegarde){extension}").format(
                                stem=stem, extension=EXTENSION
                            )
                        ).write_bytes(raw)
                        continue
                    (
                        aside
                        / translate("Backup", "{stem} (ce PC){extension}").format(
                            stem=stem, extension=EXTENSION
                        )
                    ).write_bytes(here.read_bytes())
                kept = _bring_audio(z, audio_files.get(stem), project_dict, data)
                if kept:
                    project_dict["audio"]["kept"] = kept
                    raw = json.dumps(project_dict, ensure_ascii=False, indent=1).encode("utf-8")
                    report["audio"] += 1
                _atomic(here, raw)
                report["written"] += 1
                if progress:
                    progress(n + 1, len(todo), stem)
            # Audio for songs already here whose recording is nowhere on this PC.
            for stem in plan["same"]:
                here = folder / f"{stem}{EXTENSION}"
                try:
                    project = Project.load(here)
                except ProjectError:
                    continue
                if stem in audio_files and not library.audio_file(project.audio).is_file():
                    kept = _bring_audio(z, audio_files[stem], project.to_dict(), data)
                    if kept:
                        project.audio["kept"] = kept
                        project.save(here)
                        report["audio"] += 1
            indexed = catalog.ids()
            for stem in [*plan["new"], *plan["differ"], *plan["same"]]:
                path = folder / f"{stem}{EXTENSION}"
                if path.exists() and stem not in indexed:
                    try:
                        catalog.store(path, Project.load(path), estimated=True)
                    except ProjectError:
                        catalog.store(path, None, estimated=True)
            if CATALOG in z.namelist():
                catalog.merge_personal(json.loads(z.read(CATALOG)))
            if settings and SETTINGS in z.namelist():
                current = library.load_settings()
                restored = {**current, **json.loads(z.read(SETTINGS))}
                # The interface's language is this PC's user's choice, not the backup's.
                restored.pop("language", None)
                if "language" in current:
                    restored["language"] = current["language"]
                library.save_settings(restored)
        except (OSError, ValueError, zipfile.BadZipFile, KeyError, TypeError,
                AttributeError) as exc:  # fmt: skip
            raise BackupError(
                translate(
                    "Backup",
                    "La restauration s'est arrêtée : {reason}. Ce qui était déjà restauré "
                    "l'est entièrement ; relancer la restauration reprend le reste.",
                ).format(reason=getattr(exc, "strerror", None) or exc)
            ) from exc
    return report


def _bring_audio(z: zipfile.ZipFile, info, project_dict: dict, data: Path) -> str | None:
    """A backup's recording into audio/, if it is the analyzed one; its place there, or None."""
    if info is None:
        return None
    wanted = str((project_dict.get("audio") or {}).get("fingerprint") or Path(info.filename).stem)
    if not SAFE.fullmatch(wanted):
        return None
    folder = data / "audio"
    folder.mkdir(exist_ok=True)
    target = folder / f"{wanted}{Path(info.filename).suffix.lower()}"
    if target.is_file() and audio.fingerprint(target) == wanted:
        return f"audio/{target.name}"
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, z.open(info) as src:
            while chunk := src.read(1 << 20):
                out.write(chunk)
        if audio.fingerprint(Path(tmp)) != wanted:
            return None
        os.replace(tmp, target)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return f"audio/{target.name}"


def _same(mine: bytes, theirs: bytes) -> bool:
    """The same work, wherever each PC keeps its copy of the recording (audio.kept)."""
    if mine == theirs:
        return True
    try:
        a, b = json.loads(mine), json.loads(theirs)
        for d in (a, b):
            (d.get("audio") or {}).pop("kept", None)
        return a == b
    except (ValueError, AttributeError):
        return False


def _atomic(path: Path, raw: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
