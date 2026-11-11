"""The chart as text and as ChordPro, written from what the grid shows."""

from __future__ import annotations

from . import __version__
from . import lyrics as L
from .chords import key_name, symbol
from .i18n import translate
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
            cells.append(
                chord_text(project, seg, ascii_only=ascii_only) if starts or not opened else ""
            )
            opened = True
        out.append(cells)
    return out


def header(project: Project) -> list[tuple[str, str]]:
    key = project.key()
    tempo = project.tempo()
    meter = project.meter()
    view = project.view
    fields = [(translate("Export", "Titre"), project.audio.get("title") or "")]
    if project.audio.get("artist"):
        fields.append((translate("Export", "Artiste"), project.audio["artist"]))
    if key:
        # What sounds, transposition included; with a capo, the shapes played are another key.
        fields.append(
            (translate("Export", "Tonalité"), key_name(key["label"], int(view["transpose"])))
        )
        if view["capo"]:
            fields.append(
                (
                    translate("Export", "Formes jouées"),
                    key_name(key["label"], project.sounding_shift()),
                )
            )
    if tempo["bpm"]:
        fields.append((translate("Export", "Tempo"), f"{tempo['bpm']:.0f} BPM"))
    fields.append(
        (
            translate("Export", "Mesure"),
            translate("Export", "{beats_per_bar} temps").format(
                beats_per_bar=meter["beats_per_bar"]
            ),
        )
    )
    if view["transpose"]:
        fields.append(
            (
                translate("Export", "Transposition"),
                translate("Export", "{shift} demi-tons").format(shift=f"{view['transpose']:+d}"),
            )
        )
    if view["capo"]:
        fields.append(
            (
                translate("Export", "Capodastre"),
                translate("Export", "case {capo} (choisie, non détectée)").format(
                    capo=view["capo"]
                ),
            )
        )
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
    lines.append(
        translate(
            "Export",
            "(LocalChords {version} : extraction automatique, à vérifier à l'oreille.)",
        ).format(version=__version__)
    )
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


# With the lyrics -------------------------------------------------------------------------------


def lyric_rows(project: Project) -> list[dict]:
    """The lyrics as rows with the chords over their words, named as the grid names them."""
    chords = [
        (s.start, s.end, chord_text(project, s) if s.chord != "N" else None)
        for s in project.segments()
    ]
    return L.sheet(project.lyrics, chords, project.duration)


def approximate(rows: list[dict]) -> bool:
    return any(
        c["how"] in ("approx", "held") for r in rows if r["kind"] == "line" for c in r["chords"]
    )


def to_text_with_lyrics(project: Project, width: int = 72) -> str:
    """The chords over the words in plain text, from the same layout as the screen and the PDF,
    with a character as the unit."""
    rows = lyric_rows(project)
    out = [f"{k} : {v}" for k, v in header(project)]
    if approximate(rows):
        out.append(
            translate(
                "Export",
                "(Accords placés approximativement dans les lignes sans minutage des mots.)",
            )
        )
    out.append("")
    for row in rows:
        if row["kind"] == "section":
            out += ["", f"[{row['text']}]"]
        elif row["kind"] == "break":
            out.append("")
        elif row["kind"] == "chords":
            out.append("  ".join(c["label"] for c in row["chords"]))
        else:
            for vis in L.layout(row["text"], row["chords"], width, len, len, 1):
                above = ""
                for x, n in vis["chords"]:
                    above = above.ljust(int(x)) + row["chords"][n]["label"]
                text = ""
                for x, piece, _ in vis["runs"]:
                    text = text.ljust(int(x)) + piece
                if above:
                    out.append(above.rstrip())
                out.append(text.rstrip())
    out.append("")
    out.append(
        translate("Export", "Paroles : {kind}").format(
            kind=translate("Lyrics", L.KINDS.get(project.lyrics["source"].get("kind"), ""))
        )
        + (
            f" ({translate('LyricsOnline', project.lyrics['source']['name'])})"
            if project.lyrics["source"].get("name")
            else ""
        )
    )
    out.append(
        translate(
            "Export",
            "(LocalChords {version} : accords extraits automatiquement, à vérifier à l'oreille.)",
        ).format(version=__version__)
    )
    return "\n".join(out) + "\n"
