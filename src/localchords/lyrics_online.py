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
from difflib import SequenceMatcher

from . import __version__, identify
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


# Choosing among the candidates, for a suggestion made without being asked -------------------------

SURE = 0.85  # a suggestion offered as it is: names that match and no other version close behind
PLAUSIBLE = 0.6  # below: not offered at all, another song's lyrics would be worse than none
CLOSE = 0.06  # another candidate within this, with other lyrics: the user chooses
_JOIN = {"and", "et", "feat", "ft", "featuring", "with", "avec", "x", "vs"}  # folded "&" is "and"


def _like(a: str, b: str, artists: bool = False) -> float:
    a, b = identify.fold(identify.clean_title(a)), identify.fold(identify.clean_title(b))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # "Artist" against "Artist & Friend": one of the names credited, joined by "&", "feat."…
    # Not "Queen" against "Queen Latifah", nor for titles: "Song" and "Song Two" are other songs.
    short, long_ = sorted((a.split(), b.split()), key=len)
    n = len(short)
    if artists and (
        (long_[:n] == short and long_[n] in _JOIN)
        or (long_[-n:] == short and long_[-n - 1] in _JOIN)
    ):
        ratio = max(ratio, 0.85)
    return ratio


def score(record: dict, title: str, artist: str, album: str, duration: float) -> float:
    """How likely a record is the recording described: 0 to 1. A duration alone proves nothing,
    so it weighs little next to the names."""
    t = _like(record.get("trackName") or "", title)
    a = _like(record.get("artistName") or "", artist, True) if artist else 0.0
    s = 0.5 * t + 0.35 * a
    if duration and record.get("duration"):
        gap = abs(float(record["duration"]) - duration)
        s += 0.1 if gap <= 2 else 0.07 if gap <= 5 else 0.02 if gap <= 15 else -0.1
    if album and record.get("albumName") and _like(record["albumName"], album) > 0.9:
        s += 0.03
    if record.get("syncedLyrics"):
        s += 0.02
    # "Song (Live)" for a studio recording, or the other way round: another performance.
    if identify.is_version(record.get("trackName") or "") != identify.is_version(title):
        s -= 0.2
    return round(min(s, 1.0), 3)


def _text(record: dict) -> str:
    words = record.get("plainLyrics") or L.to_text(
        {"lines": L.parse(record.get("syncedLyrics") or ""), "offset": 0}
    )
    return identify.fold(words)[:400]


def suggest(records: list[dict], identity: dict, duration: float) -> dict:
    """{"verdict": "sure" | "choose" | "none", "candidates": [records, best first],
    "synced": whether the best one's times may be used}. Never sure on a duration alone, nor
    when another version with other lyrics comes close."""
    title, artist, album = identity["title"], identity["artist"], identity.get("album", "")
    swap = identity.get("how") in ("title", "filename") and not identity.get("sure")
    scored = []
    for r in records:
        if r.get("instrumental") or not (r.get("plainLyrics") or r.get("syncedLyrics")):
            continue
        s = score(r, title, artist, album, duration)
        if swap:  # "Title - Artist" read the wrong way round
            s = max(s, score(r, artist, title, album, duration))
        if s >= PLAUSIBLE:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    candidates = [r for _s, r in scored[:6]]
    if not scored:
        return {"verdict": "none", "candidates": [], "synced": False}
    best_s, best = scored[0]
    rival = any(best_s - s < CLOSE and _text(r) != _text(best) for s, r in scored[1:])
    gap = abs(float(best.get("duration") or 0) - duration) if duration else None
    # Times from another performance would not fall right: the words are kept, not the times.
    version = identify.is_version(
        title, identity.get("video_title", ""), best.get("trackName") or ""
    )
    synced = bool(best.get("syncedLyrics")) and not version and (gap is None or gap <= 3)
    sure = best_s >= SURE and not rival and (gap is None or gap <= 5)
    return {"verdict": "sure" if sure else "choose", "candidates": candidates, "synced": synced}


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
