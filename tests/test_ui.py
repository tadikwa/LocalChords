"""The window, driven as a user would, offscreen. Playback is real but silent."""

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
import synth
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from test_core import analysis as make_analysis

from localchords import library
from localchords.project import Project
from localchords.ui import dialogs
from localchords.ui.main_window import MainWindow, app_instance


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "data"))


@pytest.fixture
def app():
    return app_instance()


@pytest.fixture
def wav(tmp_path):
    y, _ = synth.render([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)] * 3, 120)
    return synth.write_wav(tmp_path / "été à Noël.wav", y)


def wait_for(app, condition, seconds=30.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def seeded(app, wav, tmp_path):
    """A window on an analyzed song, without running an engine: the engine has its own tests."""
    a = make_analysis(beats_each=4, bpm=120.0)
    a["segments"][-1]["end_time"] = 24.0
    audio = {"path": str(wav), "title": "Été à Noël", "artist": "", "duration": 24.0}
    Project(audio, a).save(tmp_path / "song.lchords")
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert wait_for(app, lambda: window.audio_ready)
    return window


def click_beat(app, window, beat, button=Qt.MouseButton.LeftButton, double=False):
    grid = window.song.grid
    rect = grid.cells[beat]
    point = rect.center()
    QTest.mouseClick(grid, button, pos=point.toPoint())
    if double:
        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(point),
            grid.mapToGlobal(point),
            button,
            button,
            Qt.KeyboardModifier.NoModifier,
        )
        app.sendEvent(grid, event)
    app.processEvents()


def test_home_shows_nothing_recent_at_first(app):
    window = MainWindow(muted=True)
    assert not window.home.recent_title.isVisibleTo(window.home)
    window.close()


