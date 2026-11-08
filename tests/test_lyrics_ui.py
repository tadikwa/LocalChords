"""The lyrics in the window, offscreen: the sheet, following the playback, moving a chord,
syncing by hand, the exports and what the catalog's lyrics may not do. The lyrics are made up."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from test_ui import app, isolated, seeded, wait_for, wav  # noqa: F401 - fixtures

from localchords import export, transcribe
from localchords import lyrics as L
from localchords.project import Project
from localchords.ui.main_window import MainWindow
from localchords.ui.pdf import write_lyrics_sheet

LRC = """[ti:Été à Noël]
[00:00.50]Le matin se lève sur la ville
[00:04.50]Je marche seul au bord de l'eau
[Refrain]
[00:08.50]Chante encore, chante avec moi
[00:12.50]Le vent nous porte vers demain
"""


def with_lyrics(app, wav, tmp_path, source=None):
    window = seeded(app, wav, tmp_path)
    lines = L.parse(LRC)
    src = source or {"kind": "file", "name": "test.lrc", "exportable": True}
    window.project.set_lyrics(L.new(lines, src))
    window._content_changed()
    window.lyrics.set_mode("sheet")
    app.processEvents()
    return window


def press(app, widget, kind, pos, buttons=Qt.MouseButton.LeftButton):
    event = QMouseEvent(
        kind,
        QPointF(pos),
        widget.mapToGlobal(QPointF(pos)),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(widget, event)
    app.processEvents()


def test_lyrics_found_beside_the_recording_are_offered_then_used(app, wav, tmp_path):
    wav.with_suffix(".lrc").write_text(LRC, encoding="utf-8")
    window = seeded(app, wav, tmp_path)
    c = window.lyrics
    c.set_mode("sheet")
    assert window.song.middle.currentWidget() is c.page
    assert c.page.stack.currentWidget() is c.page.empty
    assert c._found and c._found[1]["kind"] == "file"
    c.use_found()
    lyr = window.project.lyrics
    assert lyr["source"]["name"] == "été à Noël.lrc"
    assert c.page.stack.currentWidget() is c.page.scroll
    assert "Importées depuis un fichier" in c.page.origin.toolTip()
    window.close()


def test_a_new_song_takes_its_side_lyrics_at_once(app, wav, tmp_path):
    wav.with_suffix(".lrc").write_text(LRC, encoding="utf-8")
    window = MainWindow(muted=True)
    project, _file, analyzed = window._project_for(wav)
    assert not analyzed
    assert project.lyrics["source"]["kind"] == "file"
    assert project.lyrics["lines"][0]["text"] == "Le matin se lève sur la ville"
    window.close()


def test_sheet_puts_chords_over_lines_and_follows_the_playback(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c = window.lyrics
    rows = [r for r in c.rows if r["kind"] == "line"]
    assert len(rows) == 4
    assert all(r["chords"] for r in rows)
    assert any(r["kind"] == "section" and r["text"] == "Refrain" for r in c.rows)
    window.seek(9.0)
    wait_for(app, lambda: c.sheet.now_row is not None, 2)
    assert c.rows[c.sheet.now_row]["text"] == "Chante encore, chante avec moi"
    assert c.sheet.now_key is not None
    # A click on a line plays from it.
    line = next(ln for ln in c.sheet.lines if ln.row == c.rows.index(rows[1]))
    pos = QPointF(c.sheet.MARGIN + 30, line.y + line.h - 4)
    press(app, c.sheet, QEvent.Type.MouseButtonPress, pos)
    press(app, c.sheet, QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.NoButton)
    assert window.player.position == pytest.approx(4.5, abs=0.05)
    window.close()


def test_dragging_a_chord_onto_a_word_moves_only_its_place(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c, sheet = window.lyrics, window.lyrics.sheet
    before = [(s.start, s.chord) for s in window.project.segments()]
    first = next(ln for ln in sheet.lines if ln.kind == "line" and ln.chords)
    x, chord = first.chords[0]
    start = QPointF(sheet.MARGIN + x + 4, first.y + 4)
    text, line_no = c.rows[first.row]["text"], c.rows[first.row]["line"]
    char = text.index("ville")
    run_x = first.runs[0][0]
    target = QPointF(
        sheet.MARGIN + run_x + sheet.f.tm.horizontalAdvance(text[:char]) + 2,
        first.y + first.chord_h + 6,
    )
    press(app, sheet, QEvent.Type.MouseButtonPress, start)
    press(app, sheet, QEvent.Type.MouseMove, QPointF(start.x() + 20, start.y() + 10))
    press(app, sheet, QEvent.Type.MouseMove, target)
    press(app, sheet, QEvent.Type.MouseButtonRelease, target, Qt.MouseButton.NoButton)
    anchors = window.project.lyrics["anchors"]
    assert anchors[chord["key"]] == {"line": line_no, "char": char}
    moved = next(x for r in c.rows for x in r["chords"] if x["key"] == chord["key"])
    assert moved["how"] == "manual" and moved["char"] == char
    assert [(s.start, s.chord) for s in window.project.segments()] == before  # same harmony
    # Saved, reopened: the place is kept; Ctrl + Z in this session takes it back.
    window.flush()
    file = window.project_file
    window.undo()
    assert not window.project.lyrics["anchors"]
    window.redo()
    window.flush()
    window.close()
    assert Project.load(file).lyrics["anchors"][chord["key"]]["char"] == char


def test_sync_mode_times_lines_with_enter(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path, {"kind": "user", "name": "", "exportable": True})
    c = window.lyrics
    lyr = window.project.lyrics
    for x in lyr["lines"]:
        x["start"] = None
    window.project.set_lyrics(lyr)
    window._content_changed()
    c.page.sync.setChecked(True)
    assert c.picked == 0
    window.seek(1.25)
    window.edit_selected()  # Enter
    window.seek(5.0)
    window.edit_selected()
    lines = window.project.lyrics["lines"]
    assert lines[0]["start"] == pytest.approx(1.25, abs=0.02)
    assert lines[1]["start"] == pytest.approx(5.0, abs=0.02)
    assert c.picked == 3  # the section heading is skipped
    window.undo()
    assert window.project.lyrics["lines"][1]["start"] is None
    window.close()


def test_offset_and_line_corrections_keep_the_original(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c = window.lyrics
    c.page.offset.step(3)
    assert window.project.lyrics["offset"] == pytest.approx(0.3)
    c._line_action(0, "later")
    lyr = window.project.lyrics
    assert lyr["lines"][0]["start"] == pytest.approx(0.6)
    assert lyr["original"][0]["start"] == pytest.approx(0.5)
    assert "corrigées par vous" in c.page.origin.toolTip()
    c.revert_original()
    lyr = window.project.lyrics
    assert lyr["lines"] == lyr["original"] and lyr["offset"] == 0
    window.close()


def test_catalog_lyrics_show_but_never_export(app, wav, tmp_path, monkeypatch):
    alerts = []
    monkeypatch.setattr(MainWindow, "_alert", lambda self, text: alerts.append(text))
    source = {"kind": "catalog", "name": "LRCLIB", "exportable": False, "artist": "X"}
    window = with_lyrics(app, wav, tmp_path, source)
    c = window.lyrics
    assert c.page.badge.text() == "Non exportables" and c.page.badge.isVisibleTo(c.page)
    assert all(not a.isEnabled() for a in c.exports)
    assert c._save_path("x", ".lrc", "LRC (*.lrc)") is None  # refused even if called
    assert len(alerts) == 1 and "pas exportables" in alerts[0]
    window.close()


def test_transcription_lands_in_its_own_project_and_is_a_draft(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c = window.lyrics
    task = transcribe.Task(done=True, result={"lines": [{"text": "Bonjour", "start": 1.0}],
                                              "language": "fr"})  # fmt: skip
    c.task, c.task_target = task, (window.project, window.project_file)
    c.task_info = {"model": "small-q5_1", "language": "auto", "began": 0.0}
    c._poll()
    lyr = window.project.lyrics
    assert lyr["source"]["kind"] == "transcription" and lyr["source"]["exportable"]
    assert lyr["previous"]["source"]["kind"] == "file"  # the lyrics before are one click away
    assert c.page.badge.text() == "Brouillon"
    c.revert_previous()
    assert window.project.lyrics["source"]["kind"] == "file"
    window.close()


def test_modes_strip_and_k(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c, s = window.lyrics, window.song
    c.set_mode("strip")
    assert s.middle.currentWidget() is s.scroll and c.strip.isVisibleTo(s)
    window.seek(4.7)
    wait_for(app, lambda: c.strip.now != "", 2)
    assert c.strip.now == "Je marche seul au bord de l'eau"
    c.set_mode("grid")
    assert not c.strip.isVisibleTo(s)
    c.toggle_mode()
    assert c.mode == "strip"  # K goes back to the last lyrics mode
    c.set_mode("lyrics")
    assert s.middle.currentWidget() is c.page and not c.sheet.chords_on
    window.close()


def test_small_window_keeps_the_lyrics_usable(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    window.resize(560, 700)
    app.processEvents()
    p = window.lyrics.page
    p.adapt_to_width(560)
    assert not p.offset.isVisibleTo(p) and p.more.isVisibleTo(p)
    assert window.lyrics.sheet.lines  # laid out at that width
    window.close()


def test_exports_text_and_pdf(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    project = window.project
    text = export.to_text_with_lyrics(project)
    assert "Le matin se lève sur la ville" in text and "[Refrain]" in text
    assert "Paroles : Importées depuis un fichier (test.lrc)" in text
    lrc = L.to_lrc(project.lyrics, "Été à Noël", "")
    assert "[00:08.50]Chante encore" in lrc
    items, positions = window.song.chords.all_items, window.song.positions
    for options in (
        {},
        {"diagrams": "both", "landscape": True, "size": "large", "diagrams_first": False},
        {"diagrams": "none", "details": False, "size": "small"},
    ):
        path = tmp_path / f"sheet-{len(options)}.pdf"
        pages = write_lyrics_sheet(project, path, options, items, positions)
        assert pages >= 1 and path.read_bytes().startswith(b"%PDF")
    window.close()


def test_long_lines_and_many_chords_wrap_without_loss(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    lyr = window.project.lyrics
    long = " ".join(["Une phrase qui ne finit jamais vraiment"] * 12)
    lyr["lines"] = [{"text": long, "start": 0.2}] + [
        {"text": f"Ligne {i} du couplet", "start": 1 + i * 0.4} for i in range(60)
    ]
    window.project.set_lyrics(lyr)
    window._content_changed()
    sheet = window.lyrics.sheet
    row = next(i for i, r in enumerate(window.lyrics.rows) if r["line"] == 0)
    first = [ln for ln in sheet.lines if ln.row == row]
    assert len(first) > 1  # wrapped
    shown = "".join(piece for ln in first for _x, piece, _c in ln.runs)
    assert shown.replace(" ", "") == long.replace(" ", "")  # every letter is there
    width = sheet.width() - 2 * sheet.MARGIN
    assert all(x + sheet.f.chord_w(c["label"]) <= width + 1 for ln in sheet.lines
               for x, c in ln.chords)  # fmt: skip
    pages = write_lyrics_sheet(window.project, tmp_path / "long.pdf", {}, [], window.song.positions)
    assert pages >= 2
    window.close()


def test_project_without_lyrics_opens_as_before(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    assert window.project.lyrics is None
    assert window.song.middle.currentWidget() is window.song.scroll
    window.flush()
    window.close()


def test_a_copy_of_the_project_leaves_catalog_lyrics_out(app, wav, tmp_path, monkeypatch):
    import json

    from localchords.ui import main_window as mw

    source = {"kind": "catalog", "name": "LRCLIB", "exportable": False}
    window = with_lyrics(app, wav, tmp_path, source)
    copy = tmp_path / "copie.lchords"
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a, **k: (str(copy), ""))
    window.save_as()
    d = json.loads(copy.read_text(encoding="utf-8"))
    assert "lyrics" not in d and d["version"] == 1
    assert window.project.lyrics["source"]["kind"] == "catalog"  # still shown here
    window.close()


def test_a_project_that_cannot_be_read_is_kept_aside(app, wav, tmp_path):
    from localchords import audio, library

    saved = library.project_path(audio.fingerprint(wav))
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text('{"format": "localchords", "version": 99}', encoding="utf-8")
    window = MainWindow(muted=True)
    project, file, known = window._project_for(wav)
    assert not known and file == saved and not saved.exists()
    aside = list(saved.parent.glob(f"{saved.stem}-*.illisible"))
    assert len(aside) == 1 and '"version": 99' in aside[0].read_text(encoding="utf-8")
    window.close()


def test_a_transcription_reaches_its_song_reopened_meanwhile(app, wav, tmp_path):
    window = with_lyrics(app, wav, tmp_path)
    c = window.lyrics
    task = transcribe.Task(done=True, result={"lines": [{"text": "Bonjour", "start": 1.0}],
                                              "language": "fr"})  # fmt: skip
    earlier = Project.load(window.project_file)  # the same song, as it was when it began
    c.task, c.task_target = task, (earlier, window.project_file)
    c.task_info = {"model": "small-q5_1", "language": "auto", "began": 0.0}
    c._poll()
    assert window.project.lyrics["source"]["kind"] == "transcription"
    window.close()


def test_catalog_lyrics_cannot_be_copied_out_of_the_editor(app):
    from localchords.ui.lyrics_dialogs import LyricsEditor

    for copyable, expected in ((True, "Une ligne"), (False, "")):
        dialog = LyricsEditor("Une ligne", copyable=copyable)
        dialog.edit.selectAll()
        assert dialog.edit.createMimeDataFromSelection().text() == expected
        dialog.close()
