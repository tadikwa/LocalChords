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
from PySide6.QtWidgets import QPushButton
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
    assert grid.cell_w >= 56
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


def test_recent_songs_stay_within_the_window_and_say_when_audio_is_gone(app, wav, tmp_path):
    long = {"path": str(wav), "title": "très long titre " * 30, "duration": 8.0}
    gone = {"path": str(tmp_path / "parti.wav"), "title": "Parti", "duration": 8.0}
    Project(long, make_analysis()).save(library.project_path("a" * 16))
    Project(gone, make_analysis()).save(library.project_path("b" * 16))
    window = MainWindow(muted=True)
    window.resize(1100, 700)
    window.show()
    app.processEvents()
    assert window.width() == 1100
    texts = {b.text(): b.toolTip() for b in window.home.findChildren(QPushButton, "recent")}
    assert any("Parti" in t and "audio introuvable" in t for t in texts)
    shortened = next(t for t in texts if t.startswith("très"))
    assert "…" in shortened and "très long titre " * 30 in texts[shortened]
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


def test_dropping_a_file_opens_it(app, wav, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    a = make_analysis()
    audio = {"path": str(wav), "title": "x", "duration": 8.0}
    Project(audio, a).save(tmp_path / "déposé.lchords")
    window = MainWindow(muted=True)
    window.show()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "déposé.lchords"))])
    actions = Qt.DropAction.CopyAction
    button = Qt.MouseButton.LeftButton
    keys = Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(window.rect().center(), actions, mime, button, keys)
    window.dragEnterEvent(enter)
    assert enter.isAccepted() and window.drop_hint.isVisible()
    window.dropEvent(QDropEvent(QPointF(10, 10), actions, mime, button, keys))
    assert not window.drop_hint.isVisible()
    assert window.stack.currentWidget() is window.song
    window.close()


