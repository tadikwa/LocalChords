"""What song a recording is, from what it already says about itself: the music fields yt-dlp
reads on the site, the file's tags, then its title or name. Nothing is listened to.

Every answer says how it was reached ("how") and whether it can be taken as it is ("sure"): a
title split at its dash is a guess, and the uploader's channel is never taken for the artist
unless the site says it is the artist's own channel.
"""

from __future__ import annotations

import re
import unicodedata

# The fields of yt-dlp's info dict worth keeping; the rest (formats, thumbnails…) is dropped.
INFO_KEYS = (
    "id",
    "title",
    "track",
    "artist",
    "artists",
    "creator",
    "creators",
    "album",
    "album_artist",
    "duration",
    "channel",
    "uploader",
    "release_year",
    "webpage_url",
)

# Words a video adds to a song's title: they say nothing about the song.
_NOISE = re.compile(
    r"\s*[\(\[【][^\)\]】]*\b(official|officiel|officielle|clip|video|vidéo|audio|lyrics?|"
    r"paroles|visuali[sz]er|hd|hq|4k|remaster(ed)?|mv|m/v)\b[^\)\]】]*[\)\]】]",
    re.IGNORECASE,
)
# "… [dQw4w9WgXcQ]" from the download; a plain word such as "[Acoustic]" is the title's own.
_ID_TAIL = re.compile(r"\s*\[(?![A-Z]?[a-z]+\]|[A-Z]+\])[A-Za-z0-9_-]{6,20}\]\s*$")
_SEPARATORS = re.compile(r"\s+[-–—|:]\s+|\s+[-–—]|[-–—]\s+")
_FEAT = re.compile(r"\s*[\(\[]?\b(feat\.?|ft\.?|featuring)\s.*$", re.IGNORECASE)
_TOPIC = re.compile(r"\s*-\s*(topic|thème)$", re.IGNORECASE)  # YouTube's channels of an artist
_VEVO = re.compile(r"vevo$", re.IGNORECASE)
# Another performance than the studio one: its times are not the original's.
VERSION_WORDS = re.compile(
    r"\b(live|en concert|en public|concert|cover|reprise|acoustic|acoustique|unplugged|"
    r"remix|karaoke|karaoké|instrumental|version|session|demo|démo|edit)\b",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    """For comparing names: no accents, no case, no punctuation, single spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"[^\w]+", " ", text.replace("&", " and "))
    return " ".join(text.split())


def clean_title(text: str) -> str:
    """A video's or file's title without its id, its "(Official Video)" and the like."""
    text = _ID_TAIL.sub("", text or "")
    text = _NOISE.sub("", text)
    text = re.sub(r"\s*\|.*$", "", text)  # "Song | Channel's name"
    text = text.replace("_", " ")
    return " ".join(text.split()).strip(" -–—")


def split_title(text: str) -> tuple[str, str] | None:
    """(artist, title) when the title reads "Artist - Title", once and only once."""
    parts = [p.strip() for p in _SEPARATORS.split(clean_title(text)) if p.strip()]
    if len(parts) != 2:
        return None
    artist, title = parts
    if not re.search(r"\w", artist) or not re.search(r"\w", title) or len(artist) > 60:
        return None
    return artist, title


def _channel_artist(channel: str) -> str:
    """The artist a channel stands for, only when the site says so ("Artist - Topic")."""
    if _TOPIC.search(channel or ""):
        return _TOPIC.sub("", channel).strip()
    return ""


def _same(a: str, b: str) -> bool:
    a, b = fold(a).replace(" ", ""), fold(_VEVO.sub("", b or "")).replace(" ", "")
    return bool(a and b) and (a == b or (len(b) >= 4 and (a in b or b in a)))


def _result(title, artist="", album="", how="none", sure=False, **extra) -> dict:
    return {
        "title": title or "",
        "artist": artist or "",
        "album": album or "",
        "how": how,
        "sure": bool(sure),
        **extra,
    }


def from_info(info: dict) -> dict:
    """From the fields yt-dlp read on the site (INFO_KEYS)."""
    video = info.get("title") or ""
    channel = info.get("channel") or info.get("uploader") or ""
    hints = {"video_title": video, "channel": channel}
    artists = info.get("artists") or info.get("creators") or []
    artist = info.get("artist") or (", ".join(artists) if artists else "") or info.get("creator")
    track = info.get("track") or ""
    album = info.get("album") or ""
    split = split_title(video)
    by_channel = _channel_artist(channel)
    if track:  # the site's own music fields ("Music in this video"), the most reliable
        if artist:
            return _result(track, artist, album, "music", True, **hints)
        # No artist field: the channel's, else the title's when it names the same track.
        guess = by_channel or (split[0] if split and fold(split[1]) == fold(track) else "")
        return _result(track, guess, album, "music", bool(by_channel), **hints)
    if split:
        a, t = split
        # The channel agrees with the title: the artist's own channel posted it.
        sure = _same(a, channel) or _same(a, by_channel)
        return _result(t, a, album, "title", sure, **hints)
    title = clean_title(video)
    if by_channel:  # "Artist - Topic" posting "Song": YouTube's own artist channel
        return _result(title, by_channel, album, "channel", True, **hints)
    return _result(title, "", album, "title" if title else "none", False, **hints)


def from_file(tags: dict, stem: str) -> dict:
    """From a file's tags (audio.metadata), then from its name."""
    title, artist = tags.get("title") or "", tags.get("artist") or ""
    if not artist and tags.get("album_artist"):
        artist = tags["album_artist"]
    album = tags.get("album") or ""
    if title:
        split = None if artist else split_title(title)  # "Artist - Title" written in the title
        if split:
            return _result(split[1], split[0], album, "tags", False)
        return _result(clean_title(title), artist, album, "tags", bool(artist))
    split = split_title(stem)
    if split:
        return _result(split[1], split[0], album, "filename", False)
    name = clean_title(stem)
    return _result(name, artist, album, "filename" if name else "none", False)


def is_version(*texts: str) -> bool:
    """Whether a title names a live, a cover, a remix… rather than the studio recording."""
    return any(VERSION_WORDS.search(_FEAT.sub("", t or "")) for t in texts)


def searchable(identity: dict) -> bool:
    """Enough to ask a catalog without risking another song's lyrics: a title and an artist."""
    return bool(identity.get("title", "").strip() and identity.get("artist", "").strip())


def keep(info: dict) -> dict:
    """The part of yt-dlp's info dict that crosses from the download process: plain values."""
    out = {}
    for k in INFO_KEYS:
        v = info.get(k)
        if isinstance(v, (str, int, float)) or (
            isinstance(v, list) and all(isinstance(x, str) for x in v)
        ):
            out[k] = v
    return out
