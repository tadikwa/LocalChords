"""The library (v1.4): an index of the analyzed songs, and what the user adds to them.

The projects in `projects/` stay the truth about each song. This index (`catalog.db`, SQLite from
Python's standard library) is rebuilt from them when it is lost, and never changes them. What no
project holds, the favourites, genres, tags, collections and the dates of adding and opening, lives
here only: it is copied aside once a day (`backups/`) and goes into a library backup (backup.py).
docs/TECHNIQUE.md#la-bibliothèque-v14 explains the choices.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

from . import library
from .project import EXTENSION, Project, ProjectError

FILE = "catalog.db"
BACKUPS = "backups"
KEEP_BACKUPS = 7
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id TEXT PRIMARY KEY,                -- the project's file name without .lchords
    file TEXT NOT NULL,
    mtime REAL, size INTEGER,           -- the project file when last read
    project_state TEXT NOT NULL DEFAULT 'ok',   -- ok, missing, unreadable
    title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '', album TEXT NOT NULL DEFAULT '',
    year INTEGER, file_genre TEXT, duration REAL, key TEXT, bpm REAL, chords INTEGER,
    lyrics TEXT,                        -- where the lyrics come from, NULL without lyrics
    audio_path TEXT NOT NULL DEFAULT '', kept TEXT, audio_size INTEGER, source_url TEXT,
    analyzed INTEGER NOT NULL DEFAULT 0,
    audio_state TEXT NOT NULL DEFAULT 'unknown',  -- kept, ok, offline, missing, unknown
    tags_read INTEGER NOT NULL DEFAULT 0,         -- genre and year looked for in the audio's tags
    genre TEXT,                         -- the user's: NULL for the file's, '' for none
    favorite INTEGER NOT NULL DEFAULT 0,
    added_at REAL, added_estimated INTEGER NOT NULL DEFAULT 0,
    opened_at REAL, opened_estimated INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0   -- taken out of the catalog, its project kept
);
CREATE TABLE IF NOT EXISTS tags (
    id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    tag TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (id, tag)
);
CREATE TABLE IF NOT EXISTS collections (
    cid INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    cid INTEGER NOT NULL REFERENCES collections(cid) ON DELETE CASCADE,
    id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    position REAL NOT NULL,
    PRIMARY KEY (cid, id)
);
"""
PERSONAL = ("favorite", "genre", "added_at", "added_estimated", "opened_at", "opened_estimated",
            "hidden")  # fmt: skip
GENRES = ("Pop", "Rock", "Variété française", "Chanson", "Jazz", "Blues", "Folk", "Classique",
          "Musique de film", "Électro", "Hip-hop", "Reggae", "Soul", "Country", "Métal",
          "Musiques du monde")  # fmt: skip
TAGS = ("Piano", "Guitare", "À apprendre", "À retravailler", "Maîtrisé")
SORTS = {
    "opened": "Dernière ouverture", "added": "Date d'ajout", "title": "Titre", "artist": "Artiste",
    "year": "Année", "genre": "Genre", "key": "Tonalité", "bpm": "Tempo", "duration": "Durée",
}  # fmt: skip
LATEST = 50  # songs in the "recently opened" and "latest added" views


class CatalogError(Exception):
    """The catalog could not be read or written; the message is written for the user."""


def folded(text: str | None) -> str:
    """For search and sort: no case, no accents (« Été » finds « ete »)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def year_of(value) -> int | None:
    """A song's year from a tag such as 2019, "2019-05-01" or "05/2019"."""
    found = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(value or ""))
    return int(found.group(1)) if found else None


def facts(project: Project) -> dict:
    """What the library shows of a project, as the song page shows it: the key and tempo after
    the user's corrections, nothing for what an unanalyzed song cannot say."""
    a = project.audio
    segments = project.segments() if project.analysis["segments"] else []
    key = project.key() if segments else None
    bpm = project.tempo().get("bpm") if segments else None
    lyrics = project.lyrics if project.lyrics and project.lyrics.get("lines") else None
    return {
        "title": a.get("title") or Path(a.get("path") or "").stem,
        "artist": a.get("artist") or "",
        "album": a.get("album") or "",
        "year": year_of(a.get("year")),
        "file_genre": (a.get("genre") or "").strip() or None,
        "duration": float(a.get("duration") or 0) or None,
        "key": key.get("label") if key else None,
        "bpm": bpm,
        "chords": len({s.chord for s in segments if s.chord != "N"}) if segments else None,
        "lyrics": (lyrics["source"].get("kind") or "user") if lyrics else None,
        "audio_path": a.get("path") or "",
        "kept": a.get("kept") or None,
        "audio_size": a.get("size"),
        "source_url": a.get("source_url"),
        "analyzed": int(bool(segments)),
        # A project made by v1.4 already read the tags: "" there means the file has none.
        "tags_read": int("genre" in a or "year" in a),
    }


