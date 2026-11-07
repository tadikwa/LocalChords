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

DEFAULT_SETTINGS = {"engine": "model", "latin": False, "volume": 1.0, "show_bass": True}
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
