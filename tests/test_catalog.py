"""The library (v1.4): the catalog, kept copies of the audio, backups. No window here."""

import json
import os
import sqlite3
import string
import time
import zipfile
from pathlib import Path

import pytest
import synth
from test_core import analysis

from localchords import backup, catalog, library
from localchords import lyrics as L
from localchords.catalog import Catalog, CatalogError, arrange, open_catalog
from localchords.project import VERSION, Project


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv("LOCALCHORDS_DATA", str(folder))
    return library.data_dir()


def wav(folder: Path, name: str, chords=("C:maj", "G:maj")) -> Path:
    bpm = 90 + sum(name.encode()) % 60  # each name its own recording, its own fingerprint
    y, _ = synth.render([(c, 4) for c in chords] * 2, bpm)
    folder.mkdir(parents=True, exist_ok=True)
    return synth.write_wav(folder / name, y)


def make_project(path_audio: Path, title="Chanson", artist="", lyrics=None, **audio_extra) -> Path:
    """A project as v1.3 saved it, in the projects folder, named by the audio's fingerprint."""
    from localchords import audio

    fp = audio.fingerprint(path_audio)
    a = analysis()
    info = {"path": str(path_audio), "title": title, "artist": artist, "duration": 8.0,
            "fingerprint": fp, **audio_extra}  # fmt: skip
    p = Project(info, a, lyrics=lyrics)
    target = library.project_path(fp)
    p.save(target)
    return target


def scanned(data) -> Catalog:
    c, note = open_catalog(data)
    assert note is None
    c.scan(data / "projects")
    return c


# Migration and the index -------------------------------------------------------------------------
def test_existing_projects_are_found_without_changing_them(data, tmp_path):
    files = [make_project(wav(tmp_path / "music", f"s{i}.wav"), f"Titre {i}") for i in range(3)]
    before = {f: (f.read_bytes(), f.stat().st_mtime) for f in files}
    old = time.time() - 30 * 86400
    os.utime(files[0], (old, old))
    before[files[0]] = (files[0].read_bytes(), files[0].stat().st_mtime)
    c = scanned(data)
    songs = {s["title"]: s for s in c.songs()}
    assert set(songs) == {"Titre 0", "Titre 1", "Titre 2"}
    s = songs["Titre 0"]
    # A project from before v1.4 cannot say when it was added or opened: estimated, and said so.
    assert s["added_estimated"] == 1 and s["opened_estimated"] == 1
    assert abs(s["opened_at"] - old) < 2  # its file's last change, the closest to an opening
    assert s["key"] == "C:maj" and s["bpm"] == 120.0 and s["chords"] == 4
    assert s["audio_state"] == "ok" and s["analyzed"] == 1 and s["lyrics"] is None
    assert {f: (f.read_bytes(), f.stat().st_mtime) for f in files} == before  # untouched
    assert c.scan(data / "projects")["read"] == 0  # nothing changed: nothing read again


