"""The library home page, driven offscreen: favourites, search, collections, safe deletion."""

import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
import synth
from test_core import analysis as make_analysis

from localchords import library
from localchords.project import Project
from localchords.ui import library_view
from localchords.ui.main_window import MainWindow, app_instance


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "data"))
    # Never the real Recycle Bin from a test: a folder stands in for it.
    bin_ = tmp_path / "corbeille"
    bin_.mkdir()

    def to_bin(path: Path) -> bool:
        shutil.move(str(path), str(bin_ / path.name))
        return True

    monkeypatch.setattr(library_view, "trash", to_bin)


@pytest.fixture
def app():
    return app_instance()


@pytest.fixture
def wav(tmp_path):
    y, _ = synth.render([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)] * 2, 120)
    return synth.write_wav(tmp_path / "original.wav", y)


def wait_for(app, condition, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def song(fp: str, title: str, artist: str = "", path: Path | None = None, **extra) -> Path:
    audio = {"path": str(path or ""), "title": title, "artist": artist, "duration": 16.0,
             "fingerprint": fp, **extra}  # fmt: skip
    file = library.project_path(fp)
    Project(audio, make_analysis()).save(file)
    return file


def window_on(app, *files):
    window = MainWindow(muted=True)
    window.resize(1400, 800)
    window.show()
    assert wait_for(app, lambda: not window.home.scanning)
    assert len(window.catalog.songs()) == len(files)
    return window


def titles(window):
    return [r["title"] for r in window.home.model.rows]


def test_star_on_the_song_page_makes_a_lasting_favourite(app, wav):
    file = song("a" * 32, "Étoile", "Moi", wav)
    window = window_on(app, file)
    window.open_project_file(file)
    assert not window.song.star.isChecked()
    window.song.star.setChecked(True)
    window.go_home()
    window.home.select_view(("fav",))
    assert titles(window) == ["Étoile"]
    window.close()

    window = window_on(app, file)
    window.home.select_view(("fav",))
    assert titles(window) == ["Étoile"]
    window.open_project_file(file)
    assert window.song.star.isChecked()
    window.close()


def test_a_favourite_never_leaves_for_not_being_opened(app, wav):
    files = [song(f"{i:032d}", f"Morceau {i}", path=wav) for i in range(3)]
    window = window_on(app, *files)
    window.home.toggle_favorite([window.catalog.song(files[0].stem)])
    window.home.select_view(("fav",))
    assert titles(window) == ["Morceau 0"]
    for f in files[1:]:
        window.open_project_file(f)
    window.go_home()
    window.home.select_view(("fav",))
    assert titles(window) == ["Morceau 0"]
    window.close()


def test_search_filters_and_sorts(app, wav):
    files = [
        song("1" * 32, "Yesterday", "The Beatles", wav),
        song("2" * 32, "Été indien", "Joe Dassin", wav),
        song("3" * 32, "Let It Be", "The Beatles", wav),
    ]
    window = window_on(app, *files)
    home = window.home
    assert titles(window) == ["Été indien", "Let It Be", "Yesterday"]  # by title, accents folded
    home.search.setText("beatles")
    assert wait_for(app, lambda: len(home.model.rows) == 2, 3)
    home.search.setText("ete")
    assert wait_for(app, lambda: titles(window) == ["Été indien"], 3)
    assert home.clear_filters.isVisibleTo(home)
    home.search.setText("rien de tel")
    assert wait_for(app, lambda: home.pages.currentWidget() is home.empty, 3)
    assert "Aucun morceau ne correspond" in home.empty_text.text()
    home.empty_action.click()  # clears the search and the filters
    assert len(home.model.rows) == 3
    window.catalog.set_genre([files[1].stem], "Variété")
    home.refresh()
    home.genre_box.setCurrentIndex(home.genre_box.findData("Variété"))
    assert titles(window) == ["Été indien"]
    home.genre_box.setCurrentIndex(home.genre_box.findData(""))  # Non renseigné
    assert set(titles(window)) == {"Let It Be", "Yesterday"}
    home.reset_filters()
    home.sort_box.setCurrentIndex(home.sort_box.findData("artist"))
    assert [r["artist"] for r in home.model.rows][0] == "Joe Dassin"
    home.desc.setChecked(True)
    assert [r["artist"] for r in home.model.rows][-1] == "Joe Dassin"
    window.close()


def test_collections_keep_their_songs_and_order(app, wav):
    files = [song(f"{i:032d}", f"Titre {i}", path=wav) for i in range(3)]
    window = window_on(app, *files)
    home = window.home
    cid = window.catalog.create_collection("Pour le concert")
    home.select_view(("col", cid))
    assert home.pages.currentWidget() is home.empty
    assert "collection est vide" in home.empty_text.text()
    window.catalog.add_to_collection(cid, [files[2].stem, files[0].stem])
    home.refresh()
    assert home.sort_box.currentData() == "order"
    assert titles(window) == ["Titre 2", "Titre 0"]
    home.table.selectRow(1)
    home.move_selected(-1)
    assert titles(window) == ["Titre 0", "Titre 2"]
    window.catalog.delete_collection(cid)
    home.refresh()
    assert home.view_key == ("all",) and len(home.model.rows) == 3  # the songs stay
    assert all(f.exists() for f in files)
    window.close()


def test_songs_dragged_onto_a_collection_or_favourites_join_it(app, wav):
    from PySide6.QtCore import QMimeData, QPointF, Qt
    from PySide6.QtGui import QDropEvent

    files = [song(f"{i:032d}", f"Glissé {i}", path=wav) for i in range(3)]
    window = window_on(app, *files)
    home = window.home
    cid = window.catalog.create_collection("Scène")
    home.refresh()
    index = home.model.index
    mime = home.model.mimeData([index(0, 1), index(2, 1), index(2, 3)])
    ids = bytes(mime.data(library_view.SONGS_MIME)).decode().split()
    assert ids == [home.model.rows[0]["id"], home.model.rows[2]["id"]]  # one per song, in order
    side = home.side

    def drop_on(key):
        row = next(i for i in range(side.count())
                   if side.item(i).data(Qt.ItemDataRole.UserRole) == key)  # fmt: skip
        point = QPointF(side.visualItemRect(side.item(row)).center())
        event = QDropEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)  # fmt: skip
        side.dropEvent(event)

    drop_on(("col", cid))
    assert window.catalog.members(cid) == ids
    drop_on(("fav",))
    assert {s["id"] for s in window.catalog.songs() if s["favorite"]} == set(ids)
    foreign = QMimeData()
    foreign.setText("pas des morceaux")
    assert not side.acceptDrops() or side._target(
        QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, foreign, Qt.MouseButton.LeftButton,
                   Qt.KeyboardModifier.NoModifier)  # fmt: skip
    ) is None
    window.close()


