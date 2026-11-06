"""Run each engine on known synthetic progressions and print agreement and speed."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
import synth
from chordotomy import timeline

CASES = {
    "triads 100bpm": ([("C:maj",4),("A:min",4),("F:maj",4),("G:maj",4)]*6, 100),
    "sevenths 90bpm": ([("D:min7",4),("G:7",4),("C:maj7",4),("A:min7",4)]*6, 90),
    "fast 2-beat 140bpm": ([("E:min",2),("C:maj",2),("G:maj",2),("D:maj",2)]*12, 140),
    "sus+dim 110bpm": ([("A:sus4",4),("A:maj",4),("B:dim",4),("E:7",4)]*6, 110),
}
out = Path("work"); out.mkdir(exist_ok=True)
for name, (prog, bpm) in CASES.items():
    y, truth = synth.render(prog, bpm)
    p = synth.write_wav(out / (name.replace(" ", "_") + ".wav"), y)
    for engine in ("dsp", "model"):
        t = time.perf_counter()
        d = timeline.analyze(p, engine=engine)
        dt = time.perf_counter() - t
        print(f"{name:22s} {engine:6s} exact={synth.agreement(d['segments'],truth):.3f} triad={synth.agreement(d['segments'],truth,triads=True):.3f} "
              f"key={d['global_key']['label']} beats={len(d['beats'])} dur={len(y)/synth.SR:.0f}s t={dt:.1f}s "
              f"chords={[s['chord'] for s in d['segments']][:6]}", flush=True)
