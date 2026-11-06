"""The project: the analysis as the engine wrote it, the user's corrections beside it.

docs/FORMAT.md documents the file. Nothing here overwrites `analysis`: every view of the song is
computed from it and from `edits`, so a correction can always be undone, and `edits` survives a
new beat grid because it is written in seconds.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import tempfile
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FORMAT = "localchords"
VERSION = 1
EXTENSION = ".lchords"
DEFAULT_EDITS = {"chords": [], "meter": None, "grid": None, "key": None}
DEFAULT_VIEW = {
    "transpose": 0,
    "capo": 0,
    "accidentals": "auto",
    "simplify": False,
    "min_beats": 1,
    "show_bass": True,
    "show_numerals": False,
    "transpose_audio": False,
}


class ProjectError(Exception):
    """A project file that cannot be used; the message is written for the user."""


@dataclass
class Beat:
    index: int
    start: float
    end: float
    chord: str
    bass: str | None
    edited: bool


@dataclass
class Segment:
    start_beat: int
    end_beat: int
    start: float
    end: float
    chord: str
    bass: str | None
    edited: bool
    numeral: str | None = None
    role: str | None = None
    function: str | None = None
    target: str | None = None
    candidates: list[str] = field(default_factory=list)


@dataclass
class Bar:
    number: int  # 1 for the first full bar, 0 for a pickup
    beats: list[int | None]  # beat indexes; None pads a bar cut by the start or end of the song


def encode_waveform(values: np.ndarray) -> str:
    return base64.b64encode(np.asarray(values, dtype=np.uint8).tobytes()).decode("ascii")


def decode_waveform(text: str | None) -> np.ndarray:
    if not text:
        return np.zeros(0, dtype=np.uint8)
    return np.frombuffer(base64.b64decode(text), dtype=np.uint8)


class Project:
    def __init__(self, audio: dict, analysis: dict, edits=None, view=None):
        self.audio = audio
        self.analysis = analysis
        self.edits = {**copy.deepcopy(DEFAULT_EDITS), **(edits or {})}
        self.view = {**DEFAULT_VIEW, **(view or {})}
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._cache: dict = {}

    # The file ----------------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": VERSION,
            "audio": self.audio,
            "analysis": self.analysis,
            "edits": self.edits,
            "view": self.view,
        }

    def save(self, path: Path) -> None:
        """Write atomically: a crash midway leaves the previous file whole."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.to_dict(), ensure_ascii=False, indent=1).encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: Path) -> Project:
        try:
            with path.open(encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError as exc:
            raise ProjectError(f"Projet introuvable : {path}") from exc
        except (OSError, ValueError) as exc:
            raise ProjectError(f"« {path.name} » n'est pas un projet lisible.") from exc
        if not isinstance(d, dict) or d.get("format") != FORMAT:
            raise ProjectError(f"« {path.name} » n'est pas un projet LocalChords.")
        if d.get("version", 0) > VERSION:
            raise ProjectError(f"« {path.name} » vient d'une version plus récente de LocalChords.")
        try:
            analysis = d["analysis"]
            analysis["beats"], analysis["segments"], d["audio"]["duration"]  # noqa: B018
        except (KeyError, TypeError) as exc:
            raise ProjectError(f"« {path.name} » est incomplet.") from exc
        return cls(d["audio"], analysis, d.get("edits"), d.get("view"))

    # Corrections and undo ----------------------------------------------------------------------
    def _touch(self) -> None:
        self._cache.clear()

    def _record(self) -> None:
        self._undo.append(copy.deepcopy(self.edits))
        self._redo.clear()
        self._touch()

    def set_chord(self, start: float, end: float, chord: str, bass: str | None = None) -> None:
        """Correct [start, end) in seconds; later corrections lie over earlier ones."""
        self._record()
        self.edits["chords"].append(
            {"start": round(start, 3), "end": round(end, 3), "chord": chord, "bass": bass}
        )

    def set_meter(self, beats_per_bar: int, first_downbeat: int) -> None:
        self._record()
        self.edits["meter"] = {
            "beats_per_bar": int(beats_per_bar),
            "first_downbeat": int(first_downbeat) % int(beats_per_bar),
        }

    def set_grid(self, *, scale=None, offset=None, bpm=None) -> None:
        """Change the beat grid: halve or double it, shift it, or lay a steady one at a tempo."""
        self._record()
        grid = dict(self.edits["grid"] or {"scale": 1, "offset": 0.0, "bpm": None})
        if scale is not None:
            grid["scale"] = scale
        if offset is not None:
            grid["offset"] = round(float(offset), 3)
        if bpm is not None:
            grid["bpm"] = bpm or None
        same = grid["scale"] == 1 and not grid["offset"] and not grid["bpm"]
        self.edits["grid"] = None if same else grid

    def set_key(self, key: str | None) -> None:
        self._record()
        self.edits["key"] = key

    def reset_edits(self) -> None:
        self._record()
        self.edits = copy.deepcopy(DEFAULT_EDITS)

    def replace_analysis(self, analysis: dict) -> None:
        """A new analysis keeps the corrections: they are in seconds, not on the old grid."""
        self.analysis = analysis
        self._touch()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self.edits)
            self.edits = self._undo.pop()
            self._touch()

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self.edits)
            self.edits = self._redo.pop()
            self._touch()

    def set_view(self, **values) -> None:
        self.view.update(values)
        self._touch()

    # What the song is, after corrections -------------------------------------------------------
    @property
    def duration(self) -> float:
        return float(self.audio["duration"])

    def grid(self) -> list[float]:
        """The beat times in use."""
        if "grid" in self._cache:
            return self._cache["grid"]
        base = list(self.analysis["beats"])
        options = self.edits["grid"]
        if options and base:
            if options.get("bpm"):
                base = [float(t) for t in np.arange(base[0], self.duration, 60 / options["bpm"])]
            elif options.get("scale") == 2:
                mids = [(a + b) / 2 for a, b in zip(base, base[1:], strict=False)]
                base = sorted([*base, *mids])
            elif options.get("scale") == 0.5:
                base = base[::2]
            shift = float(options.get("offset") or 0.0)
            base = [round(t + shift, 3) for t in base if 0 <= t + shift < self.duration]
        self._cache["grid"] = base
        return base

    def _pieces(self) -> list[tuple[float, float, str, str | None, bool]]:
        """Non-overlapping (start, end, chord, bass, edited), the edits lying over the analysis."""
        pieces = [
            (s["start_time"], s["end_time"], s["chord"], s.get("bass"), False)
            for s in self.analysis["segments"]
        ]
        for e in self.edits["chords"]:
            kept = []
            for a, b, chord, bass, edited in pieces:
                if b <= e["start"] or a >= e["end"]:
                    kept.append((a, b, chord, bass, edited))
                    continue
                if a < e["start"]:
                    kept.append((a, e["start"], chord, bass, edited))
                if b > e["end"]:
                    kept.append((e["end"], b, chord, bass, edited))
            kept.append((e["start"], e["end"], e["chord"], e.get("bass"), True))
            pieces = sorted(kept, key=lambda p: p[0])
        return pieces

    def beats(self) -> list[Beat]:
        """One chord per beat: whichever covers most of it."""
        if "beats" in self._cache:
            return self._cache["beats"]
        times = self.grid()
        pieces = self._pieces()
        out = []
        cursor = 0
        for i, start in enumerate(times):
            end = times[i + 1] if i + 1 < len(times) else self.duration
            while cursor < len(pieces) and pieces[cursor][1] <= start:
                cursor += 1
            overlap: dict[tuple, float] = {}
            j = cursor
            while j < len(pieces) and pieces[j][0] < end:
                a, b, chord, bass, edited = pieces[j]
                span = min(b, end) - max(a, start)
                if span > 0:
                    k = (chord, bass, edited)
                    overlap[k] = overlap.get(k, 0.0) + span
                j += 1
            chord, bass, edited = max(overlap, key=overlap.get) if overlap else ("N", None, False)
            out.append(Beat(i, start, end, chord, bass, edited))
        self._cache["beats"] = out
        return out

    def segments(self) -> list[Segment]:
        """The chord runs as shown, short runs absorbed, with their harmonic analysis."""
        if "segments" in self._cache:
            return self._cache["segments"]
        runs: list[Segment] = []
        for b in self.beats():
            if runs and (runs[-1].chord, runs[-1].bass) == (b.chord, b.bass):
                runs[-1].end_beat, runs[-1].end = b.index + 1, b.end
                runs[-1].edited |= b.edited
            else:
                runs.append(
                    Segment(b.index, b.index + 1, b.start, b.end, b.chord, b.bass, b.edited)
                )
        runs = _absorb_short(runs, int(self.view.get("min_beats") or 1))
        self._annotate(runs)
        self._cache["segments"] = runs
        return runs

    def _annotate(self, runs: list[Segment]) -> None:
        from chordotomy import harmony

        # Harmony reads chord runs: a bass change under one chord doesn't end it.
        groups: list[list[Segment]] = []
        for s in runs:
            if groups and groups[-1][0].chord == s.chord:
                groups[-1].append(s)
            else:
                groups.append([s])
        progression = [(g[0].chord, g[-1].end_beat - g[0].start_beat) for g in groups]
        # Normalized here, so a flat key from anywhere (Db:maj) reaches harmony as it expects it.
        chosen = self.edits.get("key")
        chosen = harmony.parse_key(chosen) if chosen else None
        key_info, regions, analyses = harmony.analyze(progression, chosen)
        self._cache["key"] = key_info
        self._cache["regions"] = regions
        for group, a in zip(groups, analyses, strict=True):
            for s in group:
                s.numeral, s.role = a.get("numeral"), a.get("role")
                s.function, s.target = a.get("function"), a.get("target")
        raw = self.analysis["segments"]
        starts = [s["start_time"] for s in raw]
        for s in runs:
            i = bisect_right(starts, s.start + 1e-6) - 1
            if 0 <= i < len(raw):
                s.candidates = list(raw[i].get("candidates") or [])

    def key(self) -> dict | None:
        """The key after corrections: {label, source, candidates}."""
        self.segments()
        return self._cache.get("key")

    def key_regions(self) -> list[dict]:
        self.segments()
        return self._cache.get("regions", [])

    def meter(self) -> dict:
        edited = self.edits["meter"]
        if edited:
            return {**edited, "confidence": 1.0, "edited": True}
        base = self.analysis.get("meter") or {"beats_per_bar": 4, "first_downbeat": 0}
        return {**base, "edited": False}

    def tempo(self) -> dict:
        from .rhythm import tempo

        return tempo(self.grid())

    def bars(self) -> list[Bar]:
        """The beats in bars, from the analysis's bar lines or from a count the user set.

        Beats before the first bar line make a pickup bar, padded in front. A bar cut short pads
        behind; one that overruns its length carries on into a bar of its own.
        """
        if "bars" in self._cache:
            return self._cache["bars"]
        meter = self.meter()
        per_bar = int(meter["beats_per_bar"])
        n = len(self.grid())
        lines = meter.get("bar_lines")
        first_line = int(meter["first_downbeat"])
        # Bar lines count beats of the analysis's grid. A corrected grid counts afresh, from the
        # beat nearest where the analysis heard a downbeat.
        if self.edits["grid"] and not meter["edited"] and n:
            base = self.analysis["beats"]
            anchor = base[lines[0] if lines else first_line] if base else 0.0
            times = np.asarray(self.grid())
            first_line = int(np.argmin(np.abs(times - anchor))) % per_bar
        if lines is None or self.edits["grid"]:
            lines = list(range(first_line, n, per_bar))
        lines = [line for line in lines if line < n]
        bars: list[Bar] = []
        first = lines[0] if lines else n
        if first:
            # A long intro counts back from the first bar line, the pickup against it.
            bars = _pickup_bars(first, per_bar)
        number = 1
        for line, end in zip(lines, [*lines[1:], n], strict=True):
            for start in range(line, end, per_bar):
                cells = list(range(start, min(start + per_bar, end)))
                bars.append(Bar(number, cells + [None] * (per_bar - len(cells))))
                number += 1
        self._cache["bars"] = bars
        return bars

    def bar_position(self, beat: int) -> tuple[int, int] | None:
        """(bar number, beat in the bar, from 1) of a beat; the bar number is 0 in a pickup."""
        for bar in self.bars():
            if beat in bar.beats:
                played = [b for b in bar.beats if b is not None]
                return bar.number, played.index(beat) + 1
        return None

    def beat_at(self, t: float) -> int:
        """Index of the beat playing at t, -1 before the first one.

        The tolerance is for a seek to a beat, whose time comes back through sample frames and can
        land a hair under it.
        """
        return bisect_right(self.grid(), t + 1e-3) - 1

    def segment_at_beat(self, beat: int) -> Segment | None:
        for s in self.segments():
            if s.start_beat <= beat < s.end_beat:
                return s
        return None

    def progressions(self, limit: int = 4) -> list[dict]:
        """What comes back, by how much of the song it covers: {chords, count, start_beats}."""
        runs: list[Segment] = []
        for s in self.segments():
            if s.chord != "N" and (not runs or runs[-1].chord != s.chord):
                runs.append(s)
        return [
            {
                "chords": [runs[i].chord for i in range(hit["at"][0], hit["at"][0] + hit["size"])],
                "symbols": [runs[i] for i in range(hit["at"][0], hit["at"][0] + hit["size"])],
                "count": len(hit["at"]),
                "start_beats": [runs[i].start_beat for i in hit["at"]],
            }
            for hit in find_repeats([r.chord for r in runs], limit)
        ]

    def agreement_with(self, other: dict) -> dict:
        """How another analysis of this song compares, beat by beat, as shares of the beats."""
        from .chords import parse, simplified

        def triad(label):
            parsed = parse(label)
            return None if parsed is None else (parsed[0], simplified(parsed[1]))

        them = Project(self.audio, other)
        grid = them.grid()
        beats = them.beats()
        mine = self.beats()
        if not mine or not grid:
            return {"exact": 0.0, "triads": 0.0, "differences": []}
        exact = same_triad = 0
        differences: list[float] = []
        for b in mine:
            at = bisect_right(grid, (b.start + b.end) / 2) - 1
            label = beats[at].chord if at >= 0 else "N"
            exact += label == b.chord
            matches = triad(label) == triad(b.chord)
            same_triad += matches
            if not matches:
                differences.append(b.start)
        return {
            "exact": exact / len(mine),
            "triads": same_triad / len(mine),
            "differences": differences,
        }

    def sounding_shift(self) -> int:
        """Semitones between what plays and what the chart shows: transposition less capo."""
        return int(self.view["transpose"]) - int(self.view["capo"])


