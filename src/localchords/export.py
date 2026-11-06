"""The chart as text and as ChordPro, written from what the grid shows."""

from __future__ import annotations

from . import __version__
from .chords import key_name, symbol
from .project import Project, Segment

BARS_PER_LINE = 4


def chord_text(project: Project, seg: Segment, *, ascii_only: bool = False) -> str:
    """A segment's symbol with the project's transposition, capo and spelling applied."""
    view = project.view
    key = project.key()
    return symbol(
        seg.chord,
        seg.bass,
        key=key["label"] if key else None,
        semitones=project.sounding_shift(),
        accidentals=view["accidentals"],
        simplify=view["simplify"],
        show_bass=view["show_bass"],
        ascii_only=ascii_only,
        latin=view.get("latin", False),
    )


def bar_symbols(project: Project, *, ascii_only: bool = True) -> list[list[str]]:
    """Per bar, one entry per beat: the symbol where a chord starts or the bar opens, else ''."""
    by_beat = {}
    for seg in project.segments():
        for beat in range(seg.start_beat, seg.end_beat):
            by_beat[beat] = (seg, beat == seg.start_beat)
    out = []
    for bar in project.bars():
        cells = []
        opened = False
        for beat in bar.beats:
            if beat is None or beat not in by_beat:
                cells.append("")
                continue
            seg, starts = by_beat[beat]
            cells.append(chord_text(project, seg, ascii_only=ascii_only) if starts or not opened else "")
            opened = True
        out.append(cells)
    return out


def header(project: Project) -> list[tuple[str, str]]:
    key = project.key()
    tempo = project.tempo()
    meter = project.meter()
    view = project.view
    fields = [("Titre", project.audio.get("title") or "")]
    if project.audio.get("artist"):
        fields.append(("Artiste", project.audio["artist"]))
    if key:
        fields.append(("Tonalité", key_name(key["label"], project.sounding_shift())))
    if tempo["bpm"]:
        fields.append(("Tempo", f"{tempo['bpm']:.0f} BPM"))
    fields.append(("Mesure", f"{meter['beats_per_bar']} temps"))
    if view["transpose"]:
        fields.append(("Transposition", f"{view['transpose']:+d} demi-tons"))
    if view["capo"]:
        fields.append(("Capodastre", f"case {view['capo']}"))
    return fields


def to_text(project: Project) -> str:
    """Aligned bars: `| C . . . | Am . G . |`, four to a line."""
    lines = [f"{k} : {v}" for k, v in header(project)]
    lines.append("")
    bars = bar_symbols(project)
    width = max((len(c) for bar in bars for c in bar), default=1) or 1
    for i in range(0, len(bars), BARS_PER_LINE):
        row = bars[i : i + BARS_PER_LINE]
        text = " | ".join(" ".join((c or ".").ljust(width) for c in bar) for bar in row)
        lines.append(f"| {text} |")
    lines.append("")
    lines.append(f"(LocalChords {__version__} : extraction automatique, à vérifier à l'oreille.)")
    return "\n".join(lines) + "\n"


def to_chordpro(project: Project) -> str:
    key = project.key()
    tempo = project.tempo()
    meter = project.meter()
    lines = [f"{{title: {project.audio.get('title') or ''}}}"]
    if project.audio.get("artist"):
        lines.append(f"{{artist: {project.audio['artist']}}}")
    if key:
        moved = symbol(
            key["label"], key=key["label"], semitones=project.sounding_shift(), ascii_only=True
        )
        lines.append(f"{{key: {moved}}}")
    if tempo["bpm"]:
        lines.append(f"{{tempo: {tempo['bpm']:.0f}}}")
    lines.append(f"{{time: {meter['beats_per_bar']}/4}}")
    if project.view["capo"]:
        lines.append(f"{{capo: {project.view['capo']}}}")
    lines.append("")
    bars = bar_symbols(project)
    for i in range(0, len(bars), BARS_PER_LINE):
        cells = []
        for bar in bars[i : i + BARS_PER_LINE]:
            chords = [f"[{c}]" for c in bar if c]
            cells.append(" ".join(chords) if chords else "%")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
