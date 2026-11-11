"""Separated stems: the model and its download, the cache on disk, and the mixer's settings.

The separation itself runs in its own process (worker.start_separation, separation.py), once per
song and mode; the stems are kept as FLAC under <data>/stems and mixed live by player.Mix. Nothing
is sent anywhere. docs/SEPARATION.md gives the measurements behind the choices made here.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
from pathlib import Path

import numpy as np

from . import library

# The networks are converted from Meta's published weights (MIT) by scripts/export_demucs_onnx.py,
# and hosted with the v1.6 release: pinned by size and SHA-256 like the whisper models.
RELEASE = "https://github.com/tadikwa/LocalChords/releases/download/v1.6/"
MODEL = {
    "id": "htdemucs",
    "label": "Demucs v4 « htdemucs » (Meta, licence MIT)",
    "file": "htdemucs.onnx",
    "size": 174_264_717,
    "sha256": "98e91e185f202396e989753f1f5843136f436368eb710177bbf8c418abf82100",
    "sources": ["drums", "bass", "other", "vocals"],
    "samplerate": 44100,
    "segment": 343_980,
    "weights": [[1.0, 1.0, 1.0, 1.0]],
}
MODES = {
    "karaoke": {
        "label": "Karaoké : voix et instrumental (2 pistes)",
        "stems": ["vocals", "instrumental"],
    },
    "musician": {
        "label": "Musicien : voix, batterie, basse, autres (4 pistes)",
        "stems": ["vocals", "drums", "bass", "other"],
    },
}
DEFAULT_MODE = "musician"
NAMES = {
    "vocals": "Voix",
    "drums": "Batterie",
    "bass": "Basse",
    "other": "Autres",
    "instrumental": "Instrumental",
}
FORMAT_VERSION = 1
# 16-bit FLAC of a separated stem, measured on songs: about this many bytes per second each.
FLAC_BYTES_PER_SECOND = 110_000
WORK_MB_PER_MINUTE = 250  # memory the separation needs beyond the model, per minute of song
SPACE_MARGIN_MB = 300

# Levels -------------------------------------------------------------------------------------
# A level is a slider position 0..100: 0 is silence, UNITY is the stem as separated, and the
# gain follows the square of the position (a fader's law): -12 dB at half of UNITY, +5 dB at 100.
UNITY = 75
TOP = 100


def gain(level: int) -> float:
    return (max(0, min(TOP, level)) / UNITY) ** 2


def db_text(level: int) -> str:
    if level <= 0:
        return "−∞"
    db = 40 * math.log10(level / UNITY)
    return "0 dB" if abs(db) < 0.5 else f"{db:+.0f} dB".replace("-", "−")


def new_settings(mode: str) -> dict:
    """The mixer as it opens on a song just separated: every stem as it is, playing the stems."""
    return {
        "mode": mode,
        "on": True,
        "levels": {name: UNITY for name in MODES[mode]["stems"]},
        "mute": [],
        "solo": [],
    }


def gains(settings: dict) -> list[float]:
    """What each stem is played at: a muted stem is silent, and while any stem is soloed, only the
    soloed ones sound (a stem both muted and soloed stays silent). Levels are kept as set."""
    names = MODES[settings["mode"]]["stems"]
    solo = [n for n in settings["solo"] if n in names]
    out = []
    for name in names:
        heard = name not in settings["mute"] and (not solo or name in solo)
        out.append(gain(settings["levels"].get(name, UNITY)) if heard else 0.0)
    return out


PRESETS = {
    # name: (label, levels by stem, stems absent from the mode make the preset unavailable)
    "original": ("Original", None),
    "karaoke": ("Karaoké (sans voix)", {"vocals": 0}),
    "vocals": ("Voix seule", {"drums": 0, "bass": 0, "other": 0, "instrumental": 0}),
    "no_bass": ("Sans basse", {"bass": 0}),
    "no_drums": ("Sans batterie", {"drums": 0}),
}


def presets_for(mode: str) -> list[str]:
    names = set(MODES[mode]["stems"])
    return [k for k, (_, levels) in PRESETS.items() if levels is None or set(levels) & names]


def apply_preset(settings: dict, preset: str) -> dict:
    """Presets only set levels (and clear mute and solo); "original" plays the recording."""
    names = MODES[settings["mode"]]["stems"]
    levels = PRESETS[preset][1]
    if levels is None:
        return {**settings, "on": False}
    return {
        **settings,
        "on": True,
        "levels": {n: levels.get(n, UNITY) for n in names},
        "mute": [],
        "solo": [],
    }


def current_preset(settings: dict) -> str:
    """The preset these settings are, or "custom"."""
    if not settings["on"]:
        return "original"
    if settings["mute"] or settings["solo"]:
        return "custom"
    for key in presets_for(settings["mode"]):
        if key != "original" and apply_preset(settings, key)["levels"] == settings["levels"]:
            return key
    return "custom"


def checked(settings) -> dict | None:
    """Settings read back from a project, or None when they are not usable (an older or newer
    format, a hand edit): the mixer then opens as new."""
    if not isinstance(settings, dict) or settings.get("mode") not in MODES:
        return None
    names = MODES[settings["mode"]]["stems"]
    levels = settings.get("levels")
    if not isinstance(levels, dict):
        return None
    try:
        clean = {n: max(0, min(TOP, int(levels.get(n, UNITY)))) for n in names}
    except (TypeError, ValueError):
        return None

    def names_in(key):
        value = settings.get(key)
        return [n for n in value if n in names] if isinstance(value, list) else []

    return {
        "mode": settings["mode"],
        "on": bool(settings.get("on", True)),
        "levels": clean,
        "mute": names_in("mute"),
        "solo": names_in("solo"),
    }


# The model ----------------------------------------------------------------------------------
def model_path() -> Path:
    return library.data_dir() / "models" / "separation" / MODEL["file"]


def model_installed() -> bool:
    """Its size is checked here; its content was checked by SHA-256 when it was downloaded."""
    path = model_path()
    return path.is_file() and path.stat().st_size == MODEL["size"]


def download_model(task, opener=None) -> Path:
    from . import transcribe

    kwargs = {"opener": opener} if opener else {}
    return transcribe.fetch(RELEASE + MODEL["file"], model_path(), MODEL, task, **kwargs)


def delete_model() -> None:
    """The separated stems stay: they need the model only to be made."""
    for path in (model_path(), model_path().with_suffix(".part")):
        path.unlink(missing_ok=True)


# The cache ----------------------------------------------------------------------------------
def cache_root() -> Path:
    return library.data_dir() / "stems"


def cache_dir(fingerprint: str, mode: str) -> Path:
    """One folder per recording, mode and model file: a new model never reuses an old result."""
    return cache_root() / f"{fingerprint}-{mode}-{MODEL['id']}-{MODEL['sha256'][:12]}"


def cached(fingerprint: str, mode: str) -> Path | None:
    folder = cache_dir(fingerprint, mode)
    try:
        info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = [folder / f"{name}.flac" for name in MODES[mode]["stems"]]
    ok = info.get("version") == FORMAT_VERSION and all(f.is_file() for f in files)
    return folder if ok else None


def song_folders(fingerprint: str) -> list[Path]:
    """Everything kept for one recording, finished or not (any mode, any model)."""
    root = cache_root()
    if not fingerprint or not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(fingerprint + "-"))


def size_of(folders: list[Path]) -> int:
    total = 0
    for folder in folders:
        for f in folder.rglob("*"):
            try:
                total += f.stat().st_size if f.is_file() else 0
            except OSError:
                pass
    return total


def total_size() -> int:
    root = cache_root()
    return size_of([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else 0


def delete_song(fingerprint: str) -> None:
    """Only the separated stems: the recording, the project and its settings are not here."""
    for folder in song_folders(fingerprint):
        shutil.rmtree(folder, ignore_errors=True)


def delete_all() -> None:
    root = cache_root()
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)


def arrange(mode: str, sources: np.ndarray, mix: np.ndarray) -> dict[str, np.ndarray]:
    """The model's sources (S, L, 2) as the mode's stems. What the model leaves over goes into the
    last stem, so that the stems at their own level add up exactly to the recording."""
    by_name = dict(zip(MODEL["sources"], sources, strict=True))
    vocals = by_name["vocals"]
    if mode == "karaoke":
        return {"vocals": vocals, "instrumental": mix - vocals}
    drums, bass = by_name["drums"], by_name["bass"]
    return {"vocals": vocals, "drums": drums, "bass": bass, "other": mix - vocals - drums - bass}


def write(folder: Path, stems: dict[str, np.ndarray], sr: int, about: dict) -> Path:
    """FLAC 16-bit, lossless once written; a stem louder than full scale is stored scaled down and
    scaled back on reading. Written beside, renamed when complete."""
    import av

    part = folder.with_name(folder.name + ".part")
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    scales = {}
    for name, y in stems.items():
        peak = float(np.abs(y).max()) if len(y) else 0.0
        scale = max(1.0, peak * 1.0001)
        scales[name] = scale
        pcm = np.clip(np.round(y / scale * 32768), -32768, 32767).astype(np.int16)
        with av.open(str(part / f"{name}.flac"), "w", format="flac") as container:
            stream = container.add_stream("flac", rate=sr, layout="stereo")
            for start in range(0, len(pcm), sr * 10):
                frame = av.AudioFrame.from_ndarray(
                    np.ascontiguousarray(pcm[start : start + sr * 10]).reshape(1, -1),
                    format="s16",
                    layout="stereo",
                )
                frame.sample_rate = sr
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode(None):
                container.mux(packet)
    info = {
        **about,
        "version": FORMAT_VERSION,
        "model": MODEL["id"],
        "model_sha256": MODEL["sha256"],
        "samplerate": sr,
        "frames": len(next(iter(stems.values()))),
        "stems": list(stems),
        "scale": scales,
    }
    (part / "info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    shutil.rmtree(folder, ignore_errors=True)
    os.replace(part, folder)
    return folder


def load(folder: Path, mode: str, sr: int, frames: int, should_cancel=None) -> np.ndarray:
    """The stems at the player's rate, cut or padded to the recording's `frames`: (S, frames, 2),
    float16 (a quarter of a 4-minute song's stems is 23 MB)."""
    from . import audio

    info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
    names = MODES[mode]["stems"]
    out = np.zeros((len(names), frames, 2), dtype=np.float16)
    for i, name in enumerate(names):
        y = audio.decode(folder / f"{name}.flac", sr, should_cancel=should_cancel)
        n = min(frames, len(y))
        out[i, :n] = y[:n] * float(info["scale"].get(name, 1.0))
    return out


# Before separating --------------------------------------------------------------------------
def needed_mb(duration: float, mode: str) -> int:
    return int(len(MODES[mode]["stems"]) * duration * FLAC_BYTES_PER_SECOND / 2**20) + 1


def removable(folder: Path) -> bool:
    """On a USB stick or a memory card (Windows' own word for it)."""
    if sys.platform != "win32":
        return False
    import ctypes

    drive = os.path.splitdrive(str(folder.resolve()))[0]
    return bool(drive) and ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == 2


def space_problem(duration: float, mode: str) -> str | None:
    """Why the stems cannot be written, written for the user, or None."""
    root = cache_root()
    why = library.unwritable(root)
    if why:
        return f"Impossible d'écrire dans {root} : {why}."
    need = needed_mb(duration, mode) + SPACE_MARGIN_MB
    free = library.free_mb(root)
    if free and free < need:
        return (
            f"Pas assez de place sur le disque de {root} : {free} Mo libres, "
            f"environ {need} Mo nécessaires pour les pistes de ce morceau."
        )
    return None


def size_text(size: int) -> str:
    if size >= 2**30:
        return f"{size / 2**30:.1f} Go".replace(".", ",")
    return f"{max(1, round(size / 2**20))} Mo"