def find_repeats(chords: list[str], limit: int = 4, min_size=2, max_size=12) -> list[dict]:
    """Sequences that recur, greedily by the most chords covered; each chord counted once.

    A pattern doubled (A B A B) counts as its half, and only runs of at least two appearances count.
    Returns {at: [indexes of the appearances], size}.
    """
    used = [False] * len(chords)
    found = []
    while len(found) < limit:
        best = None
        for size in range(min_size, max_size + 1):
            places: dict[tuple, list[int]] = {}
            for i in range(len(chords) - size + 1):
                if any(used[i : i + size]):
                    continue
                piece = tuple(chords[i : i + size])
                seen = places.setdefault(piece, [])
                if not seen or i >= seen[-1] + size:
                    seen.append(i)
            for piece, at in places.items():
                half = size // 2
                doubled = size % 2 == 0 and piece[:half] == piece[half:]
                if len(at) < 2 or doubled or len(set(piece)) < 2:
                    continue
                coverage = len(at) * size
                # On a tie the longer pattern: it says more about the song's form.
                if best is None or (coverage, size) > (best[0], best[1]):
                    best = (coverage, size, at)
        if best is None:
            break
        _, size, at = best
        for start in at:
            for i in range(start, start + size):
                used[i] = True
        found.append({"at": at, "size": size})
    return found


def _pickup_bars(first: int, per_bar: int) -> list[Bar]:
    """Full bars counted back from the first bar line; the short one first, padded in front."""
    short = first % per_bar
    bars = [Bar(0, [None] * (per_bar - short) + list(range(short)))] if short else []
    for start in range(short, first, per_bar):
        bars.append(Bar(0, list(range(start, start + per_bar))))
    return bars


def _absorb_short(runs: list[Segment], min_beats: int) -> list[Segment]:
    """Fold runs shorter than min_beats into the neighbour before them; a correction stays whole
    and never grows."""
    if min_beats <= 1:
        return runs
    out: list[Segment] = []
    for run in runs:
        short = run.end_beat - run.start_beat < min_beats and not run.edited
        same = out and (out[-1].chord, out[-1].bass) == (run.chord, run.bass)
        if out and (same or (short and not out[-1].edited)):
            out[-1].end_beat, out[-1].end = run.end_beat, run.end
            out[-1].edited |= run.edited
        else:
            out.append(run)
    first_short = out and out[0].end_beat - out[0].start_beat < min_beats and not out[0].edited
    if first_short and len(out) > 1 and not out[1].edited:
        out[1].start_beat, out[1].start = out[0].start_beat, out[0].start
        out.pop(0)
    return out