def test_deleting_an_analysis_never_touches_the_original(app, wav, tmp_path, monkeypatch):
    fp = "d" * 32
    kept = library.data_dir() / "audio" / f"{fp}.wav"
    kept.parent.mkdir(parents=True)
    shutil.copyfile(wav, kept)
    file = song(fp, "À jeter", path=wav, kept=f"audio/{fp}.wav")
    window = window_on(app, file)
    home = window.home
    row = window.catalog.song(fp)
    monkeypatch.setattr(library_view.LibraryPage, "_ask_delete", lambda self, s, m: None)
    home.delete_projects([row])
    assert file.exists() and window.catalog.song(fp)  # cancelled: nothing happens
    monkeypatch.setattr(library_view.LibraryPage, "_ask_delete", lambda self, s, m: bool(m))
    home.delete_projects([row])
    assert not file.exists() and (tmp_path / "corbeille" / file.name).exists()
    assert not kept.exists() and (tmp_path / "corbeille" / kept.name).exists()
    assert wav.exists()  # the user's own recording stays where it was
    assert window.catalog.song(fp) is None
    window.close()


def test_an_open_song_is_not_saved_over_a_deleted_project(app, wav, monkeypatch):
    file = song("e" * 32, "Ouvert", path=wav)
    window = window_on(app, file)
    window.open_project_file(file)
    window.go_home()
    monkeypatch.setattr(library_view.LibraryPage, "_ask_delete", lambda self, s, m: False)
    window.home.delete_projects([window.catalog.song(file.stem)])
    assert window.project_file is None
    window.save()
    assert not file.exists()
    window.close()


