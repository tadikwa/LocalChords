"""The invitation to get lyrics and the suggestion from LRCLIB, in the window, offscreen. LRCLIB
is faked: these tests never reach the network. Names and lyrics are made up."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
from test_core import analysis as make_analysis
from test_ui import app, isolated, wait_for, wav  # noqa: F401 - fixtures

from localchords import library, lyrics_online
from localchords import lyrics as L
from localchords.project import Project
from localchords.ui.main_window import MainWindow

KNOWN = {"title": "Chanson inventée", "artist": "Personne", "album": ""}
FOUND = {
    "id": 42,
    "trackName": "Chanson inventée",
    "artistName": "Personne",
    "albumName": "",
    "duration": 24.0,
    "instrumental": False,
    "plainLyrics": "Une ligne inventée\nUne autre ligne",
    "syncedLyrics": "[00:01.00]Une ligne inventée\n[00:05.00]Une autre ligne",
}


@pytest.fixture
def calls(monkeypatch):
    """Every request LRCLIB would have received; answers FOUND to any search."""
    seen = []

    def get(path, params, opener=None):
        seen.append((path, params))
        return [FOUND] if path == "search" else None

    monkeypatch.setattr(lyrics_online, "_get", get)
    return seen


def write_song(tmp_path, names=None, how="tags", lyrics=None, name="song", fingerprint="f"):
    a = make_analysis(beats_each=4, bpm=120.0)
    a["segments"][-1]["end_time"] = 24.0
    names = KNOWN if names is None else names
    audio = {
        "path": str(tmp_path / "été à Noël.wav"),
        **names,
        "duration": 24.0,
        "fingerprint": fingerprint * 32,
        "identity": {"how": how, "sure": how == "tags"},
    }
    Project(audio, a, lyrics=lyrics).save(tmp_path / f"{name}.lchords")
    return tmp_path / f"{name}.lchords"


def show(app, file, mode="strip"):
    window = MainWindow(muted=True)
    window.show()
    window.lyrics.set_mode(mode)
    window.open_project_file(file)
    assert wait_for(app, lambda: window.audio_ready)
    return window


def open_song(app, wav, tmp_path, auto=None, mode="strip", **song):
    if auto is not None:
        library.save_settings({**library.load_settings(), "lyrics_auto": auto})
    return show(app, write_song(tmp_path, **song), mode)


def prompt_text(window, full=False):
    p = window.lyrics.page.prompt if full else window.lyrics.prompt
    return p.text.toolTip() or p.text.text() if p.isVisible() else None


def click(app, window, label, full=False):
    p = window.lyrics.page.prompt if full else window.lyrics.prompt
    button = next(b for b in p.buttons if b.text() == label)
    button.click()
    app.processEvents()


def test_grid_and_lyrics_invites_without_hiding_the_grid(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path, auto=False)
    c, s = window.lyrics, window.song
    assert c.prompt.isVisible() and s.scroll.isVisible()
    assert "Aucune parole disponible" in prompt_text(window)
    assert [b.text() for b in c.prompt.buttons] == [
        "Rechercher les paroles",
        "Transcrire avec l'IA",
        "Importer",
    ]
    assert c.prompt.height() <= 40
    assert not c.strip.isVisible()
    window.project.set_lyrics(L.new(L.parse("[00:01.00]Une ligne"), {"kind": "user"}))
    window._content_changed()
    app.processEvents()
    assert not c.prompt.isVisible() and c.strip.isVisible()
    window.lyrics.set_mode("grid")
    assert not c.prompt.isVisible()
    assert calls == []  # disabled: nothing sent
    window.close()


def test_the_invitation_hides_for_this_song_only(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path, auto=False)
    window.lyrics.prompt.close.click()
    app.processEvents()
    assert not window.lyrics.prompt.isVisible()
    window.flush()
    window.close()
    again = show(app, tmp_path / "song.lchords")
    assert not again.lyrics.prompt.isVisible()
    again.close()
    other = show(app, write_song(tmp_path, name="other", fingerprint="e"))
    assert other.lyrics.prompt.isVisible()
    other.close()


def test_first_use_asks_before_anything_is_sent(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path)
    assert "Rechercher automatiquement" in prompt_text(window)
    assert "jamais l'audio" in prompt_text(window)
    app.processEvents()
    assert calls == []
    click(app, window, "Autoriser")
    assert library.load_settings()["lyrics_auto"] is True
    assert window.auto_lyrics_action.isChecked()
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 10)
    sent = {k for _path, params in calls for k, v in params.items() if v}
    assert sent <= {"track_name", "artist_name", "album_name", "duration", "q"}
    assert prompt_text(window).startswith("Paroles trouvées : Personne – Chanson inventée")
    assert "synchronisées" in prompt_text(window)
    click(app, window, "Utiliser")
    lyr = window.project.lyrics
    assert lyr["source"]["kind"] == "catalog" and not L.exportable(lyr)
    assert lyr["lines"][0]["start"] == 1.0 and not window.lyrics.prompt.isVisible()
    window.close()


def test_refusing_is_remembered_and_sends_nothing(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path)
    click(app, window, "Non merci")
    assert library.load_settings()["lyrics_auto"] is False
    assert "Aucune parole disponible" in prompt_text(window)
    window.close()
    again = open_song(app, wav, tmp_path)
    app.processEvents()
    assert calls == [] and "Rechercher automatiquement" not in prompt_text(again)
    again.close()


def test_the_menu_turns_it_off_and_on(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path, auto=True)
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 10)
    window.auto_lyrics_action.setChecked(False)
    assert library.load_settings()["lyrics_auto"] is False
    window.close()
    calls.clear()
    again = open_song(app, wav, tmp_path)
    app.processEvents()
    assert calls == [] and again.lyrics.lookup is None
    again.close()


def test_lyrics_already_there_are_never_looked_up_nor_replaced(app, wav, tmp_path, calls):
    mine = L.new(L.parse("Mes propres paroles"), {"kind": "user", "exportable": True})
    window = open_song(app, wav, tmp_path, auto=True, lyrics=mine)
    app.processEvents()
    assert calls == [] and window.lyrics.lookup is None
    window.lyrics.suggestion = {"verdict": "sure", "candidates": [FOUND], "synced": True}
    window.lyrics.use_suggestion()
    assert window.project.lyrics["lines"][0]["text"] == "Mes propres paroles"
    window.close()


def test_an_unknown_song_gets_no_one_elses_lyrics_and_no_transcription_on_its_own(
    app, wav, tmp_path, calls
):
    names = {"title": "yue output 03", "artist": "", "album": ""}
    window = open_song(app, wav, tmp_path, auto=True, names=names, how="filename")
    app.processEvents()
    assert calls == [] and window.lyrics.task is None
    assert "morceau non identifié" in prompt_text(window)
    assert "Transcrire avec l'IA" in [b.text() for b in window.lyrics.prompt.buttons]
    window.close()


def test_nothing_reliable_found_offers_the_transcription_first(app, wav, tmp_path, monkeypatch):
    monkeypatch.setattr(lyrics_online, "_get", lambda *a, **k: [])
    window = open_song(app, wav, tmp_path, auto=True)
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 10)
    assert window.lyrics.suggestion["verdict"] == "none"
    assert "Aucune parole fiable" in prompt_text(window)
    assert window.lyrics.prompt.buttons[0].text() == "Transcrire avec l'IA"
    assert window.lyrics.task is None
    window.close()


def test_several_versions_are_left_to_the_user(app, wav, tmp_path, monkeypatch):
    other = {**FOUND, "id": 43, "plainLyrics": "Tout autre texte", "syncedLyrics": None}
    monkeypatch.setattr(lyrics_online, "_get", lambda p, *a, **k: [FOUND, other])
    window = open_song(app, wav, tmp_path, auto=True, mode="lyrics")
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 10)
    assert window.lyrics.suggestion["verdict"] == "choose"
    assert "à vous de choisir" in prompt_text(window, full=True)
    first = window.lyrics.page.empty_buttons.itemAt(0).widget()
    assert first.text() == "Choisir parmi les versions trouvées…"
    assert window.project.lyrics is None  # nothing taken without asking
    window.close()


def test_the_lookup_never_holds_the_window(app, wav, tmp_path, monkeypatch):
    def slow(path, params, opener=None):
        time.sleep(1.5)
        return [FOUND] if path == "search" else None

    monkeypatch.setattr(lyrics_online, "_get", slow)
    library.save_settings({"lyrics_auto": True})
    window = open_song(app, wav, tmp_path)
    began = time.perf_counter()
    window._content_changed()
    app.processEvents()
    assert time.perf_counter() - began < 0.5
    assert "Recherche des paroles" in prompt_text(window)
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 15)
    window.close()


def test_a_late_answer_does_not_reach_another_song(app, wav, tmp_path, monkeypatch):
    def slow(path, params, opener=None):
        time.sleep(0.8)
        return [FOUND] if path == "search" else None

    monkeypatch.setattr(lyrics_online, "_get", slow)
    library.save_settings({"lyrics_auto": True})
    first = write_song(tmp_path)
    window = show(app, first)
    assert window.lyrics.lookup is not None
    unknown = {"title": "Autre chose", "artist": "", "album": ""}
    window.open_project_file(write_song(tmp_path, names=unknown, name="b", fingerprint="e"))
    assert wait_for(app, lambda: window.audio_ready and window.lyrics.lookup is None, 10)
    assert window.lyrics.suggestion is None and window.project.lyrics is None
    assert window.project.audio["title"] == "Autre chose"
    window.open_project_file(first)  # back: its dropped answer is asked for again
    assert wait_for(app, lambda: window.lyrics.suggestion is not None, 10)
    window.close()


def test_turning_the_search_off_drops_the_answer_under_way(app, wav, tmp_path, monkeypatch):
    def slow(path, params, opener=None):
        time.sleep(0.5)
        return [FOUND] if path == "search" else None

    monkeypatch.setattr(lyrics_online, "_get", slow)
    library.save_settings({"lyrics_auto": True})
    window = show(app, write_song(tmp_path))
    assert window.lyrics.lookup is not None
    window.auto_lyrics_action.setChecked(False)
    assert wait_for(app, lambda: window.lyrics.lookup is None, 10)
    assert window.lyrics.suggestion is None
    window.close()


def test_names_corrected_by_the_user_are_kept(app, wav, tmp_path, calls):
    window = MainWindow(muted=True)
    window.pending_info = {"title": "Personne - Chanson inventee (Official Video)", "id": "x1"}
    project, saved, known = window._project_for(wav)
    assert not known and project.audio["artist"] == "Personne"
    assert project.audio["identity"]["how"] == "title" and not project.audio["identity"]["sure"]
    assert "x1" not in project.audio["title"] and "Official" not in project.audio["title"]
    project.audio["title"], project.audio["identity"]["how"] = "Chanson inventée", "user"
    project.save(saved)
    again, _saved, known = window._project_for(wav)
    assert known and again.audio["title"] == "Chanson inventée"
    assert again.audio["identity"]["how"] == "user"
    window.close()


def test_a_tagged_file_names_its_song(app, tmp_path, calls):
    import av
    import numpy as np

    path = tmp_path / "piste 01.m4a"
    with av.open(str(path), "w") as c:
        c.metadata["title"] = "Chanson inventée"
        c.metadata["artist"] = "Personne"
        stream = c.add_stream("aac", rate=44100)
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, 44100), dtype=np.float32), format="fltp", layout="mono"
        )
        frame.rate = 44100
        for packet in stream.encode(frame):
            c.mux(packet)
        for packet in stream.encode(None):
            c.mux(packet)
    window = MainWindow(muted=True)
    project, _saved, _known = window._project_for(path)
    assert (project.audio["title"], project.audio["artist"]) == ("Chanson inventée", "Personne")
    assert project.audio["identity"] == {"how": "tags", "sure": True}
    window.close()


def test_catalog_times_can_be_dropped_and_the_words_kept(app, wav, tmp_path, calls):
    window = open_song(app, wav, tmp_path, auto=False, mode="lyrics")
    c = window.lyrics
    c._replace(lyrics_online.lines_of(FOUND), lyrics_online.source_of(FOUND, True))
    assert L.timed(window.project.lyrics) and c.untime_action.isEnabled()
    c.clear_times()
    lyr = window.project.lyrics
    assert not L.timed(lyr) and lyr["lines"][0]["text"] == "Une ligne inventée"
    assert not L.exportable(lyr)  # a correction does not make them ours to hand out
    window.undo()
    assert L.timed(window.project.lyrics)
    window.close()
