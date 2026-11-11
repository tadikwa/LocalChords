"""Lyrics: reading LRC, SRT and plain text, following the playback, and placing chords over words.

Nothing here draws or touches the network. A project's lyrics are a plain dict (docs/TECHNIQUE.md):

  source    where they come from: kind (user, file, embedded, catalog, transcription), name, and
            whether they may be exported
  original  the lines as received, never changed
  lines     the lines as corrected: {text, start, end?, section?, words?}; start and end are seconds
            of the recording, or None for a line nobody has timed
  offset    seconds added to every time, to shift them all at once
  anchors   where the user put a chord in the text: {chord time: {line, char}}
  previous  the lyrics these replaced, to go back to them

A chord keeps its musical time (from the grid) and, apart from it, an editorial anchor in the text:
moving a chord over another word never changes the harmony.
"""

from __future__ import annotations

import contextlib
import copy
import re
from bisect import bisect_right
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP

KINDS = {
    "user": QT_TRANSLATE_NOOP("Lyrics", "Saisies par vous"),
    "file": QT_TRANSLATE_NOOP("Lyrics", "Importées depuis un fichier"),
    "embedded": QT_TRANSLATE_NOOP("Lyrics", "Lues dans le fichier audio"),
    "catalog": QT_TRANSLATE_NOOP("Lyrics", "Catalogue en ligne"),
    "transcription": QT_TRANSLATE_NOOP(
        "Lyrics", "Transcription automatique (brouillon à vérifier)"
    ),
}
SIDE_FILES = (".lrc", ".srt", ".txt")
_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORD_TIME = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
_META = re.compile(r"^\[(ar|ti|al|au|by|re|ve|length|offset|la|lang|#)\s*:(.*)\]$", re.IGNORECASE)
_SECTION = re.compile(r"^\[([^\]]+)\]$")
_SRT_TIME = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
)
HELD_GAP = 0.5  # a line starting this long after its chord began shows that chord at its start


def _seconds(m: str, s: str, frac: str | None) -> float:
    return int(m) * 60 + int(s) + (int(frac) / 10 ** len(frac) if frac else 0.0)


