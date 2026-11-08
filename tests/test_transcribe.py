import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest

from localchords import transcribe as T

RATE = T.RATE


def token(text, ms):
    return {"text": text, "offsets": {"from": ms, "to": ms + 200}}


def segment(text, start_ms, end_ms, tokens):
    return {"text": text, "offsets": {"from": start_ms, "to": end_ms}, "tokens": tokens}


def loud(seconds=30):
    t = np.arange(int(seconds * RATE)) / RATE
    return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_lines_from_keeps_word_starts_and_accents():
    data = {
        "transcription": [
            segment(
                " Été doré",
                1000,
                2500,
                [
                    token("[_BEG_]", 1000),
                    token(" Ét", 1000),
                    token("é", 1200),
                    token(" doré", 1700),
                ],
            )
        ]
    }
    (line,) = T.lines_from(data, loud())
    assert line == {"text": "Été doré", "start": 1.0, "end": 2.5, "words": [[0, 1.0], [4, 1.7]]}


def test_loops_credits_and_words_in_silence_are_dropped():
    y = loud()
    y[int(20 * RATE) :] = 0  # silence from 20 s
    same = [
        segment(
            " Encore toi",
            i * 1000,
            i * 1000 + 900,
            [token(" Encore", i * 1000), token(" toi", i * 1000 + 400)],
        )
        for i in range(8)
    ]
    data = {
        "transcription": [
            *same,
            segment(" Sous-titres réalisés par la communauté", 9000, 10000, []),
            segment(" la la la la la la la la la la la la la la la la", 11000, 15000, []),
            segment(" Plus personne", 21000, 23000, [token(" Plus", 21000)]),
        ]
    }
    lines = T.lines_from(data, y)
    assert [x["text"] for x in lines] == ["Encore toi"] * 3


def test_download_checks_size_and_hash_and_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path))
    blob = b"modele" * 1000
    fake = {
        "id": "fake",
        "file": "ggml-fake.bin",
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "label": "",
        "note": "",
    }
    monkeypatch.setattr(T, "MODELS", [fake])

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    task = T.Task()
    path = T.download("fake", task, opener=lambda req, timeout: R(blob))
    assert path.read_bytes() == blob and T.installed("fake") and task.progress == 1.0
    assert path.parent == tmp_path / "models" / "whisper"  # the data folder, portable or not
    T.delete_model("fake")
    assert not T.installed("fake")
    with pytest.raises(T.TranscribeError, match="SHA-256"):
        T.download("fake", T.Task(), opener=lambda req, timeout: R(blob[:-1] + b"x"))
    assert not list((tmp_path / "models" / "whisper").iterdir())  # nothing half-written is kept
    task = T.Task()
    task.cancel()
    with pytest.raises(T.TranscribeError, match="annulé"):
        T.download("fake", task, opener=lambda req, timeout: R(blob))
    assert not list((tmp_path / "models" / "whisper").iterdir())


def test_no_model_installed_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path))
    assert T.installed_models() == []
    with pytest.raises(T.TranscribeError, match="modèle"):
        T.transcribe(tmp_path / "x.wav", T.DEFAULT_MODEL, "fr", T.Task())


def test_task_reports_errors_instead_of_raising():
    def work(task):
        raise T.TranscribeError("non")

    task = T.run(work)
    for _ in range(200):
        if task.done:
            break
        import time

        time.sleep(0.01)
    assert task.done and task.error == "non"


def test_engine_gets_ascii_names_in_the_models_folder(tmp_path, monkeypatch):
    """whisper-cli opens ANSI names only: a Cyrillic folder must never reach its arguments."""
    home = tmp_path / "Привет été"
    home.mkdir()
    (home / T.MODELS[0]["file"]).write_bytes(b"0")
    monkeypatch.setattr(T, "models_dir", lambda: home)
    monkeypatch.setattr(T, "engine_ready", lambda: True)
    monkeypatch.setattr(T, "installed", lambda mid: True)
    monkeypatch.setattr(T.audio, "decode", lambda *a, **k: np.zeros((RATE, 1), np.float32))
    seen = {}

    def run(cmd, task, cwd=None):
        seen["cmd"], seen["cwd"] = cmd, cwd
        out = Path(cwd) / cmd[cmd.index("-of") + 1]
        out.with_suffix(".json").write_text('{"transcription": []}', encoding="utf-8")

    monkeypatch.setattr(T, "_run_engine", run)
    T.transcribe(tmp_path / "Привет.wav", T.MODELS[0]["id"], "fr", T.Task())
    assert seen["cwd"] == home
    assert all(arg.isascii() for arg in seen["cmd"][1:]), seen["cmd"]
    assert not [p for p in home.iterdir() if p.is_dir()]  # the temporary folder is gone


@pytest.mark.slow
def test_engine_on_an_instrumental_writes_no_words(tmp_path, monkeypatch):
    """The demo song has no voice: a model run over it must not invent lyrics."""
    bench = Path(__file__).parents[1] / "work" / "lyrics-bench" / "models"  # kept out of git
    if not T.installed_models() and bench.is_dir():
        monkeypatch.setattr(T, "models_dir", lambda: bench)
    if not (T.engine_ready() and T.installed_models()):
        pytest.skip("moteur ou modèle absent")
    import wave

    t = np.arange(20 * RATE) / RATE
    chords = sum(np.sin(2 * np.pi * f * t) for f in (261.6, 329.6, 392.0)) * 0.1
    path = tmp_path / "instrumental.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((chords * 32767).astype(np.int16).tobytes())
    result = T.transcribe(path, T.installed_models()[0], "fr", T.Task())
    assert result["lines"] == [], json.dumps(result["lines"], ensure_ascii=False)
