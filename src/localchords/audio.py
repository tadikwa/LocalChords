"""Decoding, through PyAV's bundled FFmpeg: every common format, Unicode paths, clear errors."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

AUDIO_EXTENSIONS = (
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wma", ".aif", ".aiff",
    ".mp4", ".webm", ".mka",
)  # fmt: skip


class AudioError(Exception):
    """A file that cannot be read; the message is written for the user."""


class Cancelled(Exception):
    pass


def fingerprint(path: Path) -> str:
    """Identifies a recording fast: its size, and its first and last megabyte."""
    size = path.stat().st_size
    sha = hashlib.sha256(str(size).encode())
    with path.open("rb") as f:
        sha.update(f.read(1 << 20))
        if size > 1 << 20:
            f.seek(-(1 << 20), 2)
            sha.update(f.read(1 << 20))
    return sha.hexdigest()[:32]


def _open(path: Path):
    import av

    try:
        return av.open(str(path))
    except FileNotFoundError as exc:
        raise AudioError(f"Fichier introuvable : {path}") from exc
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise AudioError(
            f"Impossible de lire « {path.name} » : le fichier est endommagé ou son format "
            "n'est pas reconnu."
        ) from exc


def decode(
    path: Path,
    sr: int,
    channels: int = 2,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> np.ndarray:
    """All the audio as float32 samples of shape (n, channels) at the sample rate asked for."""
    import av

    layout = {1: "mono", 2: "stereo"}[channels]
    with _open(path) as container:
        if not container.streams.audio:
            raise AudioError(f"« {path.name} » ne contient pas de piste audio.")
        stream = container.streams.audio[0]
        stream.thread_type = "AUTO"
        resampler = av.AudioResampler(format="flt", layout=layout, rate=sr)
        parts: list[np.ndarray] = []
        try:
            for frame in container.decode(stream):
                if should_cancel and should_cancel():
                    raise Cancelled
                for out in resampler.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1, channels).copy())
            for out in resampler.resample(None):
                parts.append(out.to_ndarray().reshape(-1, channels).copy())
        except av.FFmpegError as exc:
            # A truncated file still plays up to the damage, as other players do.
            if not parts:
                raise AudioError(
                    f"Impossible de décoder « {path.name} » : le fichier est endommagé."
                ) from exc
    if not parts:
        raise AudioError(f"« {path.name} » ne contient aucun son décodable.")
    return np.concatenate(parts)


def metadata(path: Path) -> dict:
    """Title, artist, album, duration and lyrics as the file states them, "" where it is silent
    (identify.from_file falls back on the file's name)."""
    with _open(path) as container:
        tags = {k.lower(): v for k, v in container.metadata.items()}
        if container.streams.audio:
            tags |= {k.lower(): v for k, v in container.streams.audio[0].metadata.items()}
        duration = container.duration / 1_000_000 if container.duration else None
    # Lyrics: "lyrics" (MP4, Matroska), "lyrics-eng" (ID3 USLT), "unsyncedlyrics" (Vorbis).
    words = next((v for k, v in tags.items() if k.startswith(("lyrics", "unsyncedlyrics"))), "")
    return {
        "title": tags.get("title") or "",
        "artist": tags.get("artist") or "",
        "album_artist": tags.get("album_artist") or "",
        "album": tags.get("album") or "",
        "duration": duration,
        "lyrics": words.strip(),
    }


def peaks(y: np.ndarray, n: int = 3000) -> np.ndarray:
    """The waveform as n bytes: the loudest sample per slice, on a scale of 0 to 255."""
    mono = np.abs(y).max(axis=1) if y.ndim == 2 else np.abs(y)
    if len(mono) == 0:
        return np.zeros(n, dtype=np.uint8)
    edges = np.minimum(np.linspace(0, len(mono), n, endpoint=False).astype(int), len(mono) - 1)
    slices = np.maximum.reduceat(mono, edges)
    return (np.clip(slices / max(float(mono.max()), 1e-6), 0, 1) * 255).astype(np.uint8)
