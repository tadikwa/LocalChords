"""Looking for lyrics online, only when asked: LRCLIB (https://lrclib.net), a free community
database with no key. Only the title, artist, album and duration are sent, never the audio.

LRCLIB states no licence for the lyrics it serves: they are shown, attributed and kept in the
project, never exported (lyrics.exportable). docs/TECHNIQUE.md says why.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from . import lyrics as L

API = "https://lrclib.net/api"
NAME = "LRCLIB (lrclib.net), base de paroles communautaire"
USER_AGENT = f"LocalChords/{__version__} (https://github.com/tadikwa/LocalChords)"
TIMEOUT = 12


class OnlineError(Exception):
    pass


def _get(path: str, params: dict, opener=urllib.request.urlopen) -> object | None:
    """JSON from the API; None for "not found"."""
    url = f"{API}/{path}?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code == 429:
            wait = exc.headers.get("Retry-After") if exc.headers else None
            raise OnlineError(
                "LRCLIB reçoit trop de demandes"
                + (f" : réessayez dans {wait} s." if wait else " : réessayez dans un moment.")
            ) from exc
        raise OnlineError(f"LRCLIB a répondu par une erreur ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OnlineError("Pas de réponse de LRCLIB : vérifiez la connexion à Internet.") from exc
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise OnlineError("LRCLIB a renvoyé une réponse illisible.") from exc


def search(
    title: str,
    artist: str = "",
    album: str = "",
    duration: float = 0.0,
    opener=urllib.request.urlopen,
) -> list[dict]:
    """Candidates, the closest in duration first. Nothing here says one is the right one."""
    if not title.strip():
        raise OnlineError("Indiquez au moins le titre du morceau.")
    found: dict[int, dict] = {}
    if artist and 1 <= duration <= 3600:
        exact = _get(
            "get",
            {
                "track_name": title,
                "artist_name": artist,
                "album_name": album,
                "duration": round(duration),
            },
            opener,
        )
        if isinstance(exact, dict) and "id" in exact:
            found[exact["id"]] = exact
    hits = _get("search", {"track_name": title, "artist_name": artist}, opener)
    if not hits and artist:  # a misspelled artist: try the words alone
        hits = _get("search", {"q": f"{title} {artist}"}, opener)
    for r in hits if isinstance(hits, list) else []:
        if isinstance(r, dict) and "id" in r:
            found.setdefault(r["id"], r)
    out = [
        r
        for r in found.values()
        if r.get("plainLyrics") or r.get("syncedLyrics") or r.get("instrumental")
    ]

    def gap(r):
        return abs(float(r.get("duration") or 0) - duration) if duration else 0.0

    return sorted(out, key=lambda r: (gap(r), not r.get("syncedLyrics")))


def lines_of(record: dict, synced: bool = True) -> list[dict]:
    """The lines; synced=False keeps the words without their times, for another recording."""
    if synced and record.get("syncedLyrics"):
        return L.parse(record["syncedLyrics"])
    if record.get("plainLyrics"):
        return L.parse(record["plainLyrics"])
    return [
        {**x, "start": None}
        for x in L.parse(record.get("syncedLyrics") or "")
        if x["text"] or x.get("section")
    ]


def source_of(record: dict, synced: bool) -> dict:
    return {
        "kind": "catalog",
        "name": NAME,
        "id": record.get("id"),
        "url": f"{API}/get/{record.get('id')}",
        "title": record.get("trackName") or "",
        "artist": record.get("artistName") or "",
        "album": record.get("albumName") or "",
        "duration": record.get("duration"),
        "synced": bool(synced and record.get("syncedLyrics")),
        "exportable": False,
    }