def test_held_chord_is_named_again_at_each_bar(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.apply_chord(0, 11, "C:maj", None)
    assert window.song.grid.continued[4] == "C"
    assert window.song.grid.continued[8] == "C"
    window.close()


def test_import_link_refuses_nonsense(app, monkeypatch):
    alerts = []
    monkeypatch.setattr(MainWindow, "_alert", lambda self, text: alerts.append(text))
    window = MainWindow(muted=True)
    window.import_link("pas une adresse")
    window.import_link("file:///C:/Windows/system.ini")
    assert len(alerts) == 2 and window.download_job is None
    window.close()


def test_audio_follows_transposition_only_when_asked(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.song.transpose.step(12)
    assert window.player.pitch == 1.0
    assert "désactivé" in window.song.audio_button.toolTip()
    window.song.audio_button.click()
    assert window.player.pitch == pytest.approx(2.0)  # an octave: ±12 is reachable
    assert window.song.audio_button.text().strip() == "Son transposé"
    window.song.transpose.step(-24)
    assert window.player.pitch == pytest.approx(0.5)
    window.song.audio_button.click()
    assert window.player.pitch == 1.0
    window.close()


def test_progressions_dialog_seeks(app, wav, tmp_path):
    from localchords.ui.main_window import ProgressionsDialog

    a = make_analysis(chords=("C:maj", "A:min", "F:maj", "G:7") * 3)
    audio = {"path": str(wav), "title": "x", "duration": 24.0}
    p = Project(audio, a)
    seen = []
    dialog = ProgressionsDialog(p, seen.append)
    buttons = dialog.findChildren(
        type(dialog.findChild(__import__("PySide6.QtWidgets").QtWidgets.QPushButton))
    )
    assert buttons and "× 3" in buttons[0].text()
    buttons[0].click()
    assert seen == [0.0]


@pytest.mark.slow
def test_batch_analyzes_several_files_in_the_background(app, tmp_path):
    y, _ = synth.render([("C:maj", 4), ("F:maj", 4), ("G:maj", 4), ("C:maj", 4)] * 3, 100)
    z, _ = synth.render([("D:min", 4), ("G:maj", 4), ("C:maj", 4), ("A:min", 4)] * 3, 120)
    files = [synth.write_wav(tmp_path / "un.wav", y), synth.write_wav(tmp_path / "deux.wav", z)]
    bad = tmp_path / "abîmé.mp3"
    bad.write_bytes(b"not audio" * 100)
    window = MainWindow(muted=True)
    window.show()
    window.open_paths([files[0], bad, files[1]])
    assert window.stack.currentWidget() is window.home
    assert wait_for(app, lambda: not window.batch_timer.isActive(), 240)
    assert "terminée" in window.home.batch_text.text() and "abîmé" in window.home.batch_text.text()
    assert len(library.recent()) == 2
    window.open_path(files[1])
    assert window.job is None and window.project.segments()
    window.close()


@pytest.mark.slow
def test_compare_engines_keeps_the_current_grid_on_request(app, tmp_path, monkeypatch):
    y, _ = synth.render([("C:maj", 4), ("F:maj", 4), ("G:maj", 4), ("C:maj", 4)] * 3, 100)
    wav = synth.write_wav(tmp_path / "c.wav", y)
    window = MainWindow(muted=True)
    window.show()
    window.open_path(wav)
    assert wait_for(app, lambda: window.job is None, 120)
    before = window.project.analysis
    seen = []
    monkeypatch.setattr(window, "_keep_compared", lambda e, a: seen.append(e) or False)
    window.compare_with("dsp")
    assert wait_for(app, lambda: window.job is None, 120)
    assert seen == ["dsp"] and window.project.analysis is before
    window.close()


def test_flat_key_from_the_menu_does_not_break_the_window(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window._set_key("Db:maj")
    assert "D♭ majeur" in window.song.key_button.text()
    window.flush()
    window.close()
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert "D♭ majeur" in window.song.key_button.text()
    window.close()


def test_selection_is_dropped_when_the_grid_shrinks(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    last = len(window.project.grid()) - 1
    window.song.grid.set_selection(last, last)
    window.project.set_grid(scale=0.5)
    window._content_changed()
    assert window.song.grid.selection is None
    window.toggle_loop_key()
    window.close()


def test_a_failed_comparison_does_not_disturb_the_next_analysis(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.compare_with("dsp")
    assert window.compare_engine == "dsp"
    window.cancel_analysis()
    assert window.compare_engine is None
    window.close()


def test_a_link_url_does_not_stick_to_the_next_file(app, wav, tmp_path):
    window = MainWindow(muted=True)
    window.pending_source_url = "https://example.org/x"
    project, _, known = window._project_for(wav)
    assert project.audio["source_url"] == "https://example.org/x" and not known
    assert window._project_for(wav)[0].audio["source_url"] is None
    window.close()


def test_editor_uses_latin_names_when_asked(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window._view(latin=True)
    editor = dialogs.ChordEditor(window.project, 0, 0, window)
    assert editor.input.text() == "Do"
    editor.root_buttons.button(5).click()
    assert editor.input.text() == "Fa"
    editor.quality_buttons.button(editor.qualities.index("maj(9)")).click()
    assert editor.input.text() == "Faadd9"
    assert editor.apply_button.isEnabled()
    editor._accept()
    assert editor.result_label == "F:maj(9)"
    window.close()


@pytest.mark.parametrize("width", [1000, 1120, 1240, 2560])
def test_transport_controls_fit_whatever_the_window_manager_imposes(app, wav, tmp_path, width):
    a = make_analysis(chords=("C:maj", "A:min", "F:maj", "G:7") * 12)
    audio = {"path": str(wav), "title": "Long", "duration": a["segments"][-1]["end_time"]}
    Project(audio, a).save(tmp_path / "long.lchords")
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "long.lchords")
    window.resize(width, 800)
    app.processEvents()
    s = window.song
    s.adapt_to_width(width)
    app.processEvents()
    needed = s.play.parent().minimumSizeHint().width()
    assert needed <= width, f"the transport needs {needed} px"
    assert s.grid.bars_per_row >= 4, "a narrow window still reads four bars to a line"
    window.close()


# Diagrams ----------------------------------------------------------------------------------------
def panel_at(app, window, beat):
    window.seek(window.project.grid()[beat])
    app.processEvents()
    return window.song.panel


def test_diagrams_follow_the_chord_played(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = panel_at(app, window, 5)
    assert panel.isVisible() and window.song.diagrams_button.isVisible()
    assert panel.title.text() == "Am" and panel.status.text() == "Suit la lecture"
    assert panel.guitar_positions[0].text == "x02210"
    panel = panel_at(app, window, 13)
    assert panel.title.text() == "G7" and panel.guitar_positions[0].text == "320001"
    assert panel.guitar.count.text().startswith("1 / ")
    panel.step("guitar", 1)
    assert panel.guitar.count.text().startswith("2 / ")
    assert panel.guitar.diagram.fingering is panel.guitar_positions[1]
    window.close()


def test_a_click_pins_the_diagrams_and_a_double_click_still_edits(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    edits = []
    window.song.grid.editRequested.disconnect()
    window.song.grid.editRequested.connect(lambda *span: edits.append(span))
    panel = window.song.panel
    click_beat(app, window, 9)
    assert panel.title.text() == "F" and panel.follow.isVisible()
    assert panel.status.text() == "Épinglé : mesure 3"
    window.seek(window.project.grid()[1])  # playback moves on, the pin stays
    app.processEvents()
    assert panel.title.text() == "F"
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.pinned_at is None and not panel.follow.isVisible()
    assert panel.title.text() == "C"
    click_beat(app, window, 9)  # a click also moves the playhead there
    window.seek(window.project.grid()[5])
    panel.follow.click()
    assert panel.title.text() == "Am"
    click_beat(app, window, 13, double=True)
    assert edits, "a double click opens the chord editor"
    window.close()


def test_starting_playback_follows_again(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    if window.player.stream is None and not window.player.open_device():
        pytest.skip(window.player.last_error)
    click_beat(app, window, 9)
    window.seek(0)
    window.toggle_play()
    assert window.pinned_at is None
    assert wait_for(app, lambda: window.song.panel.title.text() == "Am", 6)
    window.toggle_play()
    window.close()


def test_diagram_mode_and_size_are_remembered(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = window.song.panel
    panel.mode_buttons["both"].click()
    assert panel.guitar.isVisible() and panel.piano.isVisible()
    panel.resize_button.click()
    assert panel.state == "reduced" and not panel.modes.isVisible()
    window.close()
    window = seeded(app, wav, tmp_path)
    panel = window.song.panel
    assert (panel.mode, panel.state) == ("both", "reduced")
    QTest.keyClick(window, Qt.Key.Key_D)
    assert panel.state == "hidden" and not panel.isVisible()
    assert not window.song.diagrams_button.isChecked()
    window.close()
    window = seeded(app, wav, tmp_path)
    assert not window.song.panel.isVisible()
    window.song.diagrams_button.click()
    assert window.song.panel.isVisible() and window.song.panel.state == "full"
    window.close()


def window_rect(widget, window):
    return widget.rect().translated(widget.mapTo(window, widget.rect().topLeft()))


@pytest.mark.parametrize(
    ("size", "side"),
    [((1000, 760), False), ((1920, 1080), True), ((3440, 1440), True), ((5120, 1440), True)],
)
def test_the_panel_fits_beside_or_under_the_grid(app, wav, tmp_path, size, side):
    window = seeded(app, wav, tmp_path)
    window.song.panel.set_mode("both")
    window.resize(*size)
    app.processEvents()
    s = window.song
    s.adapt_to_width(size[0])  # as a tiling window manager imposes it
    app.processEvents()
    assert s.panel.side is side
    panel = window_rect(s.panel, window)
    assert not window_rect(s.scroll, window).intersects(panel)
    assert panel.right() <= window.width() and panel.bottom() <= window.height()
    assert s.grid.cell_w >= 56
    for diagram in (s.panel.guitar.diagram, s.panel.piano.diagram):
        assert diagram.width() >= 120 and diagram.height() >= 90
    window.grab()
    window.close()


def test_diagrams_follow_transposition_capo_and_notation(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = panel_at(app, window, 1)
    window._view(transpose=2)  # C heard as D
    assert panel.title.text() == "D" and panel.guitar_positions[0].text == "xx0232"
    window._view(capo=2)  # D with a capo on 2: a C shape
    assert panel.title.text() == "C" and panel.guitar_positions[0].text == "x32010"
    assert "son réel D" in panel.capo_note.text() and panel.capo_note.isVisible()
    assert panel.shown.sound.title == "D" and panel.piano_voicings[0].notes[0] % 12 == 2
    assert panel.piano.kind.text().startswith("son réel D")
    window._view(latin=True)
    assert panel.title.text() == "Do"
    window._view(latin=False, capo=0, transpose=1, accidentals="flats")
    panel = panel_at(app, window, 5)
    assert panel.title.text() == "B♭m"
    window._view(accidentals="sharps")
    assert panel.title.text() == "A♯m"
    window.close()


def test_diagrams_follow_corrections_and_come_back_with_the_project(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.apply_chord(0, 3, "B:min", None)
    panel = panel_at(app, window, 1)
    assert panel.title.text() == "Bm" and panel.guitar_positions[0].text == "x24432"
    window.apply_chord(4, 7, "D:maj", "F#")
    panel = panel_at(app, window, 5)
    assert panel.title.text() == "D/F♯" and panel.guitar_positions[0].text == "2x0232"
    window.song.capo.set_value(2)
    window.song.capo.changed.emit(2)
    assert panel.title.text() == "C/E"
    window.flush()
    window.close()
    window = MainWindow(muted=True)
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert wait_for(app, lambda: window.audio_ready)
    panel = panel_at(app, window, 5)
    assert panel.title.text() == "C/E" and panel.guitar_positions[0].text == "032010"
    window.close()


def test_no_chord_and_unplayable_chords_say_so(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.apply_chord(4, 7, "N", None)
    panel = panel_at(app, window, 5)
    assert panel.title.text() == "N.C." and panel.shown is None
    assert "Pas d'accord ici" in panel.guitar.diagram.message
    # B minor over C sharp with a capo on 11: no verified position, and the panel says why.
    window.apply_chord(0, 3, "B:min", "C#")
    window._view(capo=11)
    panel = panel_at(app, window, 1)
    assert panel.guitar_positions == () and panel.guitar.diagram.fingering is None
    assert "Aucune position vérifiée" in panel.guitar.diagram.message
    assert panel.guitar.kind.text() == "Aucune position"
    assert panel.piano_voicings, "the piano still plays it"
    window.close()


def test_following_the_playhead_stays_fast(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.song.panel.set_mode("both")
    window.resize(1920, 1080)
    app.processEvents()
    beats = len(window.project.grid())
    start = time.perf_counter()
    for i in range(200):
        window._update_now((i * 3) % beats)
        window.song.panel.guitar.diagram.grab()
        window.song.panel.piano.diagram.grab()
    per_beat = (time.perf_counter() - start) / 200
    assert per_beat < 0.02, f"{per_beat * 1000:.1f} ms per beat"
    window.close()


def test_a_pin_holds_through_a_grid_edit_and_follows_the_arrows(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = window.song.panel
    click_beat(app, window, 9)
    assert panel.title.text() == "F"
    window.project.set_grid(scale=2)  # the ×2 button: every beat is renumbered
    window._content_changed()
    assert panel.title.text() == "F" and panel.follow.isVisible()
    window.project.set_grid(scale=1)
    window._content_changed()
    window.step_beat(4)  # a bar later, the pin moves with the selection
    assert panel.title.text() == "G7" and panel.follow.isVisible()
    window.step_bar(-2)
    assert panel.title.text() == "Am" and panel.status.text() == "Épinglé : mesure 2"
    window.close()


def test_the_keyboard_pins_and_unpins(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = panel_at(app, window, 5)
    QTest.keyClick(window, Qt.Key.Key_D, Qt.KeyboardModifier.ShiftModifier)
    assert window.pinned_at is not None and panel.title.text() == "Am"
    assert panel.status.text().startswith("Épinglé")
    QTest.keyClick(window, Qt.Key.Key_D, Qt.KeyboardModifier.ShiftModifier)
    assert window.pinned_at is None and panel.status.text() == "Suit la lecture"
    window.close()


def test_with_a_capo_the_title_names_what_is_on_show(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = panel_at(app, window, 1)
    window._view(capo=2)  # C heard, a B♭ shape on the guitar
    assert panel.title.text() == "B♭"
    panel.set_mode("piano")
    assert panel.title.text() == "C" and "forme de B♭" in panel.capo_note.text()
    panel.set_mode("both")
    panel.set_state("reduced")
    assert panel.capo_note.isVisible() and panel.capo_note.text() == "Capo 2 · son réel C"
    window._view(capo=0)
    assert not panel.capo_note.isVisible()
    panel.set_state("full")
    window.close()


def test_the_no_position_message_counts_the_frets_left_above_the_capo(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.apply_chord(0, 3, "B:min", "C#")
    window._view(capo=11)
    panel = panel_at(app, window, 1)
    message = panel.guitar.diagram.message
    assert "dans les 4 cases au-dessus du capo" in message and message.count(" avec ") == 0
    assert "Afficher les basses" in message and "capo" in message
    window.close()
