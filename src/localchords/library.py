"""Where things live on disk: analyzed songs and settings, under the user's profile."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .project import EXTENSION, Project, ProjectError

DEFAULT_SETTINGS = {"engine": "model", "latin": False, "volume": 1.0, "show_bass": True}


def data_dir() -> Path:
    # A test or a portable setup can point it elsewhere.
    override = os.environ.get("LOCALCHORDS_DATA")
    base = (
        Path(override)
        if override
        else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalChords"
    )
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


def save_settings(settings: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=data_dir(), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)
    os.replace(tmp, data_dir() / "settings.json")