def test_hidden_songs_come_back(app, wav):
    file = song("f" * 32, "Caché", path=wav)
    window = window_on(app, file)
    home = window.home
    home._hide([file.stem], True)
    assert home.pages.currentWidget() is home.welcome or not home.model.rows
    home.select_view(("hidden",))
    assert titles(window) == ["Caché"]
    window.open_project_file(file)
    window.go_home()
    home.select_view(("all",))
    assert titles(window) == ["Caché"]
    window.close()


def test_a_link_imported_before_is_not_downloaded_again(app, wav):
    url = "https://example.com/watch?v=1"
    file = song("9" * 32, "Déjà là", path=wav, source_url=url)
    window = window_on(app, file)
    window.import_link(url)
    assert window.download_job is None
    assert window.project_file == file and window.stack.currentWidget() is window.song
    window.close()


def test_enter_and_double_click_open_a_song(app, wav):
    file = song("8" * 32, "Entrée", path=wav)
    window = window_on(app, file)
    window.home.table.setFocus()
    window.home.table.selectRow(0)
    window._enter()
    assert window.project_file == file and window.stack.currentWidget() is window.song
    window.close()


def test_cards_show_the_same_songs_and_their_star(app, wav):
    file = song("7" * 32, "Carte", path=wav)
    window = window_on(app, file)
    home = window.home
    home.set_mode("cards")
    assert home.pages.currentWidget() is home.cards
    assert window.settings["library_view"] == "cards"
    home.cards.starClicked.emit(0)
    assert window.catalog.song(file.stem)["favorite"]
    home.set_mode("list")
    window.close()


def test_missing_project_and_audio_are_said_not_deleted(app, wav, tmp_path):
    gone = tmp_path / "gone.wav"
    shutil.copyfile(wav, gone)
    file = song("6" * 32, "Parti", path=gone)
    window = window_on(app, file)
    window.close()
    gone.unlink()
    file.unlink()
    window = MainWindow(muted=True)
    assert wait_for(app, lambda: not window.home.scanning)
    row = window.home.model.rows[0]
    assert window.home.model.text(row, "audio") == "Projet absent"
    assert window.catalog.song("6" * 32)  # still listed: never dropped behind the user's back
    window.close()


def test_a_thousand_songs_stay_quick(app):
    window = MainWindow(muted=True)
    assert wait_for(app, lambda: not window.home.scanning)
    now = time.time()
    rows = [
        (f"{i:032x}", f"{i:032x}.lchords", f"Chanson {i}", f"Artiste {i % 37}", now - i, "ok")
        for i in range(1000)
    ]
    window.catalog._many(
        "INSERT INTO songs (id, file, title, artist, added_at, audio_state) VALUES (?,?,?,?,?,?)",
        rows,
    )
    window.catalog.set_favorite([r[0] for r in rows[:40]], True)
    home = window.home
    started = time.perf_counter()
    home.refresh()
    assert time.perf_counter() - started < 1.0
    assert len(home.model.rows) == 1000
    started = time.perf_counter()
    home.search.setText("artiste 5")
    home.refresh()
    assert time.perf_counter() - started < 1.0
    found = home.model.rows  # every word, anywhere in the title or the artist
    assert found and len(found) < 1000
    assert all("5" in r["artist"] + r["title"] for r in found)
    window.close()
