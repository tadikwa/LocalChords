"""Measure what really comes out of the speakers: pitch, speed and loops of the transposed audio.

Runs in a separate environment with `soundcard` (WASAPI loopback), never in the program's own:
    uv venv meas && uv pip install --python meas/Scripts/python.exe soundcard numpy
    meas/Scripts/python.exe scripts/measure_pitch.py signal ref.wav
    meas/Scripts/python.exe scripts/measure_pitch.py record 60 rec.wav [stamp.json]
    meas/Scripts/python.exe scripts/measure_pitch.py analyze rec.wav stamp.json schedule.json

The reference signal: 20 s of a 440 Hz sine, then a ladder of 0.5 s notes, note k at k semitones
above 440 Hz (k cycling 0..11), so that a run of the pitch track gives pitch, speed and position.
"""

from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

SR = 44100
SINE_END = 20.0
NOTE = 0.5


def write_wav(path, y, sr):
    data = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1] if data.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        y = np.frombuffer(w.readframes(n), "<i2").astype(np.float32) / 32767
    return y.reshape(-1, ch).mean(axis=1), sr


def signal(path):
    t = np.arange(int(SINE_END * SR)) / SR
    parts = [np.sin(2 * np.pi * 440 * t)]
    tn = np.arange(int(NOTE * SR)) / SR
    phase = 0.0
    for k in range(80):  # 40 s of ladder
        f = 440 * 2 ** ((k % 12) / 12)
        parts.append(np.sin(phase + 2 * np.pi * f * tn))
        phase += 2 * np.pi * f * NOTE
    y = 0.3 * np.concatenate(parts)
    write_wav(path, np.stack([y, y], 1), SR)


def record(seconds, path, stamp=None):
    import soundcard as sc

    mic = sc.get_microphone(sc.default_speaker().name, include_loopback=True)
    sr = 48000
    with mic.recorder(samplerate=sr, channels=2, blocksize=1024) as rec:
        rec.record(numframes=1024)  # the first block arrives late; the clock starts after it
        started = time.time()
        blocks = [rec.record(numframes=sr // 10) for _ in range(int(seconds * 10))]
    write_wav(path, np.concatenate(blocks), sr)
    if stamp:
        with open(stamp, "w") as f:
            json.dump({"start": started, "sr": sr}, f)


def peak_hz(x, sr, pad=1 << 20):
    """The strongest frequency, interpolated between bins."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), max(pad, len(x))))
    spec[: int(60 * len(spec) * 2 / sr)] = 0  # nothing below 60 Hz is a note here
    i = int(np.argmax(spec))
    a, b, c = np.log(spec[i - 1 : i + 2] + 1e-12)
    shift = 0.5 * (a - c) / (a - 2 * b + c)
    return (i + shift) * sr / (2 * (len(spec) - 1))


def track(x, sr, frame=4096, hop=480):
    """(time, semitones above 440 Hz) every 10 ms, NaN where it is quiet."""
    out = []
    for start in range(0, len(x) - frame, hop):
        piece = x[start : start + frame]
        level = np.sqrt(np.mean(piece**2))
        f = peak_hz(piece, sr, 1 << 15) if level > 1e-4 else np.nan
        out.append(((start + frame / 2) / sr, 12 * np.log2(f / 440) if f == f else np.nan))
    return np.array(out)


def runs(semis):
    """Runs of equal rounded pitch as (value, length in frames, median cents off)."""
    out = []
    rounded = np.round(semis)
    start = 0
    for i in range(1, len(semis) + 1):
        if i == len(semis) or rounded[i] != rounded[start]:
            seg = semis[start:i]
            if not np.isnan(rounded[start]):
                out.append((int(rounded[start]), i - start, float(np.median(seg - rounded[start]) * 100)))
            start = i
    return out


def analyze(rec_path, stamp_path, schedule_path):
    x, sr = read_wav(rec_path)
    stamp = json.loads(Path(stamp_path).read_text())
    schedule = json.loads(Path(schedule_path).read_text(encoding="utf-8"))
    results = []
    for c in schedule["conditions"]:
        # Skip 0.4 s at both ends: the device latency and the change itself.
        a = int((c["t0"] - stamp["start"] + 0.4) * sr)
        b = int((c["t1"] - stamp["start"] - 0.1) * sr)
        piece = x[max(a, 0) : max(b, 0)]
        r = {k: c[k] for k in ("name", "semitones", "audio", "rate", "region") if k in c}
        expect = c["semitones"] if c["audio"] else 0
        r["expected_semitones"] = expect
        r["level"] = float(np.sqrt(np.mean(piece**2))) if len(piece) else 0.0
        if c.get("position"):
            p0, p1 = c["position"]
            r["display_advance_per_s"] = round((p1 - p0) / (c["t1"] - c["t0"]), 3)
        if c["region"] == "sine":
            hz = peak_hz(piece, sr)
            want = 440 * 2 ** (expect / 12)
            r.update(hz=round(hz, 2), expected_hz=round(want, 2),
                     cents_off=round(1200 * np.log2(hz / want), 1))
        else:
            tr = track(piece, sr)
            rs = runs(tr[:, 1])
            full = [q for q in rs[1:-1] if q[1] > 10]  # whole notes only
            note_s = [q[1] * 0.01 for q in full]
            r["notes"] = [q[0] for q in full]
            r["note_seconds"] = round(float(np.median(note_s)), 3) if note_s else None
            r["expected_note_seconds"] = round(NOTE / c["rate"], 3)
            r["median_cents_off"] = round(float(np.median([q[2] for q in full])), 1) if full else None
            if "expect_notes" in c:
                want = [(n + expect) for n in c["expect_notes"]]
                got = r["notes"]
                r["expected_cycle"] = want
                # The loop is right when what plays is that cycle, repeated, from any phase.
                r["loop_ok"] = bool(got) and all(
                    got[i] == want[(want.index(got[0]) + i) % len(want)] if got[0] in want else False
                    for i in range(len(got))
                )
        results.append(r)
    return results


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "signal":
        signal(sys.argv[2])
    elif cmd == "record":
        record(float(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "analyze":
        res = analyze(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(res, ensure_ascii=False, indent=1))