def audio_state(path_text: str, kept: str | None, roots: dict | None = None) -> str:
    """kept (a copy LocalChords keeps), ok (the original is there), offline (its drive or network
    share is not connected: maybe it comes back), missing. roots caches each drive's answer, for a
    disconnected share not to be waited on once per song."""
    data = library.data_dir()
    if kept and (data / kept).is_file():
        return "kept"
    path = Path(path_text or "")
    if path_text and path.is_file():
        return "kept" if library.managed(path) else "ok"
    if path.parent.name == "downloads" and path.name and (data / "downloads" / path.name).is_file():
        return "kept"
    root = path.anchor
    if root:
        roots = {} if roots is None else roots
        if root not in roots:
            roots[root] = Path(root).exists()
        if not roots[root]:
            return "offline"
    return "missing"


def _created(st: os.stat_result) -> float:
    """When a file was made: st_birthtime where the system keeps it, else Windows' st_ctime."""
    return getattr(st, "st_birthtime", None) or st.st_ctime


def _nocase(a: str, b: str) -> int:
    a, b = a.casefold(), b.casefold()
    return (a > b) - (a < b)


class Catalog:
    def __init__(self, path: Path | str):
        self.path = path
        self.db = sqlite3.connect(str(path), timeout=10)
        try:
            self.db.row_factory = sqlite3.Row
            # SQLite's own NOCASE folds only A-Z: « À apprendre » and « à apprendre » are one tag.
            self.db.create_collation("NOCASE", _nocase)
            self.db.execute("PRAGMA foreign_keys = ON")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise CatalogError("La bibliothèque vient d'une version plus récente de LocalChords.")
            with self.db:
                self.db.executescript(SCHEMA)
                self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except BaseException:
            self.db.close()  # else Windows keeps the damaged file locked and it cannot be set aside
            raise

    def close(self) -> None:
        self.db.close()

    def check(self) -> None:
        """Raises sqlite3.DatabaseError on a damaged file."""
        result = self.db.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise sqlite3.DatabaseError(result)

    def _write(self, sql: str, params=()) -> None:
        try:
            with self.db:
                self.db.execute(sql, params)
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as exc:
            raise CatalogError(f"La bibliothèque n'a pas pu être enregistrée : {exc}") from exc

    def _many(self, sql: str, rows) -> None:
        try:
            with self.db:
                self.db.executemany(sql, rows)
        except sqlite3.Error as exc:
            raise CatalogError(f"La bibliothèque n'a pas pu être enregistrée : {exc}") from exc

    # Reading -----------------------------------------------------------------------------------
    def songs(self) -> list[dict]:
        """Every song, its tags as a list and its genre as shown (the user's, else the file's)."""
        tags: dict[str, list[str]] = {}
        for row in sorted(self.db.execute("SELECT id, tag FROM tags"), key=lambda r: folded(r[1])):
            tags.setdefault(row[0], []).append(row[1])
        out = []
        for row in self.db.execute("SELECT * FROM songs"):
            song = dict(row)
            song["tags"] = tags.get(song["id"], [])
            shown = song["genre"] if song["genre"] is not None else song["file_genre"]
            song["shown_genre"] = shown or None
            out.append(song)
        return out

    def song(self, sid: str) -> dict | None:
        return next((s for s in self.songs() if s["id"] == sid), None)

    def ids(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT id FROM songs")}

    def tags(self) -> list[str]:
        return sorted({r[0] for r in self.db.execute("SELECT tag FROM tags GROUP BY tag")}, key=folded)

    def genres(self) -> list[str]:
        return sorted({s["shown_genre"] for s in self.songs() if s["shown_genre"]}, key=folded)

    def collections(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.cid, c.name, c.created_at, COUNT(m.id) AS count FROM collections c "
            "LEFT JOIN members m ON m.cid = c.cid GROUP BY c.cid"
        )
        return sorted((dict(r) for r in rows), key=lambda c: folded(c["name"]))

    def members(self, cid: int) -> list[str]:
        rows = self.db.execute("SELECT id FROM members WHERE cid = ? ORDER BY position", (cid,))
        return [r[0] for r in rows]

    def collections_of(self, sid: str) -> list[int]:
        return [r[0] for r in self.db.execute("SELECT cid FROM members WHERE id = ?", (sid,))]

    def find_url(self, url: str) -> dict | None:
        """A song imported from this link before, whose audio LocalChords still keeps."""
        for song in self.songs():
            if url and song["source_url"] == url and song["project_state"] == "ok":
                if audio_state(song["audio_path"], song["kept"]) in ("kept", "ok"):
                    return song
        return None

    # The projects ------------------------------------------------------------------------------
    def store(self, file: Path, project: Project | None, *, opened: bool = False,
              estimated: bool = False) -> None:  # fmt: skip
        """Index a project file (None: one that cannot be read). A new one counts as added now, or,
        estimated, when its file was made: what a project from before v1.4 can tell."""
        st = file.stat()
        now = time.time()
        # An unreadable project (damaged, or from a newer version) keeps what was known of it.
        f = facts(project) if project else {}
        if project:  # a scan checks the audio afterwards, every drive once
            f["audio_state"] = "unknown" if estimated else audio_state(f["audio_path"], f["kept"])
        f |= {"file": file.name, "mtime": st.st_mtime, "size": st.st_size}
        f["project_state"] = "ok" if project else "unreadable"
        # Only for a song new to the index: the dates, and a title for an unreadable project.
        new = {
            "added_at": _created(st) if estimated else now,
            "added_estimated": int(estimated),
            "opened_at": (st.st_mtime if estimated else now) if (opened or estimated) else None,
            "opened_estimated": int(estimated),
        }
        if not project:
            new["title"] = file.stem
        names = list(f)
        update = ", ".join(f"{n} = excluded.{n}" for n in names)
        if opened:
            update += ", opened_at = excluded.opened_at, opened_estimated = 0, hidden = 0"
        columns = ["id", *names, *new]
        self._write(
            f"INSERT INTO songs ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) "
            f"ON CONFLICT(id) DO UPDATE SET {update}",
            [file.stem, *f.values(), *new.values()],
        )

    def opened(self, sid: str) -> None:
        self._write(
            "UPDATE songs SET opened_at = ?, opened_estimated = 0, hidden = 0 WHERE id = ?",
            (time.time(), sid),
        )

    def scan(self, folder: Path, *, progress=None, stop=None) -> dict:
        """Bring the index up to the projects in folder: read those new or changed since, mark the
        missing (never forget them: a project may come back), then check every song's audio.
        Returns {read, missing, total}."""
        try:
            files = {p.stem: p for p in folder.glob(f"*{EXTENSION}")} if folder.is_dir() else {}
            stats = {sid: p.stat() for sid, p in files.items()}
        except OSError as exc:
            raise CatalogError(f"Le dossier des projets ne se lit pas : {exc}") from exc
        known = {r["id"]: r for r in self.db.execute("SELECT id, mtime, size, project_state FROM songs")}
        changed = [
            sid
            for sid, st in stats.items()
            if sid not in known
            or known[sid]["project_state"] != "ok"
            or (known[sid]["mtime"], known[sid]["size"]) != (st.st_mtime, st.st_size)
        ]
        for i, sid in enumerate(changed):
            if stop and stop():
                break
            try:
                project = Project.load(files[sid])
            except ProjectError:
                project = None
            try:
                self.store(files[sid], project, estimated=sid not in known)
            except OSError:
                continue  # gone meanwhile: the next scan sees it
            if progress:
                progress(i + 1, len(changed))
        gone = [sid for sid in known if sid not in files]
        self._many("UPDATE songs SET project_state = 'missing' WHERE id = ?", [(s,) for s in gone])
        self.check_audio(stop=stop)
        return {"read": len(changed), "missing": len(gone), "total": len(files)}

    def check_audio(self, ids=None, stop=None) -> None:
        """Where each song's recording is now, and, once, the genre and year in its tags."""
        from . import audio

        roots: dict = {}
        rows = self.db.execute(
            "SELECT id, audio_path, kept, audio_state, tags_read, file_genre, year FROM songs"
        ).fetchall()
        for row in rows:
            if (ids is not None and row["id"] not in ids) or (stop and stop()):
                continue
            state = audio_state(row["audio_path"], row["kept"], roots)
            changes = {"audio_state": state} if state != row["audio_state"] else {}
            if state in ("ok", "kept") and not row["tags_read"]:
                path = library.audio_file({"path": row["audio_path"], "kept": row["kept"]})
                changes["tags_read"] = 1
                try:
                    info = audio.metadata(path)
                    changes["audio_size"] = path.stat().st_size
                except (audio.AudioError, OSError):
                    info = {}
                if not row["file_genre"] and info.get("genre"):
                    changes["file_genre"] = info["genre"]
                if not row["year"] and year_of(info.get("date")):
                    changes["year"] = year_of(info.get("date"))
            if changes:
                sets = ", ".join(f"{k} = ?" for k in changes)
                self._write(f"UPDATE songs SET {sets} WHERE id = ?", [*changes.values(), row["id"]])

    def set_audio(self, sid: str, path: str, kept: str | None) -> None:
        self._write(
            "UPDATE songs SET audio_path = ?, kept = ?, audio_state = ? WHERE id = ?",
            (path, kept, audio_state(path, kept), sid),
        )

    # What the user adds ------------------------------------------------------------------------
    def set_favorite(self, ids, on: bool) -> None:
        self._many("UPDATE songs SET favorite = ? WHERE id = ?", [(int(on), s) for s in ids])

    def set_genre(self, ids, genre: str | None) -> None:
        """None: back to the file's genre; "": none, whatever the file says."""
        value = genre.strip() if genre else genre
        self._many("UPDATE songs SET genre = ? WHERE id = ?", [(value, s) for s in ids])

    def add_tag(self, ids, tag: str) -> None:
        tag = tag.strip()
        if tag:
            self._many("INSERT OR IGNORE INTO tags (id, tag) VALUES (?, ?)", [(s, tag) for s in ids])

    def remove_tag(self, ids, tag: str) -> None:
        self._many("DELETE FROM tags WHERE id = ? AND tag = ?", [(s, tag) for s in ids])

    def hide(self, ids, on: bool = True) -> None:
        """Out of the catalog (on) or back in; the project and the audio stay where they are."""
        self._many("UPDATE songs SET hidden = ? WHERE id = ?", [(int(on), s) for s in ids])

    def forget(self, sid: str) -> None:
        """After its project was deleted: the song, its tags and its places in collections."""
        self._write("DELETE FROM songs WHERE id = ?", (sid,))

    # Collections -------------------------------------------------------------------------------
    def create_collection(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise CatalogError("Une collection a besoin d'un nom.")
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO collections (name, created_at) VALUES (?, ?)", (name, time.time())
                )
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Une collection s'appelle déjà « {name} ».") from exc
        except sqlite3.Error as exc:
            raise CatalogError(f"La bibliothèque n'a pas pu être enregistrée : {exc}") from exc
        return int(cur.lastrowid)

    def rename_collection(self, cid: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise CatalogError("Une collection a besoin d'un nom.")
        try:
            self._write("UPDATE collections SET name = ? WHERE cid = ?", (name, cid))
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Une collection s'appelle déjà « {name} ».") from exc

    def delete_collection(self, cid: int) -> None:
        """The collection only: its songs stay in the library."""
        self._write("DELETE FROM collections WHERE cid = ?", (cid,))

    def add_to_collection(self, cid: int, ids) -> None:
        """At the end, in the order given; a song already there keeps its place."""
        last = self.db.execute(
            "SELECT COALESCE(MAX(position), -1) FROM members WHERE cid = ?", (cid,)
        ).fetchone()[0]
        rows = [(cid, s, last + 1 + i) for i, s in enumerate(ids)]
        self._many("INSERT OR IGNORE INTO members (cid, id, position) VALUES (?, ?, ?)", rows)

    def remove_from_collection(self, cid: int, ids) -> None:
        self._many("DELETE FROM members WHERE cid = ? AND id = ?", [(cid, s) for s in ids])

    def reorder(self, cid: int, ids: list[str]) -> None:
        """The collection's songs in this order; any left out keep their order after them."""
        rest = [s for s in self.members(cid) if s not in ids]
        rows = [(i, cid, s) for i, s in enumerate([*ids, *rest])]
        self._many("UPDATE members SET position = ? WHERE cid = ? AND id = ?", rows)

    # Keeping it safe ---------------------------------------------------------------------------
    def personal(self, ids=None) -> dict:
        """What only the catalog holds, for a library backup: by song, and the collections."""
        keep = set(ids) if ids is not None else None
        songs = [
            {"id": s["id"], **{k: s[k] for k in PERSONAL}, "tags": s["tags"]}
            for s in self.songs()
            if keep is None or s["id"] in keep
        ]
        collections = [
            {
                "name": c["name"],
                "created_at": c["created_at"],
                "songs": [s for s in self.members(c["cid"]) if keep is None or s in keep],
            }
            for c in self.collections()
        ]
        return {"songs": songs, "collections": collections}

    def merge_personal(self, data: dict) -> None:
        """A backup's personal data over this catalog's, losing none of either: favourites and
        tags join, the earliest adding and latest opening win, a genre set here stays, collections
        of the same name merge. Songs not indexed here are skipped. One transaction."""
        here = {s["id"]: s for s in self.songs()}
        try:
            with self.db:
                for song in data.get("songs", []):
                    mine = here.get(song.get("id"))
                    if mine is None:
                        continue
                    added = [x for x in (mine["added_at"], song.get("added_at")) if x]
                    first = min(added) if added else None
                    exact = [
                        x
                        for x, est in ((mine["added_at"], mine["added_estimated"]),
                                       (song.get("added_at"), song.get("added_estimated")))
                        if x and not est
                    ]  # fmt: skip
                    opened = [x for x in (mine["opened_at"], song.get("opened_at")) if x]
                    last = max(opened) if opened else None
                    self.db.execute(
                        "UPDATE songs SET favorite = ?, genre = ?, added_at = ?, "
                        "added_estimated = ?, opened_at = ?, opened_estimated = ? WHERE id = ?",
                        (
                            int(bool(mine["favorite"] or song.get("favorite"))),
                            mine["genre"] if mine["genre"] is not None else song.get("genre"),
                            min(exact) if exact else first,
                            0 if exact else int(bool(first)),
                            last,
                            int(last == mine["opened_at"] and bool(mine["opened_estimated"]))
                            if last
                            else 0,
                            mine["id"],
                        ),
                    )
                    for tag in song.get("tags", []):
                        self.db.execute(
                            "INSERT OR IGNORE INTO tags (id, tag) VALUES (?, ?)", (mine["id"], tag)
                        )
                for c in data.get("collections", []):
                    row = self.db.execute(
                        "SELECT cid FROM collections WHERE name = ?", (c["name"],)
                    ).fetchone()
                    if row:
                        cid = row[0]
                    else:
                        cid = self.db.execute(
                            "INSERT INTO collections (name, created_at) VALUES (?, ?)",
                            (c["name"], c.get("created_at") or time.time()),
                        ).lastrowid
                    last = self.db.execute(
                        "SELECT COALESCE(MAX(position), -1) FROM members WHERE cid = ?", (cid,)
                    ).fetchone()[0]
                    for i, sid in enumerate(s for s in c.get("songs", []) if s in here):
                        self.db.execute(
                            "INSERT OR IGNORE INTO members (cid, id, position) VALUES (?, ?, ?)",
                            (cid, sid, last + 1 + i),
                        )
        except sqlite3.Error as exc:
            raise CatalogError(f"La bibliothèque n'a pas pu être enregistrée : {exc}") from exc

    def backup_daily(self, folder: Path, keep: int = KEEP_BACKUPS) -> Path | None:
        """A copy of the catalog for today, if none yet, the oldest beyond keep removed. An empty
        catalog is not copied: it would push out the copies that hold something."""
        if not self.db.execute("SELECT 1 FROM songs LIMIT 1").fetchone():
            return None
        target = folder / f"catalog-{time.strftime('%Y-%m-%d')}.db"
        if target.exists():
            return None
        folder.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        copy = sqlite3.connect(str(tmp))
        try:
            self.db.backup(copy)
        finally:
            copy.close()
        os.replace(tmp, target)
        for old in sorted(folder.glob("catalog-*.db"))[:-keep]:
            old.unlink(missing_ok=True)
        return target


def open_catalog(data: Path) -> tuple[Catalog, str | None]:
    """The catalog of this Data folder, and what the user should know about how it was opened.

    A damaged file is set aside (never deleted) and the newest readable daily copy takes its
    place; the next scan brings the songs up to date. A folder that cannot be written, or a
    catalog from a newer version, gives a catalog in memory for this session.
    """
    path = data / FILE
    problem = library.unwritable(data)
    if problem:
        return Catalog(":memory:"), (
            f"La bibliothèque ne peut pas être enregistrée ici ({problem}) : favoris et collections "
            "seront oubliés à la fermeture."
        )
    try:
        catalog = Catalog(path)
        catalog.check()
        return catalog, None
    except CatalogError as exc:
        return Catalog(":memory:"), f"{exc} Elle n'est pas modifiée ; rien ne sera retenu."
    except sqlite3.DatabaseError:
        pass
    stamp = time.strftime("%Y%m%d-%H%M%S")
    aside = path.with_name(f"catalog-{stamp}.illisible")
    try:
        path.replace(aside)
        path.with_name(FILE + "-journal").unlink(missing_ok=True)
    except OSError:
        return Catalog(":memory:"), "La bibliothèque est endommagée et ne peut être remplacée."
    for copy in sorted((data / BACKUPS).glob("catalog-*.db"), reverse=True):
        try:
            path.write_bytes(copy.read_bytes())
            catalog = Catalog(path)
            catalog.check()
        except (OSError, sqlite3.DatabaseError, CatalogError):
            path.unlink(missing_ok=True)
            continue
        day = copy.stem.removeprefix("catalog-")
        return catalog, (
            f"L'index de la bibliothèque était endommagé ; il a été remis en place depuis sa copie "
            f"du {day} et mis à jour d'après les projets. L'ancien fichier est gardé : {aside.name}."
        )
    return Catalog(path), (
        "L'index de la bibliothèque était endommagé et n'avait pas de copie lisible : il est "
        "reconstruit d'après les projets, sans les favoris, étiquettes et collections. "
        f"L'ancien fichier est gardé : {aside.name}. Une sauvegarde de bibliothèque peut les rendre."
    )


# Showing it ------------------------------------------------------------------------------------
def _key_order(label: str | None):
    from .chords import transpose_key

    parsed = transpose_key(label, 0)
    return None if parsed is None else (parsed[1] != "maj", parsed[0])


def _sort_value(song: dict, sort: str):
    if sort == "title":
        return folded(song["title"])
    if sort == "artist":
        return (folded(song["artist"]), folded(song["title"])) if song["artist"] else None
    if sort == "added":
        return song["added_at"]
    if sort == "opened":
        return song["opened_at"]
    if sort == "genre":
        return folded(song["shown_genre"]) if song["shown_genre"] else None
    if sort == "key":
        return _key_order(song["key"])
    return song.get(sort)  # year, bpm, duration


def matches(song: dict, words: list[str]) -> bool:
    text = " ".join(
        [song["title"], song["artist"], song["album"], song["shown_genre"] or "", *song["tags"],
         str(song["year"] or "")]
    )  # fmt: skip
    hay = folded(text)
    return all(w in hay for w in words)


def arrange(
    songs: list[dict],
    *,
    query: str = "",
    sort: str = "title",
    descending: bool = False,
    genre: str | None = None,
    tag: str | None = None,
    state: str | None = None,
    order: list[str] | None = None,
) -> list[dict]:
    """The songs a view shows: searched, filtered, sorted. A song with no value for the sort comes
    last either way, by title; order (a collection's) replaces the sort when given.

    genre "" keeps the songs without one; state is lyrics, nolyrics, missing or kept."""
    words = folded(query).split()
    keep = []
    for s in songs:
        if words and not matches(s, words):
            continue
        if genre is not None and (s["shown_genre"] or "") != genre:
            continue
        if tag is not None and folded(tag) not in {folded(t) for t in s["tags"]}:
            continue
        if state == "lyrics" and not s["lyrics"] or state == "nolyrics" and s["lyrics"]:
            continue
        if state == "missing" and s["audio_state"] not in ("missing", "offline"):
            continue
        if state == "kept" and s["audio_state"] != "kept":
            continue
        keep.append(s)
    if order is not None:
        place = {sid: i for i, sid in enumerate(order)}
        return sorted((s for s in keep if s["id"] in place), key=lambda s: place[s["id"]])
    known = [s for s in keep if _sort_value(s, sort) is not None]
    unknown = [s for s in keep if _sort_value(s, sort) is None]
    known.sort(key=lambda s: folded(s["title"]))
    known.sort(key=lambda s: _sort_value(s, sort), reverse=descending)
    unknown.sort(key=lambda s: folded(s["title"]))
    return known + unknown