def test_a_changed_project_is_read_again_and_keeps_its_dates(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"), "Avant")
    c = scanned(data)
    first = c.songs()[0]
    p = Project.load(path)
    p.set_key("A:min")
    p.audio["title"] = "Après"
    time.sleep(0.02)
    p.save(path)
    c.scan(data / "projects")
    s = c.songs()[0]
    assert s["title"] == "Après" and s["key"] == "A:min"  # the correction shows in the library
    assert (s["added_at"], s["opened_at"]) == (first["added_at"], first["opened_at"])


def test_dates_of_adding_and_opening(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"))
    c, _ = open_catalog(data)
    t0 = time.time()
    c.store(path, Project.load(path), opened=True)  # what the window does on a new song
    s = c.songs()[0]
    assert s["added_estimated"] == 0 and s["opened_estimated"] == 0
    assert t0 - 1 <= s["added_at"] <= time.time() and s["opened_at"] >= t0 - 1
    time.sleep(0.02)
    c.store(path, Project.load(path))  # a later save: not an opening, not an adding
    assert c.songs()[0]["opened_at"] == s["opened_at"]
    c.opened(s["id"])
    assert c.songs()[0]["opened_at"] > s["opened_at"]
    assert c.songs()[0]["added_at"] == s["added_at"]


def test_a_missing_project_is_marked_never_forgotten(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"))
    c = scanned(data)
    c.set_favorite([path.stem], True)
    moved = path.with_suffix(".away")
    path.rename(moved)
    c.scan(data / "projects")
    s = c.songs()[0]
    assert s["project_state"] == "missing" and s["favorite"] == 1
    moved.rename(path)
    c.scan(data / "projects")
    assert c.songs()[0]["project_state"] == "ok" and c.songs()[0]["favorite"] == 1


def test_an_unreadable_project_keeps_what_was_known(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"), "Connu")
    c = scanned(data)
    path.write_text('{"format": "localchords", "version": 99}', encoding="utf-8")
    c.scan(data / "projects")
    s = c.songs()[0]
    assert s["project_state"] == "unreadable" and s["title"] == "Connu"
    junk = data / "projects" / "nouveau.lchords"
    junk.write_text("pas du json", encoding="utf-8")
    c.scan(data / "projects")
    assert {s["title"] for s in c.songs()} == {"Connu", "nouveau"}


def test_v13_projects_still_open_and_the_format_is_unchanged(data, tmp_path):
    # v1.4 writes no new project version: v1.3 opens what v1.4 saves, and the other way round.
    assert VERSION == 2
    lyr = L.new([{"text": "la", "start": 1.0}], {"kind": "user", "name": "", "exportable": True})
    path = make_project(wav(tmp_path, "a.wav"), lyrics=lyr, kept="audio/x.wav", genre="Pop")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["version"] == 2 and set(d) == {"format", "version", "audio", "analysis", "edits",
                                            "view", "lyrics"}  # fmt: skip
    p = Project.load(path)
    assert p.audio["kept"] == "audio/x.wav" and p.lyrics["lines"][0]["text"] == "la"


# Favourites, genres, tags, collections -----------------------------------------------------------
def test_favourites_survive_a_restart(data, tmp_path):
    ids = [make_project(wav(tmp_path, f"{i}.wav"), f"T{i}").stem for i in range(3)]
    c = scanned(data)
    c.set_favorite(ids[:2], True)
    c.set_favorite([ids[0]], False)
    c.close()
    c, _ = open_catalog(data)
    assert {s["id"] for s in c.songs() if s["favorite"]} == {ids[1]}


def test_genres_from_the_file_can_be_corrected(data, tmp_path):
    a = make_project(wav(tmp_path, "a.wav"), "A", genre="Rock").stem
    b = make_project(wav(tmp_path, "b.wav"), "B", genre="").stem
    c = scanned(data)
    shown = lambda: {s["id"]: s["shown_genre"] for s in c.songs()}  # noqa: E731
    assert shown() == {a: "Rock", b: None}  # unknown stays unknown: « Non renseigné »
    c.set_genre([a], "Variété française")
    c.set_genre([b], "Piano solo")
    assert shown() == {a: "Variété française", b: "Piano solo"}
    c.set_genre([a], "")  # none, whatever the file says
    assert shown()[a] is None
    c.set_genre([a], None)  # back to the file's
    assert shown()[a] == "Rock"
    assert [s["id"] for s in arrange(c.songs(), genre="")] == []
    c.set_genre([b], None)
    assert [s["id"] for s in arrange(c.songs(), genre="")] == [b]
    assert c.genres() == ["Rock"]


def test_tags_join_once_whatever_their_case(data, tmp_path):
    ids = [make_project(wav(tmp_path, f"{i}.wav"), f"T{i}").stem for i in range(2)]
    c = scanned(data)
    c.add_tag(ids, "À apprendre")
    c.add_tag([ids[0]], "à apprendre")
    c.add_tag([ids[0]], "Piano")
    assert c.tags() == ["À apprendre", "Piano"]
    assert [s["tags"] for s in sorted(c.songs(), key=lambda s: s["title"])] == [
        ["À apprendre", "Piano"], ["À apprendre"]]  # fmt: skip
    assert [s["title"] for s in arrange(c.songs(), tag="piano")] == ["T0"]
    c.remove_tag(ids, "À APPRENDRE")
    assert c.tags() == ["Piano"]


def test_a_song_in_several_collections_is_one_song(data, tmp_path):
    ids = [make_project(wav(tmp_path, f"{i}.wav"), f"T{i}").stem for i in range(3)]
    c = scanned(data)
    piano = c.create_collection("Mes morceaux de piano")
    week = c.create_collection("À apprendre cette semaine")
    c.add_to_collection(piano, ids)
    c.add_to_collection(week, [ids[2], ids[0]])
    c.add_to_collection(week, [ids[0]])  # already there: stays once, in its place
    assert c.members(week) == [ids[2], ids[0]]
    assert sorted(c.collections_of(ids[0])) == sorted([piano, week])
    assert len(c.songs()) == 3 and len(list((data / "projects").iterdir())) == 3
    c.reorder(piano, [ids[2], ids[0]])
    assert c.members(piano) == [ids[2], ids[0], ids[1]]
    assert [s["id"] for s in arrange(c.songs(), order=c.members(piano))] == c.members(piano)
    c.remove_from_collection(piano, [ids[0]])
    assert c.members(piano) == [ids[2], ids[1]]
    with pytest.raises(CatalogError):
        c.create_collection("mes morceaux de PIANO")
    with pytest.raises(CatalogError):
        c.rename_collection(week, "Mes morceaux de piano")
    c.rename_collection(week, "Répertoire guitare")
    c.delete_collection(piano)
    assert [x["name"] for x in c.collections()] == ["Répertoire guitare"]
    assert len(c.songs()) == 3 and all(p.exists() for p in (data / "projects").iterdir())


# Search and sort ---------------------------------------------------------------------------------
def song(**kw):
    base = {"id": kw.get("title", "x"), "title": "", "artist": "", "album": "", "shown_genre": None,
            "tags": [], "year": None, "added_at": None, "opened_at": None, "key": None,
            "bpm": None, "duration": None, "lyrics": None, "audio_state": "ok"}  # fmt: skip
    return base | kw


def test_search_ignores_case_and_accents_across_fields():
    songs = [
        song(title="Été indien", artist="Joe"),
        song(title="Blues", artist="Élodie", tags=["À apprendre"]),
        song(title="Pluie", album="Saisons", shown_genre="Variété française", year=1971),
    ]
    titles = lambda q: [s["title"] for s in arrange(songs, query=q)]  # noqa: E731
    assert titles("ete ind") == ["Été indien"]
    assert titles("ELODIE") == ["Blues"]
    assert titles("apprendre") == ["Blues"]
    assert titles("variete saisons") == ["Pluie"]
    assert titles("1971") == ["Pluie"]
    assert titles("rien") == []


def test_every_sort_puts_unknown_values_last():
    songs = [
        song(title="b", artist="Zoé", year=2001, bpm=90.0, key="A:min", added_at=3, opened_at=1,
             shown_genre="Rock", duration=200.0),
        song(title="A", artist="adam", year=1999, bpm=140.0, key="C:maj", added_at=1, opened_at=5,
             shown_genre="pop", duration=100.0),
        song(title="c"),  # nothing known but its title
    ]  # fmt: skip
    for sort, order in {
        "title": "Abc", "artist": "Abc", "year": "Abc", "bpm": "bAc", "key": "Abc",
        "added": "Abc", "opened": "bAc", "genre": "Abc", "duration": "Abc",
    }.items():  # fmt: skip
        assert "".join(s["title"] for s in arrange(songs, sort=sort)) == order, sort
        backwards = "".join(s["title"] for s in arrange(songs, sort=sort, descending=True))
        assert backwards == (order[::-1] if sort == "title" else order[:2][::-1] + "c"), sort


def test_filters_by_lyrics_and_audio():
    songs = [song(title="a", lyrics="user"), song(title="b", audio_state="missing"),
             song(title="c", audio_state="offline"), song(title="d", audio_state="kept")]  # fmt: skip
    pick = lambda st: [s["title"] for s in arrange(songs, state=st)]  # noqa: E731
    assert pick("lyrics") == ["a"]
    assert pick("nolyrics") == ["b", "c", "d"]
    assert pick("missing") == ["b", "c"]
    assert pick("kept") == ["d"]


def test_a_thousand_songs_stay_quick(data, tmp_path):
    c, _ = open_catalog(data)
    rows = [
        (f"{i:032x}", f"{i}.lchords", f"Titre {i}", f"Artiste {i % 37}", 1700000000 + i, i % 2)
        for i in range(1000)
    ]
    c._many(
        "INSERT INTO songs (id, file, title, artist, added_at, favorite) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    c.add_tag([r[0] for r in rows[::3]], "Piano")
    start = time.perf_counter()
    songs = c.songs()
    for sort in catalog.SORTS:
        arrange(songs, sort=sort, query="titre 9")
    elapsed = time.perf_counter() - start
    assert len(songs) == 1000 and elapsed < 1.0, elapsed


def test_a_first_scan_of_hundreds_of_projects(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    for i in range(300):
        raw["audio"]["title"] = f"Copie {i}"
        (data / "projects" / f"{i:032x}.lchords").write_text(json.dumps(raw), encoding="utf-8")
    c, _ = open_catalog(data)
    start = time.perf_counter()
    report = c.scan(data / "projects")
    first = time.perf_counter() - start
    start = time.perf_counter()
    again = c.scan(data / "projects")
    second = time.perf_counter() - start
    assert report["read"] == 301 and again["read"] == 0
    # The first runs once, off the interface's thread; the next ones only stat the files.
    assert first < 60 and second < 2, (first, second)


# The audio ---------------------------------------------------------------------------------------
def unused_drive() -> str:
    return next(f"{d}:\\" for d in reversed(string.ascii_uppercase) if not Path(f"{d}:\\").exists())


def test_audio_states_tell_missing_from_disconnected(data, tmp_path):
    here = wav(tmp_path, "a.wav")
    assert catalog.audio_state(str(here), None) == "ok"
    assert catalog.audio_state(str(tmp_path / "gone.wav"), None) == "missing"
    # A drive that is not there (an external disk unplugged): maybe it comes back.
    assert catalog.audio_state(unused_drive() + "Musique\\a.wav", None) == "offline"


def test_an_unplugged_drive_deletes_nothing(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"))
    p = Project.load(path)
    p.audio["path"] = unused_drive() + "Musique\\a.wav"
    p.save(path)
    c = scanned(data)
    c.set_favorite([path.stem], True)
    c.scan(data / "projects")
    s = c.songs()[0]
    assert s["audio_state"] == "offline" and s["project_state"] == "ok" and s["favorite"]
    assert path.exists()


def test_a_kept_copy_is_made_once_and_never_touches_the_original(data, tmp_path):
    from localchords import audio

    original = wav(tmp_path / "music", "a.wav")
    before = (original.read_bytes(), original.stat().st_mtime)
    fp = audio.fingerprint(original)
    place = library.keep_copy(original, fp)
    assert place == f"audio/{fp}.wav" and (data / place).read_bytes() == before[0]
    assert library.keep_copy(original, fp) == place  # the same recording is kept once
    assert len(list((data / "audio").iterdir())) == 1
    assert (original.read_bytes(), original.stat().st_mtime) == before
    other = wav(tmp_path / "music", "b.wav", chords=("D:min", "A:min"))
    with pytest.raises(library.KeepError):
        library.keep_copy(other, fp)  # not the analyzed recording
    assert library.managed(data / place) and not library.managed(original)
    # The copy plays once the original has gone.
    original.unlink()
    info = {"path": str(original), "kept": place}
    assert library.audio_file(info) == data / place
    assert catalog.audio_state(str(original), place) == "kept"


def test_a_kept_copy_fails_cleanly_without_room(data, tmp_path, monkeypatch):
    from localchords import audio

    original = wav(tmp_path, "a.wav")
    monkeypatch.setattr(library, "free_mb", lambda folder: 1)
    with pytest.raises(library.KeepError, match="place"):
        library.keep_copy(original, audio.fingerprint(original))
    assert not list((data / "audio").glob("*"))


def test_moved_files_are_found_in_the_chosen_folder_only(data, tmp_path):
    from localchords import audio

    a = wav(tmp_path / "old", "a.wav")
    b = wav(tmp_path / "old", "b.wav", chords=("E:min", "B:7"))
    wanted = [
        {"id": "a", "fingerprint": audio.fingerprint(a), "name": "a.wav", "size": None},
        {"id": "b", "fingerprint": audio.fingerprint(b), "name": "b.wav", "size": b.stat().st_size},
    ]
    new = tmp_path / "new" / "deep"
    new.mkdir(parents=True)
    a.rename(new / "a.wav")
    b.rename(new / "renommé.wav")  # renamed: found by its size
    # A different recording with the same name is not taken for it.
    wav(tmp_path / "new", "a.wav", chords=("F:maj", "C:maj"))
    found = library.find_moved(tmp_path / "new", wanted)
    assert found == {"a": new / "a.wav", "b": new / "renommé.wav"}
    assert library.find_moved(tmp_path / "elsewhere", wanted) == {}


def test_portable_data_moves_with_its_kept_audio_and_downloads(data, tmp_path, monkeypatch):
    from localchords import audio

    original = wav(tmp_path, "a.wav")
    place = library.keep_copy(original, audio.fingerprint(original))
    download = wav(data / "downloads", "clip [x1].wav")
    moved = tmp_path / "other-drive" / "Data"
    moved.parent.mkdir()
    data.rename(moved)
    monkeypatch.setenv("LOCALCHORDS_DATA", str(moved))
    assert library.audio_file({"path": str(tmp_path / "gone.wav"), "kept": place}) == moved / place
    assert library.audio_file({"path": str(download)}) == moved / "downloads" / download.name
    assert catalog.audio_state(str(download), None) == "kept"


def test_a_link_already_imported_is_found(data, tmp_path):
    clip = wav(data / "downloads", "clip [x1].wav")
    path = make_project(clip, source_url="https://example.org/v/1")
    c = scanned(data)
    assert c.find_url("https://example.org/v/1")["id"] == path.stem
    assert c.find_url("https://example.org/v/2") is None


# Damage and errors -------------------------------------------------------------------------------
def test_a_damaged_index_comes_back_from_its_daily_copy(data, tmp_path):
    ids = [make_project(wav(tmp_path, f"{i}.wav"), f"T{i}").stem for i in range(2)]
    c = scanned(data)
    c.set_favorite([ids[0]], True)
    cid = c.create_collection("Famille")
    c.add_to_collection(cid, ids)
    assert c.backup_daily(data / catalog.BACKUPS)
    c.close()
    (data / catalog.FILE).write_bytes(b"\0" * 4096)
    c, note = open_catalog(data)
    assert "copie" in note
    c.scan(data / "projects")
    assert {s["id"] for s in c.songs() if s["favorite"]} == {ids[0]}
    assert c.members(c.collections()[0]["cid"]) == ids
    assert list(data.glob("catalog-*.illisible"))  # the damaged file is kept aside


def test_a_damaged_index_without_copy_is_rebuilt_from_the_projects(data, tmp_path):
    make_project(wav(tmp_path, "a.wav"))
    (data / catalog.FILE).write_bytes(b"pas une base")
    c, note = open_catalog(data)
    assert "reconstruit" in note
    c.scan(data / "projects")
    assert len(c.songs()) == 1


def test_an_unwritable_folder_gives_a_catalog_in_memory(data, monkeypatch):
    monkeypatch.setattr(library, "unwritable", lambda folder: "lecture seule")
    c, note = open_catalog(data)
    assert "lecture seule" in note and c.path == ":memory:"
    c.create_collection("Essai")  # works for the session
    assert not (data / catalog.FILE).exists()


def test_a_newer_catalog_is_left_alone(data):
    c, _ = open_catalog(data)
    c.db.execute("PRAGMA user_version = 99")
    c.close()
    c, note = open_catalog(data)
    assert "récente" in note and c.path == ":memory:"
    raw = sqlite3.connect(data / catalog.FILE)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 99


def test_a_write_that_fails_says_so(data, tmp_path):
    make_project(wav(tmp_path, "a.wav"))
    c = scanned(data)
    sid = c.songs()[0]["id"]
    c.close()
    c.db = sqlite3.connect(f"file:{data / catalog.FILE}?mode=ro", uri=True)
    with pytest.raises(CatalogError, match="enregistrée"):
        c.set_favorite([sid], True)


def test_daily_copies_are_few(data, tmp_path):
    make_project(wav(tmp_path, "a.wav"))
    c = scanned(data)
    folder = data / catalog.BACKUPS
    folder.mkdir()
    for day in range(1, 10):
        (folder / f"catalog-2026-01-0{day}.db").write_bytes(b"x")
    assert c.backup_daily(folder) and c.backup_daily(folder) is None  # once a day
    assert len(list(folder.glob("catalog-*.db"))) == catalog.KEEP_BACKUPS


# Backups -----------------------------------------------------------------------------------------
def library_with_everything(data, tmp_path):
    from localchords import lyrics_online  # noqa: F401 - the catalog lyrics' shape

    catalog_lyrics = L.new(
        [{"text": "sous licence", "start": 1.0}],
        {"kind": "catalog", "name": "LRCLIB", "exportable": False},
    )
    a = make_project(wav(tmp_path / "music", "a.wav"), "Alpha", genre="Pop")
    b = make_project(wav(tmp_path / "music", "b.wav", chords=("D:min", "A:min")), "Bravo",
                     lyrics=catalog_lyrics)  # fmt: skip
    p = Project.load(a)
    p.set_chord(0.0, 2.0, "E:min")  # a correction
    p.set_view(positions={"E:min": 2})
    p.save(a)
    c = scanned(data)
    c.set_favorite([a.stem], True)
    c.set_genre([b.stem], "Chanson")
    c.add_tag([a.stem, b.stem], "À apprendre")
    cid = c.create_collection("Répertoire")
    c.add_to_collection(cid, [b.stem, a.stem])
    return c, a, b


def test_a_backup_restores_on_another_pc(data, tmp_path, monkeypatch):
    c, a, b = library_with_everything(data, tmp_path)
    size = backup.estimate(c, with_audio=True)
    assert size["projects"] == 2 and size["audio"] == 2 and size["audio_bytes"] > 0
    archive = tmp_path / "sauvegarde.zip"
    manifest = backup.write(archive, c, with_audio=True)
    assert manifest["audio"] == 2 and manifest["private"]
    projects = {p.name: p.read_bytes() for p in (data / "projects").iterdir()}
    # A new PC: an empty Data folder, and the music folder is not there.
    (tmp_path / "music").rename(tmp_path / "music-elsewhere")
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "new-pc"))
    new = library.data_dir()
    c2, _ = open_catalog(new)
    plan = backup.inspect(archive)
    assert sorted(plan["new"]) == sorted([a.stem, b.stem]) and not plan["differ"]
    report = backup.restore(archive, c2)
    assert report["written"] == 2 and report["audio"] == 2
    for name, raw in projects.items():
        restored = Project.load(new / "projects" / name)
        original = json.loads(raw)
        assert restored.edits == original["edits"] and restored.view == original["view"]
        assert restored.lyrics == original.get("lyrics")
        assert library.audio_file(restored.audio).is_file()  # the kept copy
    songs = {s["title"]: s for s in c2.songs()}
    assert songs["Alpha"]["favorite"] and songs["Bravo"]["shown_genre"] == "Chanson"
    assert songs["Alpha"]["tags"] == ["À apprendre"]
    cid = c2.collections()[0]["cid"]
    assert c2.members(cid) == [b.stem, a.stem]
    # Restoring again duplicates nothing.
    again = backup.restore(archive, c2)
    assert again["written"] == 0 and again["same"] == 2
    assert len(c2.songs()) == 2 and c2.members(cid) == [b.stem, a.stem]
    assert len(list((new / "audio").iterdir())) == 2


def test_a_restore_never_overwrites_newer_work_silently(data, tmp_path):
    c, a, b = library_with_everything(data, tmp_path)
    archive = tmp_path / "sauvegarde.zip"
    backup.write(archive, c, with_audio=False)
    time.sleep(2.1)  # the zip keeps times to two seconds
    p = Project.load(a)
    p.set_chord(2.0, 4.0, "B:min")  # work done after the backup
    p.save(a)
    mine = a.read_bytes()
    plan = backup.inspect(archive)
    assert plan["differ"] == [a.stem] and plan["newer"] == []
    report = backup.restore(archive, c)
    assert a.read_bytes() == mine  # this PC's version stays
    assert report["set_aside"] == 1
    aside = Path(report["aside_folder"])
    assert [f.name for f in aside.iterdir()] == [f"{a.stem} (sauvegarde).lchords"]
    # Even asked to take the newer, the backup is older here: still this PC's.
    backup.restore(archive, c, take_newer=True)
    assert a.read_bytes() == mine


def test_a_restore_can_take_the_newer_backup_and_keeps_the_other(data, tmp_path):
    c, a, b = library_with_everything(data, tmp_path)
    old = time.time() - 86400
    os.utime(a, (old, old))
    p = Project.load(a)
    p.set_chord(2.0, 4.0, "B:min")
    p.save(a)
    os.utime(a, (old, old))  # this PC's change is the older one
    archive = tmp_path / "sauvegarde.zip"
    p.undo()
    p.save(a)
    backup.write(archive, c, with_audio=False)
    p.redo()
    p.save(a)
    os.utime(a, (old, old))
    plan = backup.inspect(archive)
    assert plan["newer"] == [a.stem]
    report = backup.restore(archive, c, take_newer=True)
    assert Project.load(a).edits["chords"][-1]["chord"] == "E:min"  # the backup's
    kept = Path(report["aside_folder"]) / f"{a.stem} (ce PC).lchords"
    assert Project.load(kept).edits["chords"][-1]["chord"] == "B:min"  # nothing lost


def test_catalog_lyrics_can_stay_out_and_never_become_exportable(data, tmp_path, monkeypatch):
    c, a, b = library_with_everything(data, tmp_path)
    without = tmp_path / "sans.zip"
    backup.write(without, c, with_audio=False, catalog_lyrics=False)
    with zipfile.ZipFile(without) as z:
        d = json.loads(z.read(f"projects/{b.name}"))
        assert "lyrics" not in d
        assert json.loads(z.read("manifest.json"))["catalog_lyrics"] is False
    with_them = tmp_path / "avec.zip"
    backup.write(with_them, c, with_audio=False)
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "new-pc"))
    c2, _ = open_catalog(library.data_dir())
    backup.restore(with_them, c2)
    restored = Project.load(library.data_dir() / "projects" / b.name)
    assert restored.lyrics["source"]["kind"] == "catalog"
    assert not L.exportable(restored.lyrics)  # restored, still not exportable
    assert "lyrics" not in restored.to_dict(shared=True)  # nor in a copy meant for others


def test_a_backup_is_whole_or_absent(data, tmp_path, monkeypatch):
    c, a, b = library_with_everything(data, tmp_path)
    target = tmp_path / "out" / "sauvegarde.zip"
    target.parent.mkdir()
    monkeypatch.setattr(library, "free_mb", lambda folder: 0)
    with pytest.raises(backup.BackupError, match="place"):
        backup.write(target, c, with_audio=True)
    monkeypatch.undo()
    monkeypatch.setenv("LOCALCHORDS_DATA", str(data))
    with pytest.raises(backup.BackupError, match="annulée"):
        backup.write(target, c, with_audio=False, stop=lambda: True)
    assert list(target.parent.iterdir()) == []  # no half file
    backup.write(target, c, with_audio=False)
    assert [f.name for f in target.parent.iterdir()] == ["sauvegarde.zip"]


def test_a_bad_backup_is_refused(data, tmp_path):
    c, _ = open_catalog(data)
    junk = tmp_path / "x.zip"
    junk.write_bytes(b"pas un zip")
    with pytest.raises(backup.BackupError, match="lisible"):
        backup.inspect(junk)
    other = tmp_path / "y.zip"
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "autre"}))
    with pytest.raises(backup.BackupError):
        backup.restore(other, c)
    newer = tmp_path / "z.zip"
    with zipfile.ZipFile(newer, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": backup.FORMAT, "version": 9}))
    with pytest.raises(backup.BackupError, match="récente"):
        backup.inspect(newer)


def test_a_backup_cannot_write_outside_the_data_folder(data, tmp_path):
    c, _ = open_catalog(data)
    evil = tmp_path / "evil.zip"
    project = Project({"path": "x", "duration": 1.0, "fingerprint": "../../evil"}, analysis())
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": backup.FORMAT, "version": 1}))
        z.writestr("projects/../../evil.lchords", json.dumps(project.to_dict()))
        z.writestr("projects/ok.lchords", json.dumps(project.to_dict()))
        z.writestr("audio/../../evil.wav", b"RIFF")
    report = backup.restore(evil, c)
    assert report["written"] == 1 and report["audio"] == 0
    assert not (tmp_path / "evil.lchords").exists() and not (tmp_path / "evil.wav").exists()
    assert [p.name for p in (data / "projects").iterdir()] == ["ok.lchords"]


def test_preferences_come_back_only_when_asked(data, tmp_path, monkeypatch):
    c, a, b = library_with_everything(data, tmp_path)
    library.save_settings({**library.load_settings(), "latin": True})
    archive = tmp_path / "s.zip"
    backup.write(archive, c, with_audio=False)
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "new-pc"))
    c2, _ = open_catalog(library.data_dir())
    backup.restore(archive, c2)
    assert library.load_settings()["latin"] is False
    backup.restore(archive, c2, settings=True)
    assert library.load_settings()["latin"] is True