def decode(data: bytes) -> str:
    """Text from a lyrics file: UTF-8 or UTF-16 with a BOM, UTF-8, else Windows-1252."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


def parse(text: str) -> list[dict]:
    """Lines from LRC or plain text; `[Refrain]` alone on a line is a section heading.

    LRC: several times on one line repeat it; `[offset:±ms]` is applied; enhanced LRC's word times
    (`<mm:ss.xx>`) become word anchors. An empty line in plain text is a stanza break.
    """
    if _SRT_TIME.search(text):
        return parse_srt(text)
    shift = 0.0
    out: list[dict] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        meta = _META.match(line)
        if meta:
            if meta.group(1).lower() == "offset":
                with contextlib.suppress(ValueError):
                    shift = -int(meta.group(2).strip()) / 1000  # positive: lyrics come sooner
            continue
        times = []
        while m := _TIME.match(line):
            times.append(_seconds(*m.groups()))
            line = line[m.end() :]
        line = line.strip()
        if not times:
            section = _SECTION.match(line)
            if section:
                out.append({"text": section.group(1).strip(), "start": None, "section": True})
            elif line or (out and out[-1]["text"]):  # one break between stanzas, not a pile
                out.append({"text": line, "start": None})
            continue
        text_only, words, end = _word_times(line)
        for t in times:
            item = {"text": text_only, "start": round(t, 3)}
            later = t - times[0]  # a line sung again ([00:10][00:30]): its words move with it
            if words:
                item["words"] = [[c, round(w + later, 3)] for c, w in words]
            if end is not None and end + later > t:
                item["end"] = round(end + later, 3)
            out.append(item)
    starts = [x["start"] for x in out if x["start"] is not None]
    if starts != sorted(starts):
        out = _sort_timed(out)
    while out and not out[-1]["text"] and out[-1]["start"] is None:
        out.pop()
    for x in out:
        if x["start"] is not None:
            x["start"] = round(max(0.0, x["start"] + shift), 3)
            if x.get("words"):
                x["words"] = [[c, round(max(0.0, t + shift), 3)] for c, t in x["words"]]
            if x.get("end") is not None:
                x["end"] = round(max(0.0, x["end"] + shift), 3)
    return out


def _sort_timed(lines: list[dict]) -> list[dict]:
    """A file that repeats lines under several times lists them out of order: sort the timed ones,
    keeping each heading and break before the line it preceded."""
    groups, pending = [], []
    for x in lines:
        if x["start"] is None:
            pending.append(x)
        else:
            groups.append((x["start"], [*pending, x]))
            pending = []
    groups.sort(key=lambda g: g[0])
    return [x for _, g in groups for x in g] + pending


def _word_times(line: str) -> tuple[str, list[list], float | None]:
    """Enhanced LRC: the text without its <mm:ss.xx> tags, [char, time] where a tag stood, and the
    time of a tag after the last word (where the singing of the line ends), if there is one."""
    if "<" not in line:
        return line, [], None
    words, text, pos = [], "", 0
    for m in _WORD_TIME.finditer(line):
        text += line[pos : m.start()]
        pos = m.end()
        char = len(text) + (len(line[pos:]) - len(line[pos:].lstrip()))
        words.append([char, round(_seconds(*m.groups()), 3)])
    text += line[pos:]
    stripped = text.strip()
    lead = len(text) - len(text.lstrip())
    end = next((t for c, t in reversed(words) if c - lead >= len(stripped)), None)
    words = [[max(0, c - lead), t] for c, t in words if c - lead < len(stripped)]
    return stripped, words, end if words else None


def parse_srt(text: str) -> list[dict]:
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        rows = [r.strip() for r in block.split("\n") if r.strip()]
        for i, row in enumerate(rows):
            m = _SRT_TIME.search(row)
            if m:
                g = m.groups()
                start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 10 ** len(g[3])
                end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 10 ** len(g[7])
                words = " ".join(re.sub(r"<[^>]+>", "", r) for r in rows[i + 1 :]).strip()
                if words:
                    out.append({"text": words, "start": round(start, 3), "end": round(end, 3)})
                break
    return out


def read_file(path: Path) -> list[dict]:
    return parse(decode(path.read_bytes()))


def find_local(audio: Path, tagged: str = "") -> tuple[list[dict], dict] | None:
    """Lyrics already on the computer: a .lrc, .srt or .txt beside the recording, with its name,
    else the lyrics written in its tags. Nothing is looked for anywhere else."""
    for ext in SIDE_FILES:
        side = audio.with_suffix(ext)
        try:
            lines = read_file(side) if side.is_file() else []
        except OSError:
            lines = []
        if any(x["text"] for x in lines):
            return lines, {"kind": "file", "name": side.name, "exportable": True}
    lines = parse(tagged) if tagged.strip() else []
    if any(x["text"] for x in lines):
        return lines, {"kind": "embedded", "name": audio.name, "exportable": True}
    return None


# Writing --------------------------------------------------------------------------------------


def stamp(t: float) -> str:
    t = max(0.0, t)
    minutes, seconds = divmod(round(t * 100) / 100, 60)
    return f"[{int(minutes):02d}:{seconds:05.2f}]"


def to_lrc(lyrics: dict, title: str = "", artist: str = "") -> str:
    """LRC with the offset applied, so any player shows it as LocalChords does."""
    out = []
    if title:
        out.append(f"[ti:{title}]")
    if artist:
        out.append(f"[ar:{artist}]")
    offset = float(lyrics.get("offset") or 0.0)
    for x in lyrics["lines"]:
        if x.get("section"):
            out.append(f"[{x['text']}]")
        elif x["start"] is None:
            out.append(x["text"])
        else:
            out.append(stamp(x["start"] + offset) + x["text"])
    return "\n".join(out) + "\n"


def to_text(lyrics: dict) -> str:
    return (
        "\n".join(f"[{x['text']}]" if x.get("section") else x["text"] for x in lyrics["lines"])
        + "\n"
    )


def to_editor(lines: list[dict]) -> str:
    """What the text editor shows: a time before each timed line, as in LRC."""
    return "\n".join(
        f"[{x['text']}]"
        if x.get("section")
        else (stamp(x["start"]) + " " + x["text"] if x["start"] is not None else x["text"])
        for x in lines
    )


def from_editor(text: str, before: list[dict]) -> list[dict]:
    """Lines back from the editor. A line whose text and time are unchanged keeps its end and its
    word times; any other change drops them, rather than keep times that no longer fit."""
    kept = {(x["text"], x["start"]): x for x in before if not x.get("section")}
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        times = []
        while m := _TIME.match(line):
            times.append(round(_seconds(*m.groups()), 3))
            line = line[m.end() :]
        line = line.strip()
        section = _SECTION.match(line) if not times else None
        if section:
            out.append({"text": section.group(1).strip(), "start": None, "section": True})
            continue
        if not line and not times and (not out or not out[-1]["text"]):
            continue
        for t in times or [None]:
            old = kept.get((line, t))
            out.append(copy.deepcopy(old) if old else {"text": line, "start": t})
    while out and not out[-1]["text"]:
        out.pop()
    return out


# Following the playback -----------------------------------------------------------------------


def timed(lyrics: dict | None) -> bool:
    return bool(lyrics) and any(x["start"] is not None for x in lyrics["lines"])


def line_at(lyrics: dict, t: float) -> int | None:
    """Index of the timed line being sung at t (the last one begun), None before the first."""
    offset = float(lyrics.get("offset") or 0.0)
    idx = _by_start(lyrics["lines"])
    starts = [lyrics["lines"][i]["start"] + offset for i in idx]
    k = bisect_right(starts, t + 1e-3) - 1
    return idx[k] if k >= 0 else None


WORD_MAX = 2.0  # a word lights up over at most this long: a longer wait before the next is a rest
LAST_WORD = 1.0  # the last word of a line with no end known: its length is not known either


def sung(text: str, words: list, t: float, end: float | None) -> tuple[float, int, float] | None:
    """How far the singing has gone into a line at t, from its words' times (already shifted by
    the offset): (characters sung, as a fraction; start of the word being sung; how far into it,
    0..1, or -1 between words). None for a line without word times: nothing is made up.

    A word lights from its start to the next word's, over at most WORD_MAX; the last one until
    `end` (the line's end, else the next line's start), over at most LAST_WORD without one.
    """
    if not words or not text:
        return None
    points = sorted((min(max(0, int(c)), len(text)), float(w)) for c, w in words)
    times, latest = [], float("-inf")
    for _c, w in points:  # times edited by hand may go back: never light a word before its start
        latest = max(latest, w)
        times.append(latest)
    if t < times[0]:
        return float(points[0][0]), points[0][0], -1.0
    i = bisect_right(times, t) - 1
    first = points[i][0]
    following = points[i + 1][0] if i + 1 < len(points) else len(text)
    last = first + len(text[first:following].rstrip())  # the word, without the space after it
    if i + 1 < len(points):
        span = min(times[i + 1] - times[i], WORD_MAX)
    else:
        span = min(end - times[i], WORD_MAX) if end is not None else LAST_WORD
    f = (t - times[i]) / max(span, 0.05)
    if f >= 1.0:
        return float(last), first, -1.0
    return first + (last - first) * f, first, f


def _by_start(lines: list[dict]) -> list[int]:
    """Indexes of the timed lines in time order: hand-timed lines may be out of text order."""
    return sorted((i for i, x in enumerate(lines) if x["start"] is not None),
                  key=lambda i: lines[i]["start"])  # fmt: skip


def new(lines: list[dict], source: dict) -> dict:
    return {
        "source": source,
        "original": copy.deepcopy(lines),
        "lines": copy.deepcopy(lines),
        "offset": 0.0,
        "anchors": {},
    }


def checked(d) -> dict | None:
    """Lyrics read from a project file, completed, or None if they are not lyrics."""

    def number(v):
        return isinstance(v, int | float) and not isinstance(v, bool)

    def line_ok(x):
        return (
            isinstance(x, dict)
            and isinstance(x.get("text"), str)
            and (x.get("start") is None or number(x["start"]))
        )

    def word_ok(w):
        return isinstance(w, list) and len(w) == 2 and isinstance(w[0], int) and number(w[1])

    if not (
        isinstance(d, dict)
        and isinstance(d.get("source"), dict)
        and isinstance(d.get("lines"), list)
        and all(map(line_ok, d["lines"]))
    ):
        return None
    d.setdefault("original", copy.deepcopy(d["lines"]))
    if not isinstance(d.get("offset"), int | float):
        d["offset"] = 0.0
    anchors = d.get("anchors") if isinstance(d.get("anchors"), dict) else {}
    d["anchors"] = {
        k: a for k, a in anchors.items()
        if isinstance(a, dict) and isinstance(a.get("line"), int) and isinstance(a.get("char"), int)
    }  # fmt: skip
    for x in d["lines"]:
        if "words" in x and not (isinstance(x["words"], list) and all(map(word_ok, x["words"]))):
            del x["words"]
    if "previous" in d and checked(d["previous"]) is None:
        del d["previous"]
    return d


def replaced(old: dict | None, lines: list[dict], source: dict) -> dict:
    """New lyrics, the old ones kept to go back to (without their own previous: one step)."""
    out = new(lines, source)
    if old:
        out["previous"] = {k: v for k, v in old.items() if k != "previous"}
    return out


def edited(lyrics: dict) -> bool:
    return (
        lyrics["lines"] != lyrics["original"]
        or bool(lyrics.get("anchors"))
        or bool(lyrics.get("offset"))
    )


def exportable(lyrics: dict | None) -> bool:
    """Catalog lyrics are shown, never exported: their rights are the catalog's, not ours."""
    source = lyrics["source"] if lyrics else {}
    return bool(source.get("exportable")) and source.get("kind") != "catalog"


