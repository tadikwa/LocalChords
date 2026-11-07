"""The song's chords under the grid, and the printed chord sheet."""

# ruff: noqa: F811  (the fixtures come from test_ui)

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_ui import app, isolated, panel_at, seeded, wait_for, wav, window_rect  # noqa: F401

from localchords.ui import pdf, theme
from localchords.ui.main_window import MainWindow
from localchords.ui.songchords import chord_key


def titles(window):
    return [card.item.shown.shape.title for card in window.song.chords.cards()]


def test_every_chord_once_in_order_without_playing(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    chords = window.song.chords
    assert chords.isVisible() and chords.view == "all"
    assert not window.player.playing
    assert titles(window) == ["C", "Am", "F", "G7"]
    assert chords.count.text() == "4 accords différents"
    places = [c.item.place for c in chords.cards()]
    assert places == ["mesure 1", "mesure 2", "mesure 3", "mesure 4"]
    window.apply_chord(8, 11, "C:maj", None)  # a correction: F was a C after all
    assert titles(window) == ["C", "Am", "G7"]
    window.apply_chord(8, 11, "C:maj", "E")  # a different bass is a different position
    assert titles(window) == ["C", "Am", "C/E", "G7"]
    window.project.undo()
    window._content_changed()
    assert titles(window) == ["C", "Am", "G7"]
    window.close()


def test_cards_follow_transposition_capo_and_notation(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window._view(transpose=2)
    assert titles(window) == ["D", "Bm", "G", "A7"]
    window._view(capo=2)  # the cards show what the hands play
    assert titles(window) == ["C", "Am", "F", "G7"]
    card = window.song.chords.cards()[0]
    assert card.guitar.diagram.fingering.text == "x32010"
    assert card.item.shown.sound.title == "D"
    window._view(capo=0, transpose=0, latin=True)
    assert titles(window) == ["Do", "Lam", "Fa", "Sol7"]
    window.close()


def test_the_next_chords_move_on_with_the_playhead(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    chords = window.song.chords
    chords.set_view("next")
    window.seek(window.project.grid()[5])
    app.processEvents()
    cards = chords.cards()
    assert [c.item.shown.shape.title for c in cards][:3] == ["Am", "F", "G7"]
    assert cards[0].item.current and cards[0].item.place == "en cours"
    assert not cards[1].item.current
    window.seek(window.project.grid()[13])
    app.processEvents()
    assert titles(window) == ["G7"]
    chords.set_view("all")  # the chord playing is outlined in the full list too
    assert [c.current for c in chords.cards()] == [False, False, False, True]
    window.close()


def test_a_card_shows_its_chord_without_moving_playback(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    window.seek(window.project.grid()[1])
    app.processEvents()
    before = window.player.position
    card = window.song.chords.cards()[2]
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert window.song.panel.title.text() == "F"
    assert window.player.position == before
    assert window.song.chords.selected == chord_key(card.item.shown) and card.selected
    QTest.keyClick(card, Qt.Key.Key_Right)  # the arrows go from card to card
    assert window.song.chords.cards()[3].hasFocus()
    window.close()


def test_one_position_per_chord_shared_and_saved(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    panel = panel_at(app, window, 1)
    card = window.song.chords.cards()[0]
    assert card.guitar.diagram.fingering is panel.guitar_positions[0]
    panel.step("guitar", 1)
    assert card.guitar.diagram.fingering is panel.guitar_positions[1]
    card.guitar.next.click()  # and the other way round
    assert panel.guitar.diagram.fingering is panel.guitar_positions[2]
    window.save()
    window.close()
    window = MainWindow(muted=True)  # not seeded(): that writes the project again
    window.show()
    window.open_project_file(tmp_path / "song.lchords")
    assert wait_for(app, lambda: window.audio_ready)
    card = window.song.chords.cards()[0]
    assert card.guitar.diagram.fingering.text == panel.guitar_positions[2].text
    window.close()


def test_the_section_state_is_remembered(app, wav, tmp_path):
    window = seeded(app, wav, tmp_path)
    chords = window.song.chords
    chords.mode_buttons["both"].click()
    chords.view_buttons["next"].click()
    chords.resize_button.click()
    assert chords.state == "expanded"
    QTest.keyClick(window, Qt.Key.Key_T)
    assert chords.state == "hidden" and not chords.isVisible()
    assert not window.song.chords_button.isChecked()
    window.close()
    window = seeded(app, wav, tmp_path)
    chords = window.song.chords
    assert (chords.mode, chords.view, chords.state) == ("both", "next", "hidden")
    window.song.chords_button.click()
    assert chords.isVisible() and chords.state == "compact"  # as the panel: back to its default
    window.close()


@pytest.mark.parametrize("size", [(1000, 760), (1600, 1000), (5120, 1440)])
@pytest.mark.parametrize("state", ["compact", "expanded"])
def test_play_takes_a_real_click_with_the_section(app, wav, tmp_path, size, state):
    """The click goes through the window, as the system delivers it."""
    window = seeded(app, wav, tmp_path)
    window.song.chords.set_mode("both")
    window.song.chords.set_state(state)
    window.resize(*size)
    window.song.adapt_to_width(size[0])
    app.processEvents()
    clicks = []
    play = window.song.play
    play.clicked.connect(lambda: clicks.append(1))
    rect = window_rect(play, window)
    assert window.rect().contains(rect), "the play button stays in the window"
    QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()
    assert clicks == [1]
    window.close()


def pdf_pages(path):
    return path.read_bytes().count(b"/Type /Page\n")


def test_the_chord_sheet_prints_the_positions_chosen(app, wav, tmp_path, monkeypatch):
    window = seeded(app, wav, tmp_path)
    window._view(transpose=2, capo=2)
    panel = panel_at(app, window, 1)
    panel.step("guitar", 1)
    drawn = []
    real = pdf.GuitarDiagram.draw

    def record(self, p, r):
        drawn.append(self.fingering)
        real(self, p, r)

    monkeypatch.setattr(pdf.GuitarDiagram, "draw", record)
    background = theme.BG
    path = tmp_path / "fiche.pdf"
    window.export_sheet_to(path, "both", True)
    assert path.read_bytes().startswith(b"%PDF")
    assert pdf_pages(path) == 2  # the chords, then the grid
    assert drawn[0] is panel.guitar_positions[1]  # as the program shows it, capo shape included
    cards = window.song.chords.cards()
    shown = [cards[i].guitar.diagram.fingering.text for i in (1, 2, 3)]
    assert [f.text for f in drawn[1:]] == shown
    assert background == theme.BG, "the screen colours are back"
    window.export_sheet_to(tmp_path / "guitare.pdf", "guitar", False)
    assert pdf_pages(tmp_path / "guitare.pdf") == 1
    window.close()


@pytest.mark.parametrize("mode", ["guitar", "piano", "both"])
def test_the_sheet_never_cuts_a_card_in_two(mode):
    page_h = 1004.0  # an A4 page in sheet pixels
    places = pdf.sheet_layout(40, mode, 150.0, page_h)
    h = pdf.card_height(mode)
    for _, col, y in places:
        assert y + h <= page_h
        assert 0 <= col < pdf.COLUMNS[mode]
    assert places[0] == (0, 0, 150.0)
    pages = [p for p, _, _ in places]
    assert pages == sorted(pages) and pages[-1] >= 1
