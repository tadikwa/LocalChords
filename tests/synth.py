"""Synthetic audio with a known chord progression: the ground truth for engine tests.

Additive tones with a decay envelope, a bass note an octave or two under the chord and a click on
every beat, so a beat tracker has something to lock on to. Not music, but the answer is known.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUALITIES = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dim": (0, 3, 6),
    "sus4": (0, 5, 7),
}


def _tone(freq: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    wave_ = sum(np.sin(2 * np.pi * freq * k * t) / k**1.5 for k in range(1, 6))
    return wave_ * np.exp(-1.5 * t)


def chord_audio(label: str, n: int) -> np.ndarray:
    root, quality = label.split(":")
    r = NOTES.index(root)
    out = np.zeros(n)
    for interval in QUALITIES[quality]:
        out += _tone(261.63 * 2 ** ((r + interval) / 12), n)
    return out + 1.2 * _tone(65.41 * 2 ** (r / 12), n)


def render(
    progression: list[tuple[str, float]], bpm: float = 100.0, *, lead_in: float = 0.0
) -> tuple[np.ndarray, list[tuple[float, float, str]]]:
    """Mono float audio and the reference [(start, end, label)] for (chord, beats) pairs."""
    beat = 60.0 / bpm
    parts = [np.zeros(int(lead_in * SR))] if lead_in else []
    truth = []
    now = lead_in
    for label, beats in progression:
        n = int(beats * beat * SR)
        part = np.zeros(n) if label == "N" else chord_audio(label, n)
        if label != "N":
            # Retrigger on every beat, with a click, so the pulse is audible.
            for i in range(int(beats)):
                start = int(i * beat * SR)
                part[start:] += chord_audio(label, n - start) * 0.8
                click = min(int(0.01 * SR), n - start)
                noise = np.random.default_rng(i).standard_normal(click)
                part[start : start + click] += 2.0 * noise
        parts.append(part)
        truth.append((now, now + n / SR, label))
        now += n / SR
    y = np.concatenate(parts)
    peak = np.max(np.abs(y)) or 1.0
    return (y / peak * 0.8).astype(np.float32), truth


def write_wav(path: Path, y: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def agreement(segments: list[dict], truth: list[tuple[float, float, str]], *, triads=False) -> float:
    """Share of the duration where the engine's chord equals the reference, sampled every 50 ms."""

    def at(t, items):
        return next((label for s, e, label in items if s <= t < e), "N")

    est = [(s["start_time"], s["end_time"], s["chord"]) for s in segments]
    times = np.arange(truth[0][0], truth[-1][1], 0.05)

    def reduce(label):
        if not triads or label == "N":
            return label
        root, q = label.split(":")
        return f"{root}:{'min' if q.startswith('min') else 'maj'}"

    return float(np.mean([reduce(at(t, est)) == reduce(at(t, truth)) for t in times]))