def shareable(lyrics: dict | None) -> dict | None:
    """What of the lyrics may leave the program: nothing of a catalog's, even kept as previous."""
    if not exportable(lyrics):
        return None
    out = dict(lyrics)
    if "previous" in out and not exportable(out["previous"]):
        del out["previous"]
    return out


# Chords over the words --------------------------------------------------------------------------


def chord_key(t: float) -> str:
    return f"{t:.2f}"


def sheet(lyrics: dict, chords: list[tuple[float, float, str]], duration: float) -> list[dict]:
    """The lyrics as rows, each chord placed over the line sung when it starts.

    chords: (start, end, label) in seconds, in order, labels as the grid writes them (None for no
    chord). Returns rows: {kind: line, section, break or chords (no words: an intro or a gap),
    line: index in lyrics["lines"] or None, text, start, chords: [{char, label, time, end, key,
    how}]}. `how` says what the place rests on: "word" (word times), "manual" (the user put it
    there), "approx" (spread over a line timed only at its start), "held" (began before the line).
    """
    lines = lyrics["lines"]
    offset = float(lyrics.get("offset") or 0.0)
    anchors = lyrics.get("anchors") or {}
    timed_idx = _by_start(lines)
    rows = []
    for i, x in enumerate(lines):
        kind = "section" if x.get("section") else ("line" if x["text"] else "break")
        start = x["start"] + offset if x["start"] is not None else None
        rows.append({"kind": kind, "line": i, "text": x["text"], "start": start, "chords": []})
    if not timed_idx:
        return rows
    by_line = {i: r for i, r in zip(range(len(lines)), rows, strict=True)}
    starts = [lines[i]["start"] + offset for i in timed_idx]
    intro: list[dict] = []
    gaps: dict[int, list[dict]] = {}
    real = [c for c in chords if c[2]]
    for start, end, label in real:
        k = chord_key(start)
        chord = {"label": label, "time": start, "end": end, "key": k}
        anchor = anchors.get(k)
        if anchor and 0 <= anchor["line"] < len(lines) and not lines[anchor["line"]].get("section"):
            text = lines[anchor["line"]]["text"]
            by_line[anchor["line"]]["chords"].append(
                {**chord, "char": min(max(0, int(anchor["char"])), len(text)), "how": "manual"}
            )
            continue
        j = bisect_right(starts, start + 1e-3) - 1
        if j < 0:
            intro.append({**chord, "char": 0, "how": "approx"})
            continue
        li = timed_idx[j]
        line = lines[li]
        a = starts[j]
        b = starts[j + 1] if j + 1 < len(starts) else duration
        if line.get("end") is not None:
            sung_until = line["end"] + offset
            if start >= sung_until + HELD_GAP and start < b:
                gaps.setdefault(li, []).append({**chord, "char": 0, "how": "approx"})
                continue
            b = min(b, max(sung_until, a + 0.1))
        if not line["text"]:  # an LRC line with no words marks a gap
            by_line[li]["kind"] = "chords"
            by_line[li]["chords"].append({**chord, "char": 0, "how": "approx"})
            continue
        char, how = _place(line, start - offset, a - offset, b - offset)
        by_line[li]["chords"].append({**chord, "char": char, "how": how})
    # A line that begins on a chord already sounding shows it first, so it is never a guess.
    for j, li in enumerate(timed_idx):
        row = by_line[li]
        if row["kind"] != "line":
            continue
        a = starts[j]
        if any(c["char"] == 0 or abs(c["time"] - a) < HELD_GAP for c in row["chords"]):
            continue
        sounding = [c for c in real if c[0] < a - 1e-3 and c[1] > a + HELD_GAP]
        if sounding and chord_key(sounding[-1][0]) not in anchors:  # placed by hand: shown there
            s, e, label = sounding[-1]
            row["chords"].append(
                {"label": label, "time": s, "end": e, "key": chord_key(s), "char": 0, "how": "held"}
            )
    out = []
    if intro:
        out.append(
            {"kind": "chords", "line": None, "text": "", "start": real[0][0], "chords": intro}
        )
    for row in rows:
        row["chords"].sort(key=lambda c: (c["char"], c["time"]))
        out.append(row)
        if row["line"] in gaps:
            g = gaps[row["line"]]
            out.append(
                {"kind": "chords", "line": None, "text": "", "start": g[0]["time"], "chords": g}
            )
    return out


