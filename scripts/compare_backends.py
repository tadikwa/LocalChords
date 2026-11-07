"""torch against ONNX Runtime, through the program's own analysis, on every file of Tiny AAM,
GuitarSet and a few whole songs: are beats, chords, key and meter the same?

    LOCALCHORDS_BACKEND=torch python scripts/compare_backends.py run work/v11/torch [songs...]
    python scripts/compare_backends.py run work/v11/onnx [songs...]
    python scripts/compare_backends.py diff work/v11/torch work/v11/onnx
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

CACHE = Path.home() / "AppData/Local/chordotomy/chordotomy/Cache"


def files(songs):
    tiny = sorted((CACHE / "tinyAAM.zip.unzip/audio-mixes-mp3").glob("*.mp3"))
    guitarset = sorted((CACHE / "audio_mono-mic.zip.unzip").glob("*.wav"))
    return [("tiny", p) for p in tiny] + [("gs", p) for p in guitarset] + [
        ("song", Path(s)) for s in songs
    ]


def run(out, songs):
    from localchords import audio, engines

    out.mkdir(parents=True, exist_ok=True)
    for group, path in files(songs):
        y = audio.decode(path, engines.ANALYSIS_SR, channels=1)[:, 0]
        start = time.perf_counter()
        result = engines.analyze(y, "model", lambda f, t: None)
        seconds = time.perf_counter() - start
        record = {"file": str(path), "group": group, "seconds": seconds,
                  "duration": len(y) / engines.ANALYSIS_SR, "analysis": result}
        (out / f"{group}_{path.stem}.json").write_text(json.dumps(record), encoding="utf-8")
        print(f"{group} {path.stem}: {seconds:.1f} s", result["engine"].get("backend"), flush=True)


def diff(a_dir, b_dir):
    groups: dict = {}
    for a_path in sorted(a_dir.glob("*.json")):
        a = json.loads(a_path.read_text(encoding="utf-8"))
        b = json.loads((b_dir / a_path.name).read_text(encoding="utf-8"))
        ra, rb = a["analysis"], b["analysis"]
        sa, sb = ra["segments"], rb["segments"]
        same_count = len(ra["beats"]) == len(rb["beats"])
        beat_shift = (float(np.abs(np.subtract(ra["beats"], rb["beats"])).max())
                      if same_count and ra["beats"] else None)
        chords_same = [(s["chord"], s["bass"]) for s in sa] == [(s["chord"], s["bass"]) for s in sb]
        bounds_shift = (max(abs(x["start_time"] - y["start_time"]) for x, y in zip(sa, sb, strict=True))
                        if chords_same and sa else None)
        # The chord heard at each tenth of a second, so a difference is weighed by how long it lasts.
        grid = np.arange(0, a["duration"], 0.1)

        def at(segments, grid=grid):
            starts = np.array([s["start_time"] for s in segments])
            names = [s["chord"] for s in segments]
            return [names[max(int(np.searchsorted(starts, t, "right")) - 1, 0)] for t in grid]

        agree = float(np.mean([x == y for x, y in zip(at(sa), at(sb), strict=True)])) if sa else 1.0
        row = {
            "file": a_path.stem, "beats_same_count": same_count, "beat_shift": beat_shift,
            "chords_same": chords_same, "bounds_shift": bounds_shift, "time_agreement": agree,
            "key_same": ra["global_key"] == rb["global_key"],
            "meter_same": ra["meter"]["beats_per_bar"] == rb["meter"]["beats_per_bar"]
            and ra["meter"]["bar_lines"] == rb["meter"]["bar_lines"],
            "followed_same": ra["followed_tempo"] == rb["followed_tempo"],
            "seconds": (a["seconds"], b["seconds"]), "duration": a["duration"],
        }
        groups.setdefault(a["group"], []).append(row)
    summary = {}
    for group, rows in groups.items():
        summary[group] = {
            "files": len(rows),
            "chords_identical": sum(r["chords_same"] for r in rows),
            "beats_identical_count": sum(r["beats_same_count"] for r in rows),
            "max_beat_shift_s": max((r["beat_shift"] or 0) for r in rows),
            "max_boundary_shift_s": max((r["bounds_shift"] or 0) for r in rows),
            "min_time_agreement": min(r["time_agreement"] for r in rows),
            "key_identical": sum(r["key_same"] for r in rows),
            "meter_identical": sum(r["meter_same"] for r in rows),
            "followed_identical": sum(r["followed_same"] for r in rows),
            "seconds_a": round(sum(r["seconds"][0] for r in rows), 1),
            "seconds_b": round(sum(r["seconds"][1] for r in rows), 1),
            "audio_seconds": round(sum(r["duration"] for r in rows), 1),
            "differing": [r for r in rows if not (r["chords_same"] and r["key_same"]
                                                  and r["meter_same"] and r["beats_same_count"])],
        }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(Path(sys.argv[2]), sys.argv[3:])
    else:
        diff(Path(sys.argv[2]), Path(sys.argv[3]))
