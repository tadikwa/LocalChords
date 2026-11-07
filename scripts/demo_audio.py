"""An original synthetic piece for the README screenshots: no recording, no commercial title.

Usage: demo_audio.py <out.wav>

A progression in D major at 92 BPM, played by a bass, chord stabs and an arpeggio, all additive
synthesis. The chords are known, so the screenshots can be checked against them.
"""

import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 92
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SHAPES = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10), "sus4": (0, 5, 7)}
# (root, quality, bass or None, beats): two passes of a verse, then an ending.
VERSE = [
    ("D", "maj", None, 4), ("A", "maj", "C#", 4), ("B", "min", None, 4), ("G", "maj", None, 4),
    ("D", "maj", "F#", 4), ("G", "maj", None, 4), ("E", "min", None, 4), ("A", "7", None, 4),
]  # fmt: skip
ENDING = [("B", "min", None, 4), ("F#", "min", None, 4), ("G", "maj", None, 4),
          ("A", "sus4", None, 2), ("A", "maj", None, 2), ("D", "maj", None, 8)]  # fmt: skip


def tone(midi: float, seconds: float, decay: float, bright: int = 5) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    f = 440.0 * 2 ** ((midi - 69) / 12)
    wave_ = sum(np.sin(2 * np.pi * f * k * t) / k**1.6 for k in range(1, bright + 1))
    attack = np.minimum(1.0, t / 0.006)
    return wave_ * attack * np.exp(-decay * t)


def add(out: np.ndarray, at: float, part: np.ndarray, gain: float) -> None:
    i = int(at * SR)
    j = min(len(out), i + len(part))
    out[i:j] += gain * part[: j - i]


def render() -> np.ndarray:
    beat = 60.0 / BPM
    bars = VERSE + VERSE + ENDING
    total = sum(b for *_, b in bars) * beat + 2.0
    out = np.zeros(int(total * SR))
    now = 0.0
    for root, quality, bass, beats in bars:
        r = NOTES.index(root)
        low = NOTES.index(bass) if bass else r
        chord = [60 + r + i if 60 + r + i < 69 else 48 + r + i for i in SHAPES[quality]]
        for b in range(beats):
            at = now + b * beat
            if b % 2 == 0:
                add(out, at, tone(36 + low if low < 7 else 24 + low, beat * 1.8, 2.2, 4), 0.55)
            else:
                for n in chord:
                    add(out, at, tone(n, beat * 0.9, 5.0), 0.16)
            # Eighth-note arpeggio an octave up.
            for e, n in enumerate(sorted(chord)[:3] * 2):
                if e < 2:
                    add(out, at + e * beat / 2, tone(n + 12, beat, 4.0, 3), 0.09)
        now += beats * beat
    fade = np.linspace(1, 0, int(2.0 * SR))
    out[-len(fade) :] *= fade
    return out / np.max(np.abs(out)) * 0.8


def main() -> None:
    path = Path(sys.argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (render() * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    print(path, f"{len(pcm) / SR:.1f} s")


if __name__ == "__main__":
    main()