def test_open_grid_seek_and_highlight(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    s = window.song
    assert s.middle.currentWidget() is s.scroll
    assert s.key_button.text().startswith("Tonalité : C majeur")
    assert "120 BPM" in s.rhythm_button.text() and "4 temps" in s.rhythm_button.text()
    click_beat(app, window, 5)
    assert window.player.position == pytest.approx(window.project.grid()[5], abs=0.01)
    wait_for(app, lambda: s.grid.current == 5, 2)
    assert s.grid.current == 5
    assert s.now.text() == "Am" and "F" in s.next.text()
    assert s.place.text() == "mesure 2 · temps 2"
    window.close()


def test_correction_undo_and_reopen_without_analysis(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    grid = window.project.grid()
    window.apply_chord(4, 7, "D:min7", None)
    assert window.song.grid.symbols[4][0] == "Dm7"
    assert window.song.grid.symbols[4][2].edited
    window.flush()
    window.close()

    # Back from disk: no worker, the correction is there.
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert window.job is None
    assert window.song.grid.symbols[4][0] == "Dm7"
    window.undo()  # the undo stack does not outlive the session
    assert window.song.grid.symbols[4][0] == "Dm7"
    _ = grid
    window.close()


def test_undo_redo_buttons(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    assert not window.song.undo.isEnabled()
    window.apply_chord(0, 3, "E:min", None)
    assert window.song.undo.isEnabled()
    window.song.undo.click()
    assert window.song.grid.symbols[0][0] == "C"
    assert window.song.redo.isEnabled()
    window.song.redo.click()
    assert window.song.grid.symbols[0][0] == "Em"
    window.close()


def test_chord_editor_applies_with_transposition(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.song.transpose.set_value(2)
    window.song.transpose.changed.emit(2)
    assert window.song.grid.symbols[0][0] == "D"
    editor = dialogs.ChordEditor(window.project, 0, 0, window)
    assert editor.input.text() == "D"
    editor.input.setText("E/G#")
    editor.scope_selection.setChecked(True)
    editor._accept()
    assert editor.result_label == "D:maj" and editor.result_bass == "F#"
    assert editor.result_span == (0, 0)
    window.apply_chord(*editor.result_span, editor.result_label, editor.result_bass)
    assert window.song.grid.symbols[0][0] == "E/G♯"
    window.close()


def test_chord_editor_refuses_nonsense_and_picks_with_buttons(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    editor = dialogs.ChordEditor(window.project, 0, 0, window)
    editor.input.setText("xyz")
    assert not editor.apply_button.isEnabled()
    editor.input.setText("C")
    editor.root_buttons.button(9).click()
    editor.quality_buttons.button(editor.qualities.index("min7")).click()
    assert editor.input.text() == "Am7"
    index = editor.bass.findText("G")
    editor.bass.setCurrentIndex(index)
    assert editor.input.text() == "Am7/G"
    editor._accept()
    assert editor.result_label == "A:min7" and editor.result_bass == "G"
    window.close()


def test_loop_marks_and_toggle(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.seek(window.project.grid()[4])
    window.set_loop_mark(0)
    window.seek(window.project.grid()[7])
    window.set_loop_mark(1)
    assert window.player.loop is not None
    assert window.song.loop_button.isChecked()
    assert window.song.grid.loop_beats == (4, 7)
    window.toggle_loop_key()
    assert window.player.loop is None and window.song.grid.loop_beats is None
    click_beat(app, window, 8)
    window.toggle_loop_key()
    assert window.song.grid.loop_beats == (8, 8)
    window.close()


def test_playback_moves_the_highlight_in_time(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    if window.player.stream is None and not window.player.open_device():
        pytest.skip(window.player.last_error)
    window.seek(0)
    window.toggle_play()
    assert wait_for(app, lambda: window.song.grid.current >= 4, 6)
    # Four beats at 120 BPM take 2 s; the highlight must follow what the clock says.
    heard = window.player.position
    assert window.project.beat_at(heard) - window.song.grid.current in (0, 1)
    window.toggle_play()
    assert not window.player.playing
    window.close()


def test_speed_is_applied(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.song.speed.step(-1)
    assert window.player.rate == 0.95
    window.close()


def test_exports_written_to_unicode_paths(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    folder = tmp_path / "Éxports 音楽"
    folder.mkdir()
    window.export_to(folder / "a.txt", "txt")
    window.export_to(folder / "a.cho", "cho")
    window.export_to(folder / "a.pdf", "pdf")
    assert "| C" in (folder / "a.txt").read_text(encoding="utf-8")
    assert "[Am]" in (folder / "a.cho").read_text(encoding="utf-8")
    pdf = (folder / "a.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    window.close()


def test_rhythm_dialog_changes_meter_and_tempo(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    dialog = dialogs.RhythmDialog(window.project, window)
    dialog.changed.connect(window._content_changed)
    dialog.per_bar.setValue(3)
    assert "3 temps" in window.song.rhythm_button.text()
    assert window.song.grid.bars_per_row in (16, 12, 8, 4, 2, 1)
    dialog._scale(2)
    assert "240 BPM" in window.song.rhythm_button.text()
    dialog._scale(1)
    assert "120 BPM" in window.song.rhythm_button.text()
    window.close()


def test_display_modes_do_not_change_the_data(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    s = window.song

    def choose(group, value):
        next(a for a in group.actions() if a.data() == value).trigger()

    choose(s.detail_actions, "simple")
    assert s.grid.symbols[12][0] == "G"
    choose(s.detail_actions, "analysis")
    assert s.grid.symbols[12][0] == "G7"
    assert s.grid.symbols[12][2].numeral == "V7"
    choose(s.accidental_actions, "flats")
    window._view(transpose=1)
    assert s.grid.symbols[4][0] == "B♭m"
    window.close()


@pytest.mark.parametrize("size", [(1100, 700), (1920, 1080), (5120, 1440)])
def test_layout_uses_the_width_of_the_window(app, wav, tmp_path, size):
    window = seeded(app, wav, tmp_path)
    window.resize(*size)
    app.processEvents()
    grid = window.song.grid
    grid.refresh()
    rightmost = max(r.right() for r in grid.cells.values())
    assert grid.cell_w >= 72
    assert rightmost <= grid.width()
    assert window.width() == size[0], "the controls must not force the window wider"
    assert grid.row_h <= 150
    if size[0] == 5120:
        # Whole song on screen, in cells large enough to read from the instrument.
        assert grid.rows[-1][1] <= grid.view_height
        assert grid.cell_w >= 100
    window.grab()
    window.close()


def test_missing_audio_keeps_the_grid_and_offers_to_locate(app, wav, tmp_path):
    a = make_analysis()
    audio = {"path": str(tmp_path / "absent.wav"), "title": "x", "duration": 8.0}
    Project(audio, a).save(tmp_path / "s.lchords")
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "s.lchords")
    app.processEvents()
    assert window.song.banner.isVisible() and "introuvable" in window.song.banner_text.text()
    assert window.song.middle.currentWidget() is window.song.scroll
    assert not window.song.play.isEnabled()
    window.close()


@pytest.mark.slow
def test_full_path_drop_analyze_play_correct_save_reopen(app, tmp_path):
    y, _ = synth.render([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:maj", 4)] * 4, 110)
    wav = synth.write_wav(tmp_path / "Chanson d'été #1.wav", y)
    window = MainWindow(muted=True)
    window.show()
    window.open_path(wav)
    assert window.job is not None
    assert window.song.middle.currentWidget() is window.song.status_page
    assert wait_for(app, lambda: window.job is None, 120), window.song.status_detail.text()
    assert window.song.middle.currentWidget() is window.song.scroll
    assert wait_for(app, lambda: window.audio_ready, 10)
    labels = [s.chord for s in window.project.segments()]
    assert {"C:maj", "A:min", "F:maj", "G:maj"} <= set(labels)
    saved = window.project_file
    assert saved.exists()
    window.apply_chord(0, 3, "E:min", None)
    window.flush()
    window.close()

    window = MainWindow(muted=True)
    window.show()
    window.open_path(wav)
    assert window.job is None, "an analyzed song must not be analyzed again"
    assert window.project.segments()[0].chord == "E:min"
    assert Path(window.project.audio["path"]) == wav
    assert [p for p, _ in library.recent()] == [saved]
    window.close()


@pytest.mark.slow
def test_cancel_leaves_the_song_playable_and_restartable(app, tmp_path):
    y, _ = synth.render([("C:maj", 4), ("F:maj", 4)] * 40, 100)
    wav = synth.write_wav(tmp_path / "long.wav", y)
    window = MainWindow(muted=True)
    window.show()
    window.open_path(wav)
    wait_for(app, lambda: window.audio_ready, 20)
    window.cancel_analysis()
    assert window.job is None
    assert window.song.status_text.text() == "Analyse annulée"
    assert window.song.play.isEnabled()
    window.close()


def test_corrupt_file_says_so_in_the_window(app, tmp_path, monkeypatch):
    alerts = []
    monkeypatch.setattr(MainWindow, "_alert", lambda self, text: alerts.append(text))
    bad = tmp_path / "abîmé.mp3"
    bad.write_bytes(b"not audio" * 100)
    window = MainWindow(muted=True)
    window.open_path(bad)
    assert alerts and "abîmé" in alerts[0]
    assert window.stack.currentWidget() is window.home
    window.close()


def test_long_title_does_not_widen_the_window(app, wav, tmp_path):
    a = make_analysis()
    audio = {"path": str(wav), "title": "très long titre " * 30, "artist": "", "duration": 8.0}
    Project(audio, a).save(tmp_path / "s.lchords")
    window = MainWindow(muted=True)
    window.resize(1100, 700)
    window.show()
    window.open_project_file(tmp_path / "s.lchords")
    app.processEvents()
    assert window.width() == 1100
    window.close()


def test_view_settings_come_back_with_the_project(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.song.capo.set_value(3)
    window.song.capo.changed.emit(3)
    window.flush()
    window.close()
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert window.song.capo.value == 3
    assert window.song.grid.symbols[0][0] == "A"
    window.close()
