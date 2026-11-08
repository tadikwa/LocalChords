"""The moving lyrics: the words light up only where they are timed, from the player's clock, and
nothing moves while paused or after a seek. The lyrics are made up."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
from test_lyrics_ui import with_lyrics
from test_ui import app, isolated, seeded, wait_for, wav  # noqa: F401 - fixtures

from localchords import library
from localchords import lyrics as L
from localchords.ui import lyrics_view as V
from localchords.ui.main_window import MainWindow

WORDS = "[00:01.00]<00:01.00>Lune <00:01.80>pâle, <00:02.40>été<00:03.00>\n[00:04.00]Mer grise\n"


# The words' light, without a window


def test_enhanced_lrc_keeps_the_end_of_the_last_word():
    line, plain = L.parse(WORDS)
    assert line["words"] == [[0, 1.0], [5, 1.8], [11, 2.4]]
    assert line["end"] == 3.0
    assert "end" not in plain and "words" not in plain


def test_sung_lights_each_word_from_its_start_to_the_next():
    text, words = "Lune pâle, été", [[0, 1.0], [5, 1.8], [11, 2.4]]
    assert L.sung(text, words, 0.5, 3.0) == (0.0, 0, -1.0)  # before: nothing lit
    chars, word, f = L.sung(text, words, 1.4, 3.0)
    assert word == 0 and f == pytest.approx(0.5) and chars == pytest.approx(2.0)  # "Lune" half
    chars, word, f = L.sung(text, words, 2.1, 3.0)  # "pâle," with its comma, not the space
    assert word == 5 and chars == pytest.approx(5 + 5 * 0.5)
    assert L.sung(text, words, 2.7, 3.0)[0] == pytest.approx(11 + 3 * 0.5)  # "été", to the end
    assert L.sung(text, words, 9.0, 3.0) == (14.0, 11, -1.0)  # sung through: all lit
    assert L.sung(text, words, 2.7, None)[2] == pytest.approx(0.3)  # no end: a second at most


def test_sung_makes_nothing_up_and_never_goes_back():
    assert L.sung("Mer grise", None, 5.0, None) is None
    assert L.sung("Mer grise", [], 5.0, None) is None
    # A word time edited earlier than the one before it lights with it, not before.
    chars, word, _f = L.sung("un deux trois", [[0, 1.0], [3, 2.0], [8, 1.5]], 1.7, None)
    assert word == 0 and chars < 3


def test_a_long_gap_between_two_words_does_not_stretch_the_first():
    chars, _word, f = L.sung("Oh attends", [[0, 0.0], [3, 10.0]], 3.0, None)
    assert f == -1.0 and chars == 2.0  # lit within WORD_MAX, then waits


def test_motion_default_follows_windows_reduced_animations(monkeypatch):
    monkeypatch.setattr(V, "reduces_motion", lambda: True)
    assert V.default_motion({}) == "simple"
    assert V.default_motion({"lyrics_motion": "animated"}) == "animated"
    monkeypatch.setattr(V, "reduces_motion", lambda: False)
    assert V.default_motion({}) == "animated"
    assert V.default_motion({"lyrics_motion": "bogus"}) == "animated"


def test_char_x_follows_pieces_pushed_apart_by_chords():
    runs = [(0.0, "Lune ", 0), (100.0, "pâle", 5)]
    assert V.char_x(runs, 2.5, len) == pytest.approx(2.5)
    assert V.char_x(runs, 6.0, len) == pytest.approx(101.0)
    assert V.char_x(runs, 99.0, len) == pytest.approx(104.0)


# In the window


def with_words(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    lines = L.parse(WORDS)
    window.project.set_lyrics(L.new(lines, {"kind": "file", "name": "t.lrc", "exportable": True}))
    window._content_changed()
    window.lyrics.set_motion("animated")
    window.lyrics.set_mode("lyrics")
    app.processEvents()
    return window


class Clock:
    def __init__(self, monkeypatch):
        self.t = 100.0
        monkeypatch.setattr(V.time, "monotonic", lambda: self.t)


def test_word_timing_comes_from_the_project_with_its_offset(app, wav, tmp_path):
    window = with_words(app, wav, tmp_path)
    c = window.lyrics
    row = next(r for r, x in enumerate(c.rows) if x["text"].startswith("Lune"))
    plain = next(r for r, x in enumerate(c.rows) if x["text"] == "Mer grise")
    assert c.sheet.timing[row] == ([[0, 1.0], [5, 1.8], [11, 2.4]], 3.0)
    assert plain not in c.sheet.timing  # line-timed: lit whole, no progress made up
    assert "mot à mot" not in c.page.hint.text()
    c._offset_changed(5)  # +0.5 s
    assert c.sheet.timing[row] == ([[0, 1.5], [5, 2.3], [11, 2.9]], 3.5)
    window.close()


def test_line_timed_lyrics_say_why_words_do_not_light(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.project.set_lyrics(L.new(L.parse("[00:01.00]Mer grise\n"), {"kind": "file"}))
    window._content_changed()
    window.lyrics.set_motion("animated")
    window.lyrics.set_mode("lyrics")
    assert not window.lyrics.sheet.timing
    assert "mot à mot" in window.lyrics.page.hint.text()
    window.lyrics.set_motion("simple")
    assert "mot à mot" not in window.lyrics.page.hint.text()
    window.close()


def test_a_line_comes_in_while_playing_but_a_seek_puts_it_there(app, wav, tmp_path, monkeypatch):
    window = with_words(app, wav, tmp_path)
    clock = Clock(monkeypatch)
    c, sheet = window.lyrics, window.lyrics.sheet
    window.tick_timer.stop()
    window.player.playing = True  # the clock is the positions given below
    first = next(r for r, x in enumerate(c.rows) if x["text"].startswith("Lune"))
    second = next(r for r, x in enumerate(c.rows) if x["text"] == "Mer grise")
    c.tick(2.0, 0)
    c.tick(3.9, 0)
    c.tick(4.1, 0)  # played on into the next line
    assert sheet.now_row == second and sheet._from_row == first
    assert sheet.row_alpha(first) == pytest.approx(1.0)  # still the old line, at first
    clock.t += V.TRANSITION / 2
    assert 0.66 < sheet.row_alpha(first) < 1.0 and 0.66 < sheet.row_alpha(second) < 1.0
    clock.t += V.TRANSITION
    assert sheet.row_alpha(second) == 1.0 and sheet.row_alpha(first) == V.DIM[1]
    assert sheet.row_scale(first) == V.AWAY and sheet.row_scale(second) == 1.0
    c.tick(1.2, 0)  # a seek back (or a loop's return): there at once
    assert sheet.now_row == first and sheet._from_row is None and sheet._progress() == 1.0
    window.player.playing = False
    window.close()


def test_paused_the_words_hold_and_nothing_repaints(app, wav, tmp_path, monkeypatch):
    window = with_words(app, wav, tmp_path)
    Clock(monkeypatch)
    c, sheet = window.lyrics, window.lyrics.sheet
    window.tick_timer.stop()
    window.seek(1.4)
    window.player.pause()
    c.tick(1.4, 0)
    sheet._t = sheet.player_position()
    row = sheet.now_row
    lit = sheet.row_sung(row)
    assert lit[1] == 0 and lit[2] == pytest.approx(0.5, abs=0.02)
    assert sheet._progress() == 1.0  # paused: no transition half-way
    painted = []
    monkeypatch.setattr(sheet, "update", lambda *a: painted.append(a))
    for _ in range(5):
        c.tick(1.4, 0)
    assert len(painted) <= 1  # the first frame at most, then nothing while still
    window.close()


def test_chords_are_never_scaled_and_simple_keeps_the_15_look(app, wav, tmp_path):
    window = with_words(app, wav, tmp_path)
    c, sheet = window.lyrics, window.lyrics.sheet
    c.set_mode("sheet")
    assert all(sheet.row_scale(r) == 1.0 for r in range(len(c.rows)))
    c.set_motion("simple")
    assert not sheet.moves
    sheet.grab()  # paints without the moving look
    window.close()


def test_motion_choice_is_remembered_and_in_the_lyrics_menu(app, wav, tmp_path):
    window = with_words(app, wav, tmp_path)
    c = window.lyrics
    c.motion_actions["off"].trigger()
    assert c.motion == "off" and c.sheet.motion == "off"
    assert library.load_settings()["lyrics_motion"] == "off"
    texts = [a.text() for a in c.page.more.menu().actions()]
    assert "Animation des paroles" in texts
    window.close()
    again = MainWindow(muted=True)
    assert again.lyrics.motion == "off" and again.lyrics.motion_actions["off"].isChecked()
    again.close()


def test_motion_off_scrolls_without_animation(app, wav, tmp_path):
    window = with_words(app, wav, tmp_path)
    c = window.lyrics
    c.set_motion("off")
    c.page.follow.setChecked(True)
    c._manual_until = 0.0
    c.sheet.setMinimumHeight(4000)
    row = next(r for r, x in enumerate(c.rows) if x["text"].startswith("Lune"))
    rect = c.sheet.row_rect(row)
    c.sheet.row_rect = lambda _row: rect.translated(0, 2000)
    c._follow(row)
    assert c.anim.state() != c.anim.State.Running
    assert c.page.scroll.verticalScrollBar().value() > 0
    window.close()


def test_strip_lights_the_words_compactly(app, wav, tmp_path, monkeypatch):
    window = with_words(app, wav, tmp_path)
    c = window.lyrics
    c.set_mode("strip")
    window.tick_timer.stop()
    window.seek(1.4)
    c.tick(1.4, 0)
    assert c.strip.now.startswith("Lune") and c.strip.sung[1] == 0
    c.strip.grab()
    c.set_motion("simple")
    c.tick(1.5, 0)
    assert c.strip.sung is None
    window.close()


def test_editing_still_works_with_motion(app, wav, tmp_path):
    window = with_words(app, wav, tmp_path)
    c = window.lyrics
    line = next(i for i, x in enumerate(window.project.lyrics["lines"]) if x.get("words"))
    c._line_action(line, "later")
    x = window.project.lyrics["lines"][line]
    assert x["words"][0][1] == pytest.approx(1.1) and x["end"] == pytest.approx(3.1)
    row = next(r for r, y in enumerate(c.rows) if y["line"] == line)
    assert c.sheet.timing[row][0][0][1] == pytest.approx(1.1)
    c._line_action(line, "here")  # a new start: the words' times no longer hold
    assert "words" not in window.project.lyrics["lines"][line]
    assert row not in c.sheet.timing
    window.close()