# Found in review -------------------------------------------------------------------------------
def test_a_v13_project_opened_before_the_scan_is_not_dated_today(data, tmp_path, monkeypatch):
    path = make_project(wav(tmp_path, "vieux.wav"))
    made = time.time() - 40 * 86400
    monkeypatch.setattr(catalog, "_created", lambda st: made)  # a file from v1.3, long ago
    c, _ = open_catalog(data)
    c.store(path, Project.load(path), opened=True)  # opened from the window, not yet scanned
    s = c.songs()[0]
    assert s["added_at"] == made and s["added_estimated"] == 1
    assert s["opened_estimated"] == 0 and s["opened_at"] > made  # the opening is real


def test_an_estimated_opening_from_a_backup_stays_estimated(data, tmp_path):
    path = make_project(wav(tmp_path, "a.wav"))
    c = scanned(data)
    s = c.songs()[0]
    assert s["opened_estimated"] == 1
    later = s["opened_at"] + 1000
    entry = {"id": s["id"], "opened_at": later, "opened_estimated": 1, "tags": []}
    c.merge_personal({"songs": [entry]})
    s = c.songs()[0]
    assert s["opened_at"] == later and s["opened_estimated"] == 1
    entry |= {"opened_at": later + 5, "opened_estimated": 0}
    c.merge_personal({"songs": [entry]})
    assert c.songs()[0]["opened_estimated"] == 0
    assert path.exists()


