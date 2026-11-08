"""Where things live on disk: analyzed songs and settings, under the user's profile, or next to
the program in portable mode (docs/PORTABLE.md)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .project import EXTENSION, Project, ProjectError

DEFAULT_SETTINGS = {
    "engine": "model",
    "latin": False,
    "volume": 1.0,
    "show_bass": True,
    "diagram_mode": "guitar",  # guitar, piano or both
    "diagram_panel": "full",  # full, reduced or hidden
}
PORTABLE_MARKER = "LocalChords.portable"
LOW_SPACE_MB = 200  # an analysis writes little; a link import writes the whole song


def classic_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalChords"


def portable_dir() -> Path | None:
    """The Data folder next to the program, when LocalChords.portable sits beside it. The program's
    folder is sys.executable's, never sys._MEIPASS: a one-file build unpacks itself into a
    temporary folder that is deleted when it exits."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).resolve().parent
    return folder / "Data" if (folder / PORTABLE_MARKER).exists() else None


def unwritable(folder: Path) -> str | None:
    """Why nothing can be saved in folder (a read-only medium, no rights), or None."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(dir=folder, suffix=".probe")
        os.close(fd)
        os.unlink(probe)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def free_mb(folder: Path) -> int:
    try:
        return shutil.disk_usage(folder).free // 2**20
    except OSError:
        return 0


def use(folder: Path) -> None:
    """Keep this run's data in folder; the analysis process, started later, inherits the choice."""
    os.environ["LOCALCHORDS_DATA"] = str(folder)


def data_dir() -> Path:
    # Set by use(), or by a test.
    override = os.environ.get("LOCALCHORDS_DATA")
    base = Path(override) if override else classic_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def project_path(fingerprint: str) -> Path:
    return data_dir() / "projects" / f"{fingerprint}{EXTENSION}"


def managed(path: Path) -> bool:
    """Whether a file is one LocalChords made (a kept copy, a link's download): the only audio it
    may ever delete. The user's own recordings are never among them."""
    try:
        path = path.resolve()
        return any(path.is_relative_to((data_dir() / d).resolve()) for d in ("audio", "downloads"))
    except (OSError, ValueError):
        return False


def audio_file(info: dict) -> Path:
    """The recording to play for a project's audio dict: the copy kept in the library, else the
    original, else a link's download found in this Data folder (a portable one moves with its
    drive letter). The original's path, when none of them is there."""
    kept = info.get("kept")
    if kept and (data_dir() / kept).is_file():
        return data_dir() / kept
    path = Path(info.get("path") or "")
    if info.get("path") and path.is_file():
        return path
    moved = data_dir() / "downloads" / path.name
    if path.parent.name == "downloads" and path.name and moved.is_file():
        return moved
    return path


class KeepError(Exception):
    """A copy that could not be made; the message is written for the user."""


def keep_copy(source: Path, fingerprint: str) -> str:
    """Copy a recording into the library (audio/, named by its fingerprint: the same recording is
    never kept twice) and return its place relative to the Data folder, which a portable Data
    folder carries along. The original is only read. The copy is checked before it counts."""
    from . import audio

    try:
        if audio.fingerprint(source) != fingerprint:
            raise KeepError(f"« {source.name} » n'est pas l'enregistrement analysé.")
        folder = data_dir() / "audio"
        target = folder / f"{fingerprint}{source.suffix.lower()}"
        if target.is_file() and audio.fingerprint(target) == fingerprint:
            return f"audio/{target.name}"
        folder.mkdir(exist_ok=True)
        need = source.stat().st_size // 2**20 + 50
        if free_mb(folder) < need:
            raise KeepError(f"Pas assez de place : il faut environ {need} Mo sur {folder}.")
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".part")
        os.close(fd)
        try:
            # Contents only: the copy takes the Data folder's rights, the original keeps its own.
            shutil.copyfile(source, tmp)
            if audio.fingerprint(Path(tmp)) != fingerprint:
                raise KeepError("La copie ne correspond pas à l'original : elle n'est pas gardée.")
            os.replace(tmp, target)
        finally:
            Path(tmp).unlink(missing_ok=True)
    except OSError as exc:
        raise KeepError(f"Copie impossible : {exc.strerror or exc}") from exc
    return f"audio/{target.name}"


def find_moved(folder: Path, wanted: list[dict], stop=None, progress=None) -> dict[str, Path]:
    """Recordings found again in folder and below, the user's choice: nothing else is searched.

    wanted: {id, fingerprint, name, size}. A file is a candidate by its name or, when it is known,
    its size; it is taken only if its fingerprint is the analyzed one, so another song's chords
    never land on it. Returns {id: path}."""
    from . import audio

    by_name: dict[str, list[dict]] = {}
    by_size: dict[int, list[dict]] = {}
    for w in wanted:
        by_name.setdefault(w["name"].casefold(), []).append(w)
        if w.get("size"):
            by_size.setdefault(int(w["size"]), []).append(w)
    found: dict[str, Path] = {}
    seen = 0
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in files:
            if stop and stop():
                return found
            seen += 1
            if progress and seen % 200 == 0:
                progress(seen, root)
            path = Path(root) / name
            if path.suffix.lower() not in audio.AUDIO_EXTENSIONS:
                continue
            candidates = by_name.get(name.casefold(), [])
            try:
                candidates = candidates + by_size.get(path.stat().st_size, [])
                candidates = [w for w in candidates if w["id"] not in found]
                if candidates:
                    mark = audio.fingerprint(path)
                    for w in candidates:
                        if w["fingerprint"] == mark:
                            found[w["id"]] = path
            except OSError:
                continue
        if len(found) == len(wanted):
            break
    return found


def recent(limit: int = 30) -> list[tuple[Path, dict]]:
    """Saved songs, last touched first, as (path, audio dict). Unreadable files are skipped."""
    folder = data_dir() / "projects"
    if not folder.exists():
        return []
    files = sorted(folder.glob(f"*{EXTENSION}"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for path in files[:limit]:
        try:
            out.append((path, Project.load(path).audio))
        except ProjectError:
            continue
    return out


def load_settings() -> dict:
    try:
        with (data_dir() / "settings.json").open(encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> bool:
    """Write atomically. A full disk loses only this change of preferences, not the old file."""
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=data_dir(), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        os.replace(tmp, data_dir() / "settings.json")
    except OSError:
        if tmp:
            Path(tmp).unlink(missing_ok=True)
        return False
    return True