def _place(line: dict, t: float, a: float, b: float) -> tuple[int, str]:
    """Where in a line's text a chord at t goes: on the word sung then, or spread over the line."""
    text = line["text"]
    words = line.get("words")
    if words:
        before = [c for c, w in words if w <= t + 0.15]
        return (before[-1] if before else 0), "word"
    starts = word_starts(text)
    frac = min(max((t - a) / max(b - a, 0.1), 0.0), 1.0)
    target = frac * len(text)
    return min(starts, key=lambda c: abs(c - target)), "approx"


def word_starts(text: str) -> list[int]:
    return [0] + [i for i in range(1, len(text)) if text[i - 1] == " " and text[i] != " "]


# Layout, shared by the screen and the PDF ------------------------------------------------------


def layout(
    text: str,
    chords: list[dict],
    width: float,
    text_w: Callable[[str], float],
    chord_w: Callable[[str], float],
    gap: float,
) -> list[dict]:
    """A row as visual lines: [{runs: [(x, text, first char)], chords: [(x, index in chords)]}].

    The text is cut where words start and where chords stand. The words flow on as written; a
    piece is pushed right only when its chord name would run into the name before it, so names
    never overlap and stay over their letter at any font or window width. Lines wrap between
    words.
    """
    cuts = sorted({0, len(text), *word_starts(text), *(min(c["char"], len(text)) for c in chords)})
    at: dict[int, list[int]] = {}
    for n, c in enumerate(chords):
        at.setdefault(min(c["char"], len(text)), []).append(n)
    pieces = []
    for a, b in zip(cuts, cuts[1:] + [None], strict=False):
        if b is None and a == len(text) and a not in at:
            continue
        piece = text[a:b] if b is not None else ""
        pieces.append((a, piece, at.get(a, [])))
    lines: list[dict] = [{"runs": [], "chords": []}]
    x = free = 0.0  # where the text goes on; where the next chord name may start
    for a, piece, names in pieces:
        labels = sum(chord_w(chords[n]["label"]) for n in names) + gap * len(names)
        start = max(x, free) if names else x
        breakable = a == 0 or text[a - 1] == " " or not piece
        if x > 0 and breakable and start + max(text_w(piece.rstrip()), labels) > width:
            lines.append({"runs": [], "chords": []})
            x = free = start = 0.0
        cx = start
        for n in names:
            lines[-1]["chords"].append((cx, n))
            cx += chord_w(chords[n]["label"]) + gap
        if names:
            free = cx
        if piece:
            lines[-1]["runs"].append((start, piece, a))
        x = start + text_w(piece)
    return lines


def char_at(runs: list[tuple[float, str, int]], x: float, text_w: Callable[[str], float]) -> int:
    """The character a point of a laid-out line falls on: where a dropped chord goes."""
    best = runs[0][2] if runs else 0
    for x0, piece, first in runs:
        if x < x0:
            break
        best = first
        for k in range(1, len(piece) + 1):
            if x0 + text_w(piece[:k]) > x + text_w(piece[k - 1 : k]) / 2:
                break
            best = first + k
    return best
