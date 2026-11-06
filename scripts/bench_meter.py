"""Bar lines against Tiny AAM's annotated bars (CC BY 4.0), downloaded by `chordotomy evaluate`.

Run from the repository root. Prints per track and overall: the bar length found, and the share of
found downbeats that fall on annotated downbeats (70 ms). Results go to work/meter.json.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(os.environ["LOCALAPPDATA"]) / "chordotomy/chordotomy/Cache/tinyAAM.zip.unzip"


def reference(track: str):
    times, positions, labels = [], [], []
    text = (ROOT / "annotations" / f"{track}_beatinfo.arff").read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r"^([\d.]+),(\d+),(\d+),'([A-G]#?)(maj|min)'", line)
        if m:
            times.append(float(m[1]))
            positions.append(int(m[3]))
            labels.append(f"{m[4]}:{m[5]}")
    return np.array(times), np.array(positions), labels


def main():
    import mir_eval
    from localchords import audio, engines

    if len(sys.argv) > 2:
        engines.FOLLOW_TEMPO_BELOW = float(sys.argv[2])
    rows = []
    files = sorted((ROOT / "audio-mixes-mp3").glob("*.mp3"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(files)
    for path in files[:limit]:
        track = path.stem.split("_")[0]
        times, positions, chord_labels = reference(track)
        true_meter = int(positions.max())
        true_down = times[positions == 1]
        y = audio.decode(path, engines.ANALYSIS_SR, channels=1)[:, 0]
        start = time.perf_counter()
        result = engines.analyze(y, "model", lambda f, t: None)
        seconds = time.perf_counter() - start
        beats = np.array(result["beats"])
        labels = [
            (float(a), float(b), c)
            for a, b, c in zip(times, [*times[1:], times[-1] + 0.6], chord_labels, strict=True)
        ]
        ref_i = np.array([[a, b] for a, b, _ in labels])
        est_i = np.array([[s["start_time"], s["end_time"]] for s in result["segments"]])
        est_l = [s["chord"] for s in result["segments"]]
        scores = mir_eval.chord.evaluate(ref_i, [c for *_, c in labels], est_i, est_l)
        beat_f = mir_eval.beat.f_measure(mir_eval.beat.trim_beats(times), mir_eval.beat.trim_beats(beats))
        meter = result["meter"]
        found = beats[meter["bar_lines"]]
        near = [np.min(np.abs(true_down - t)) <= 0.07 for t in found]
        rows.append(
            {
                "track": track,
                "true": true_meter,
                "found": meter["beats_per_bar"],
                "confidence": meter["confidence"],
                "downbeat_precision": round(float(np.mean(near)), 3),
                "beat_f": round(float(beat_f), 3),
                "majmin": round(float(scores["majmin"]), 3),
                "sevenths": round(float(scores["sevenths"]), 3),
                "followed": result["followed_tempo"],
                "bar_jumps": int(np.sum(np.diff(meter["bar_lines"]) != meter["beats_per_bar"])),
                "grid_fit": result["grid_fit"],
                "seconds": round(seconds, 1),
                "duration": round(len(y) / engines.ANALYSIS_SR, 1),
            }
        )
        print(rows[-1], flush=True)
    meters = np.mean([r["true"] == r["found"] for r in rows])
    precision = np.mean([r["downbeat_precision"] for r in rows])
    weights = np.array([r["duration"] for r in rows])
    means = {k: round(float(np.average([r[k] for r in rows], weights=weights)), 3)
             for k in ("majmin", "sevenths", "beat_f", "downbeat_precision")}
    followed = sum(r["followed"] for r in rows)
    print(f"bar length right: {meters:.3f}; downbeat precision (plain): {precision:.3f}; "
          f"weighted {means}; followed {followed}/{len(rows)}")
    name = sys.argv[2] if len(sys.argv) > 2 else "default"
    Path(f"work/meter_{name}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
