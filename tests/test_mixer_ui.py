"""The Mixage panel in the window, offscreen. The separation process is replaced by a fake that
writes made-up stems into the cache, as the real one does (tests/test_separation.py)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import numpy as np
import pytest
from test_core import analysis as make_analysis
from test_ui import app, isolated, wait_for, wav  # noqa: F401 - fixtures

from localchords import audio, stems, transcribe, worker
from localchords.project import Project
from localchords.ui import mixer
from localchords.ui.main_window import MainWindow

SHARES = {"vocals": 0.4, "drums": 0.3, "bass": 0.2, "other": 0.1}


class FakeJob:
    """Writes the stems at once, then reports like the real process."""

    def __init__(self, path, mode, fingerprint, calls):
        calls.append(mode)
        y = audio.decode(path, 44100)
        if mode == "karaoke":
            layers = {"vocals": y * 0.4, "instrumental": y * 0.6}
        else:
            layers = {n: y * SHARES[n] for n in stems.MODES[mode]["stems"]}
        folder = stems.write(stems.cache_dir(fingerprint, mode), layers, 44100, {"mode": mode})
        self.messages = [
            ("progress", 0.5, "Séparation des instruments…"),
            ("done", str(folder), 2.0, len(y) / 44100),
        ]

    def poll(self):
        out, self.messages = self.messages, []
        return out

    def cancel(self):
        pass


@pytest.fixture
def fake_separation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker, "start_separation", lambda p, m, f: FakeJob(p, m, f, calls)
    )
    monkeypatch.setattr(stems, "model_installed", lambda: True)
    return calls


def opened(app, wav, tmp_path, file="song.lchords"):
    a = make_analysis(beats_each=4, bpm=120.0)
    a["segments"][-1]["end_time"] = 24.0
    info = {
        "path": str(wav),
        "title": "Été à Noël",
        "artist": "",
        "duration": 24.0,
        "fingerprint": audio.fingerprint(wav),
    }
    if not (tmp_path / file).exists():
        Project(info, a).save(tmp_path / file)
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / file)
    assert wait_for(app, lambda: window.audio_ready)
    return window


def separated(app, window, mode="musician"):
    c = window.mixer
    c.button.setChecked(True)
    c.panel.mode_buttons[mode].click()
    assert c.panel.separate.isEnabled()
    c.panel.separate.click()
    assert wait_for(app, lambda: c.panel.pages.currentWidget() is c.panel.console)
    return c


def test_nothing_is_separated_until_asked(app, wav, tmp_path, fake_separation):
    window = opened(app, wav, tmp_path)
    c = window.mixer
    assert not c.panel.isVisible() and window.player.mix is None
    window.song.mixer_button.click()
    assert c.panel.isVisible() and c.panel.pages.currentWidget() is c.panel.intro
    facts = c.panel.facts.text()
    assert "Place nécessaire" in facts and "jamais parfaite" in facts
    assert "Durée estimée" not in facts  # not measured yet on this computer
    assert fake_separation == []
    window.close()


def test_separate_then_mix_live_and_find_it_again(app, wav, tmp_path, fake_separation):
    window = opened(app, wav, tmp_path)
    c = separated(app, window)
    assert fake_separation == ["musician"]
    mix = window.player.mix
    assert mix is not None and mix.stems.shape[0] == 4
    assert len(mix) == len(mix.original)  # same clock as the recording
    assert window.settings["separation_speed"] == pytest.approx(2.0 / 24.0, rel=0.05)
    # Bass at zero, drums lower: heard at once, nothing else touched.
    rows = {r.name: r for r in c.panel.stem_rows}
    rows["bass"].slider.setValue(0)
    rows["drums"].slider.setValue(37)
    assert mix.target[0] == 0.0 and mix.target[3] == 0.0
    assert mix.target[2] == pytest.approx(stems.gain(37))
    assert rows["drums"].db.text() == "−12 dB" and rows["bass"].db.text() == "−∞"
    assert c.panel.preset_buttons["custom"].isChecked()
    # Solo keeps the others' levels; Original/Mix is one switch.
    rows["vocals"].solo.click()
    assert list(mix.target) == [0.0, 1.0, 0.0, 0.0, 0.0]
    rows["vocals"].solo.click()
    c.toggle_original()
    assert mix.target[0] == 1.0 and not mix.target[1:].any()
    c.toggle_original()
    assert mix.target[2] == pytest.approx(stems.gain(37))
    window.flush()
    saved = Project.load(window.project_file).view["mixer"]
    assert saved["levels"]["bass"] == 0 and saved["on"]
    window.close()

    again = opened(app, wav, tmp_path)
    assert wait_for(app, lambda: again.player.mix is not None)
    assert fake_separation == ["musician"]  # found again, not separated again
    assert again.mixer.settings["levels"] == {"vocals": 75, "drums": 37, "bass": 0, "other": 75}
    assert again.player.mix.target[3] == 0.0
    again.close()


def test_presets_and_the_custom_mix(app, wav, tmp_path, fake_separation):
    window = opened(app, wav, tmp_path)
    c = separated(app, window)
    mix = window.player.mix
    rows = {r.name: r for r in c.panel.stem_rows}
    rows["other"].slider.setValue(90)
    buttons = c.panel.preset_buttons
    assert set(buttons) == {"karaoke", "vocals", "no_bass", "no_drums", "custom"}
    buttons["karaoke"].click()
    assert mix.target[1] == 0.0 and mix.target[4] == 1.0  # vocals off, the rest as separated
    buttons["no_drums"].click()
    assert mix.target[1] == 1.0 and mix.target[2] == 0.0
    buttons["custom"].click()
    assert mix.target[4] == pytest.approx(stems.gain(90))
    c.panel.original.click()
    assert mix.target[0] == 1.0 and not any(b.isChecked() for b in buttons.values())
    window.close()


def test_karaoke_mode_has_its_own_presets(app, wav, tmp_path, fake_separation):
    window = opened(app, wav, tmp_path)
    c = separated(app, window, "karaoke")
    assert [r.name for r in c.panel.stem_rows] == ["vocals", "instrumental"]
    assert set(c.panel.preset_buttons) == {"karaoke", "vocals", "custom"}
    window.close()


def test_deleting_a_songs_stems_keeps_the_song(app, wav, tmp_path, fake_separation, monkeypatch):
    window = opened(app, wav, tmp_path)
    c = separated(app, window)
    fp = c.fp
    monkeypatch.setattr(mixer, "_confirm", lambda *a: True)
    c.delete_song()
    assert window.player.mix is None and stems.song_folders(fp) == []
    assert c.panel.pages.currentWidget() is c.panel.intro
    assert wav.exists() and window.project_file.exists()
    window.close()


def test_a_failed_download_is_said_and_can_be_retried(app, wav, tmp_path, monkeypatch):
    monkeypatch.setattr(stems, "model_installed", lambda: False)

    def fail(task):
        raise transcribe.TranscribeError("Le téléchargement a échoué : pas de réseau")

    monkeypatch.setattr(stems, "download_model", fail)
    window = opened(app, wav, tmp_path)
    c = window.mixer
    c.button.setChecked(True)
    assert "à télécharger une seule fois" in c.panel.facts.text()
    c.panel.separate.click()
    assert wait_for(app, lambda: not c.busy())
    assert c.panel.pages.currentWidget() is c.panel.intro
    assert "pas de réseau" in c.panel.warn.text()
    assert c.panel.separate.text() == "Réessayer" and c.panel.separate.isEnabled()
    window.close()


def test_cancel_stops_the_separation(app, wav, tmp_path, monkeypatch):
    cancelled = []

    class Slow:
        def poll(self):
            return [("progress", 0.1, "Séparation des instruments…")]

        def cancel(self):
            cancelled.append(True)

    monkeypatch.setattr(worker, "start_separation", lambda *a: Slow())
    monkeypatch.setattr(stems, "model_installed", lambda: True)
    window = opened(app, wav, tmp_path)
    c = window.mixer
    c.button.setChecked(True)
    c.panel.separate.click()
    assert wait_for(app, lambda: c.panel.step.text() == "Séparation des instruments…")
    window.player.play()  # the app stays usable meanwhile
    c.panel.cancel.click()
    assert cancelled and not c.busy() and c.panel.pages.currentWidget() is c.panel.intro
    window.close()


def test_export_writes_the_mix_as_set(app, wav, tmp_path, fake_separation, monkeypatch):
    window = opened(app, wav, tmp_path)
    c = separated(app, window)
    c.panel.preset_buttons["karaoke"].click()
    target = tmp_path / "out.flac"
    monkeypatch.setattr(
        mixer.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "FLAC (*.flac)")
    )
    c.export()
    assert wait_for(app, lambda: c.export_task is None)
    got = audio.decode(target, 44100)
    y = audio.decode(wav, 44100)
    assert len(got) == len(y)
    assert np.abs(got - y * 0.6).max() < 2e-3  # everything but the vocals
    window.close()


@pytest.mark.parametrize("width", [800, 1920, 5120])
def test_the_console_fits_the_width(app, wav, tmp_path, fake_separation, width):
    window = opened(app, wav, tmp_path)
    c = separated(app, window)
    window.resize(width, 900)
    app.processEvents()
    c.panel.reflow(width)
    cols = {c.panel.rows.getItemPosition(c.panel.rows.indexOf(r))[1] for r in c.panel.stem_rows}
    assert len(cols) == {800: 1, 1920: 4, 5120: 4}[width]
    assert (window.song.mixer_button.text() == " Mixage") == (width >= 1240)
    window.close()