def test_a_backup_without_catalog_lyrics_keeps_each_project_date(data, tmp_path):
    c, a, b = library_with_everything(data, tmp_path)
    old = time.time() - 86400
    for f in (a, b):
        os.utime(f, (old, old))
    archive = tmp_path / "sans.zip"
    backup.write(archive, c, with_audio=False, catalog_lyrics=False)
    with zipfile.ZipFile(archive) as z:
        stamp = time.mktime((*z.getinfo(f"projects/{b.name}").date_time, 0, 0, -1))
    assert abs(stamp - old) < 3  # not the time of the backup: never taken for newer work
    assert backup.inspect(archive)["newer"] == []


def test_an_unreadable_project_stays_out_of_a_backup_without_catalog_lyrics(data, tmp_path):
    c, a, b = library_with_everything(data, tmp_path)
    bad = data / "projects" / ("f" * 32 + ".lchords")
    bad.write_text('{"format": "localchords", "version": 99}', encoding="utf-8")
    archive = tmp_path / "sans.zip"
    manifest = backup.write(archive, c, with_audio=False, catalog_lyrics=False)
    assert manifest["left_out"] == [bad.name]
    with zipfile.ZipFile(archive) as z:
        assert f"projects/{bad.name}" not in z.namelist()


def test_a_malformed_catalog_in_a_backup_is_refused_cleanly(data, tmp_path):
    c, a, b = library_with_everything(data, tmp_path)
    archive = tmp_path / "s.zip"
    backup.write(archive, c, with_audio=False)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename == "catalog.json":
                raw = json.dumps({"songs": ["x"], "collections": [{"songs": []}]}).encode()
            dst.writestr(info, raw)
    with pytest.raises(backup.BackupError):
        backup.restore(broken, c)


def test_a_locked_catalog_is_not_taken_for_a_damaged_one(data, monkeypatch):
    c, _ = open_catalog(data)
    c.close()
    real = catalog.Catalog.check

    def locked(self):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(catalog.Catalog, "check", locked)
    c2, note = open_catalog(data)
    assert "ne s'ouvre pas" in note
    assert (data / "catalog.db").exists() and not list(data.glob("catalog-*.illisible"))
    monkeypatch.setattr(catalog.Catalog, "check", real)
    c2.close()
