"""The real engines on audio with a known answer. Slow: seconds per test."""

import time

import numpy as np
import pytest
import synth

from localchords import audio, engines, worker

pytestmark = pytest.mark.slow
SR = engines.ANALYSIS_SR


def load(tmp_path, progression, bpm, name="x.wav", **kw):
    y, truth = synth.render(progression, bpm, **kw)
    path = synth.write_wav(tmp_path / name, y)
    return audio.decode(path, SR, channels=1)[:, 0], truth, path


def run(y, engine="model"):
    return engines.analyze(y, engine, lambda f, t: None)


@pytest.mark.parametrize("engine", ["model", "dsp"])
def test_triads_are_found_on_time(tmp_path, engine):
    prog = [("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:maj", 4)] * 4
    y, truth, _ = load(tmp_path, prog, 100)
    d = run(y, engine)
    assert synth.agreement(d["segments"], truth) > 0.95
    assert d["global_key"]["label"] == "C:maj"
    assert d["tempo"]["bpm"] == pytest.approx(100, abs=3)
    # Changes land within a beat of the truth (0.6 s at 100 BPM) and on the grid.
    assert set(s["start_time"] for s in d["segments"]) <= set(d["beats"])


def test_sevenths_read_at_least_their_triad(tmp_path):
    prog = [("D:min7", 4), ("G:7", 4), ("C:maj7", 4), ("A:min7", 4)] * 4
    y, truth, _ = load(tmp_path, prog, 90)
    d = run(y)
    assert synth.agreement(d["segments"], truth, triads=True) > 0.95
    labels = {s["chord"] for s in d["segments"]}
    assert "G:7" in labels and "D:min7" in labels


def test_results_are_stable_between_runs(tmp_path):
    prog = [("E:min", 2), ("C:maj", 2), ("G:maj", 2), ("D:maj", 2)] * 4
    y, _, _ = load(tmp_path, prog, 140)
    first, second = run(y), run(y)
    assert first["segments"] == second["segments"] and first["beats"] == second["beats"]


def test_silent_lead_in_is_no_chord(tmp_path):
    prog = [("C:maj", 4), ("F:maj", 4), ("G:maj", 4), ("C:maj", 4)] * 4
    y, truth, _ = load(tmp_path, prog, 100, lead_in=4.0)
    d = run(y)
    assert d["segments"][0]["chord"] == "N" or d["segments"][0]["start_time"] > 2.0
    assert synth.agreement(d["segments"], truth, triads=True) > 0.9


def test_pure_silence_is_refused(tmp_path):
    with pytest.raises(engines.AnalysisError, match="silencieux"):
        run(np.zeros(SR * 5, dtype=np.float32))


def test_too_short_is_refused():
    with pytest.raises(engines.AnalysisError, match="court"):
        run(np.ones(100, dtype=np.float32) * 0.1)


def test_tempo_change_keeps_the_chords(tmp_path):
    # Known limit: chordotomy's grid has one tempo per file. The chords must survive a change.
    y1, t1 = synth.render([("C:maj", 4), ("F:maj", 4)] * 6, 90)
    y2, t2 = synth.render([("G:maj", 4), ("A:min", 4)] * 8, 130)
    end = t1[-1][1]
    truth = t1 + [(a + end, b + end, c) for a, b, c in t2]
    d = run(np.concatenate([y1, y2]))
    # 44.1k render fed in without resampling would be wrong: go through a file.
    path = synth.write_wav(tmp_path / "t.wav", np.concatenate([y1, y2]))
    d = run(audio.decode(path, SR, channels=1)[:, 0])
    assert synth.agreement(d["segments"], truth, triads=True) > 0.75


def test_worker_reports_progress_and_result(tmp_path):
    prog = [("C:maj", 4), ("F:maj", 4), ("G:maj", 4), ("C:maj", 4)] * 3
    _, _, path = load(tmp_path, prog, 100, "été à Noël.wav")
    job = worker.start(path, "model")
    messages = []
    deadline = time.time() + 180
    while time.time() < deadline and not any(m[0] in ("done", "error") for m in messages):
        messages += job.poll()
        time.sleep(0.05)
    kinds = [m[0] for m in messages]
    assert kinds[-1] == "done", messages[-1]
    assert "waveform" in kinds and "progress" in kinds
    fractions = [m[1] for m in messages if m[0] == "progress"]
    assert fractions == sorted(fractions)
    job.process.join(10)


def test_worker_can_be_cancelled_midway(tmp_path):
    y, _ = synth.render([("C:maj", 4), ("F:maj", 4)] * 40, 100)
    path = synth.write_wav(tmp_path / "long.wav", y)
    job = worker.start(path, "model")
    deadline = time.time() + 60
    started = False
    while time.time() < deadline and not started:
        started = any(m[0] == "progress" for m in job.poll())
        time.sleep(0.02)
    assert started
    t = time.time()
    job.cancel()
    assert not job.process.is_alive() and time.time() - t < 5


def test_worker_reports_a_corrupt_file(tmp_path):
    path = tmp_path / "abîmé.mp3"
    path.write_bytes(b"not audio" * 1000)
    job = worker.start(path, "dsp")
    messages = []
    deadline = time.time() + 60
    while time.time() < deadline and not any(m[0] == "error" for m in messages):
        messages += job.poll()
        time.sleep(0.05)
    error = next(m for m in messages if m[0] == "error")
    assert "abîmé" in error[1]


def test_a_worker_that_dies_is_reported_once(tmp_path):
    job = worker.Job.__new__(worker.Job)
    job.ended = job.answered = False

    class Dead:
        def poll(self):
            raise EOFError

    job.conn = Dead()
    first, second = job.poll(), job.poll()
    assert first[0][0] == "error" and second == []
