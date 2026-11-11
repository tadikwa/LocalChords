"""Chord labels: from the engine's Harte labels (`F#:hdim7`) to what a musician reads (`F♯m7♭5`)."""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

from .i18n import translate

LETTERS = "CDEFGAB"
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LATIN = {"C": "Do", "D": "Ré", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# How a key is usually written; the minor list keeps C# and G# minor rather than Db and Ab minor.
MAJOR_TONICS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_TONICS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
# Scale degree (0 = the tonic's letter) of each semitone above the tonic: b2, b3, #4, b6 and b7
# take the letter a chart gives them, in major and in minor (whose raised 3, 6 and 7 fall on the
# same letters).
DEGREES = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6]

# Quality → (unicode suffix, ascii suffix, tones above the root, reduced triad).
QUALITIES = {
    "maj": ("", "", (0, 4, 7), "maj"),
    "min": ("m", "m", (0, 3, 7), "min"),
    "7": ("7", "7", (0, 4, 7, 10), "maj"),
    "maj7": ("maj7", "maj7", (0, 4, 7, 11), "maj"),
    "min7": ("m7", "m7", (0, 3, 7, 10), "min"),
    "min6": ("m6", "m6", (0, 3, 7, 9), "min"),
    "hdim7": ("m7♭5", "m7b5", (0, 3, 6, 10), "dim"),
    "dim7": ("°7", "dim7", (0, 3, 6, 9), "dim"),
    "dim": ("°", "dim", (0, 3, 6), "dim"),
    "aug": ("+", "aug", (0, 4, 8), "aug"),
    "sus4": ("sus4", "sus4", (0, 5, 7), "sus4"),
    "sus2": ("sus2", "sus2", (0, 2, 7), "sus2"),
    "sus4(b7)": ("7sus4", "7sus4", (0, 5, 7, 10), "sus4"),
    "maj(9)": ("add9", "add9", (0, 2, 4, 7), "maj"),
    "min(9)": ("madd9", "madd9", (0, 2, 3, 7), "min"),
}
# A key's name in the interface's language; the tonic itself follows the notation setting.
MODE_NAMES = {
    "maj": QT_TRANSLATE_NOOP("Chords", "{tonic} majeur"),
    "min": QT_TRANSLATE_NOOP("Chords", "{tonic} mineur"),
}


def name_to_pc(name: str) -> int:
    """Pitch class of a note name such as `F#`, `Bb` or `B♭`."""
    letter, accidentals = name[0].upper(), name[1:]
    if letter not in NATURAL or any(c not in "#b♯♭" for c in accidentals):
        raise ValueError(f"not a note name: {name!r}")
    return (NATURAL[letter] + sum(1 if c in "#♯" else -1 for c in accidentals)) % 12


def parse(label: str | None) -> tuple[int, str] | None:
    """(root pitch class, quality) of a Harte label, or None for N (no chord)."""
    if not label or label == "N":
        return None
    root, _, quality = label.partition(":")
    quality = quality or "maj"
    if quality not in QUALITIES:
        raise ValueError(f"unknown chord quality: {label!r}")
    return name_to_pc(root), quality


def make(pc: int, quality: str) -> str:
    """The engine's label for a root pitch class and a quality."""
    return f"{SHARP_NAMES[pc % 12]}:{quality}"


def parse_key(key: str | None) -> tuple[int, str] | None:
    """(tonic pitch class, mode) of a key label such as `A:min`."""
    if not key:
        return None
    root, _, mode = key.partition(":")
    return name_to_pc(root), "min" if mode == "min" else "maj"


def spell_tonic(pc: int, mode: str) -> str:
    return (MINOR_TONICS if mode == "min" else MAJOR_TONICS)[pc % 12]


def spell_root(pc: int, key: tuple[int, str] | None, accidentals: str = "auto") -> str:
    """A root's name: forced sharps or flats, or by its scale degree in the key.

    The degree gives the letter, so a bVII in C is B♭ and not A♯, and the V of A minor's E7 has a
    G♯. A spelling that would need a double accidental falls back to the plain name.
    """
    pc %= 12
    if accidentals == "sharps":
        return SHARP_NAMES[pc]
    if accidentals == "flats":
        return FLAT_NAMES[pc]
    if key is None:
        return FLAT_NAMES[pc] if pc in (3, 8, 10) else SHARP_NAMES[pc]
    tonic_pc, mode = key
    tonic = spell_tonic(tonic_pc, mode)
    letter = LETTERS[(LETTERS.index(tonic[0]) + DEGREES[(pc - tonic_pc) % 12]) % 7]
    diff = (pc - NATURAL[letter] + 6) % 12 - 6
    if diff == 0:
        return letter
    name = letter + ("#" if diff > 0 else "b")
    # Cb, Fb, E# and B# are right in theory, but no chart writes a chord's root that way.
    if abs(diff) > 1 or name in ("Cb", "Fb", "E#", "B#"):
        flat_side = tonic == "F" or "b" in tonic
        return (FLAT_NAMES if flat_side else SHARP_NAMES)[pc]
    return name


def pretty_note(name: str, *, ascii_only: bool = False, latin: bool = False) -> str:
    letter, accidental = name[0], name[1:]
    base = LATIN[letter] if latin else letter
    if ascii_only:
        return base + accidental
    return base + accidental.replace("#", "♯").replace("b", "♭")


def transpose_key(key: str | None, semitones: int) -> tuple[int, str] | None:
    parsed = parse_key(key)
    return None if parsed is None else ((parsed[0] + semitones) % 12, parsed[1])


def key_name(key: str | None, semitones: int = 0, *, latin: bool = False) -> str:
    """`La mineur`, `F♯ majeur`: a key as the interface says it."""
    moved = transpose_key(key, semitones)
    if moved is None:
        return "—"
    tonic = pretty_note(spell_tonic(*moved), latin=latin)
    return translate("Chords", MODE_NAMES[moved[1]]).format(tonic=tonic)


def simplified(quality: str) -> str:
    """The triad a beginner would play: Dm7 → Dm, G7 → G, F♯m7♭5 → F♯°."""
    return QUALITIES[quality][3]


# Interval in semitones → letters above the root (a minor third is two letters up).
_LETTER_STEPS = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6}


def spell(root: str, quality: str, accidentals: str = "auto") -> dict[int, str]:
    """Pitch class → name for each note of the chord: by interval from a spelled root, so that
    B minor is B, D, F♯ and E♭ is E♭, G, B♭. A name needing a double accidental, or one that the
    program never writes (C♭, F♭, E♯, B♯), falls back to the plain name; forced sharps or flats
    are applied to every note."""
    root_pc = name_to_pc(root)
    out = {}
    for t in QUALITIES[quality][2]:
        pc = (root_pc + t) % 12
        if accidentals == "sharps":
            out[pc] = SHARP_NAMES[pc]
            continue
        if accidentals == "flats":
            out[pc] = FLAT_NAMES[pc]
            continue
        letter = LETTERS[(LETTERS.index(root[0]) + _LETTER_STEPS[t]) % 7]
        diff = (pc - NATURAL[letter] + 6) % 12 - 6
        name = letter + ("#" if diff > 0 else "b" if diff < 0 else "")
        if abs(diff) > 1 or name in ("Cb", "Fb", "E#", "B#"):
            flat_side = "b" in root or root == "F"
            name = (FLAT_NAMES if flat_side else SHARP_NAMES)[pc]
        out[pc] = name
    return out


def symbol(
    label: str | None,
    bass: str | None = None,
    *,
    key: str | None = None,
    semitones: int = 0,
    accidentals: str = "auto",
    simplify: bool = False,
    show_bass: bool = True,
    ascii_only: bool = False,
    latin: bool = False,
) -> str:
    """The chord as written on a chart, moved by `semitones` and spelled in the moved key."""
    parsed = parse(label)
    if parsed is None:
        return "N.C."
    pc, quality = parsed
    moved_key = transpose_key(key, semitones)
    root = spell_root(pc + semitones, moved_key, accidentals)
    if simplify:
        quality = simplified(quality)
    unicode_suffix, ascii_suffix, *_ = QUALITIES[quality]
    text = pretty_note(root, ascii_only=ascii_only, latin=latin)
    text += ascii_suffix if ascii_only else unicode_suffix
    if show_bass and bass and not simplify:
        bass_pc = name_to_pc(bass)
        if bass_pc != pc:
            # A chord note keeps its name in the chord (E/G♯, not E/A♭); another, its degree.
            moved_bass = (bass_pc + semitones) % 12
            in_chord = spell(root, quality, accidentals).get(moved_bass)
            bass_name = in_chord or spell_root(moved_bass, moved_key, accidentals)
            text += "/" + pretty_note(bass_name, ascii_only=ascii_only, latin=latin)
    return text


# What a musician types after the root, to the engine's quality. Longest first when matching.
TYPED_QUALITIES = {
    "": "maj", "maj": "maj", "M": "maj",
    "m": "min", "min": "min", "-": "min",
    "7": "7", "dom7": "7",
    "maj7": "maj7", "M7": "maj7", "Δ": "maj7", "Δ7": "maj7", "7M": "maj7",
    "m7": "min7", "min7": "min7", "-7": "min7",
    "m6": "min6", "min6": "min6", "-6": "min6",
    "m7b5": "hdim7", "m7♭5": "hdim7", "ø": "hdim7", "ø7": "hdim7", "-7b5": "hdim7",
    "dim7": "dim7", "°7": "dim7", "o7": "dim7",
    "dim": "dim", "°": "dim", "o": "dim",
    "aug": "aug", "+": "aug", "5+": "aug",
    "sus4": "sus4", "sus": "sus4",
    "sus2": "sus2",
    "7sus4": "sus4(b7)", "7sus": "sus4(b7)",
    "add9": "maj(9)", "madd9": "min(9)", "m(add9)": "min(9)",
}  # fmt: skip
_LATIN_ROOTS = {
    "do": "C",
    "ré": "D",
    "re": "D",
    "mi": "E",
    "fa": "F",
    "sol": "G",
    "la": "A",
    "si": "B",
}


def _roots(text: str) -> list[tuple[str, str]]:
    """Every way to read a root at the start of what was typed: (note, rest of the text)."""
    lowered = text.lower()
    out = []
    for latin in ("sol", "do", "ré", "re", "mi", "fa", "la", "si"):
        if lowered.startswith(latin):
            out.append((_LATIN_ROOTS[latin], text[len(latin) :]))
            break
    if text and text[0].upper() in NATURAL:
        out.append((text[0].upper(), text[1:]))
    read = []
    for letter, rest in out:
        # "Bb" is B flat; "Bbm" too. A lone lowercase b never starts a quality here.
        if rest[:1] and rest[0] in "#♯b♭":
            read.append((letter + ("#" if rest[0] in "#♯" else "b"), rest[1:]))
        read.append((letter, rest))
    return read


def parse_symbol(text: str) -> tuple[str, str | None] | None:
    """(label, bass) for a typed chord such as `F#m7b5/A`, `Bb`, `Rém7`, `N.C.`; None if unread.

    The Latin name wins an ambiguity (`Do7` is C7), but no reading is lost to it: `Fadd9` is F add9.
    """
    text = text.strip()
    if not text:
        return None
    if text.upper().replace(".", "") in ("N", "NC"):
        return "N", None
    chord, _, bass_text = text.partition("/")
    root = next(((n, r) for n, r in _roots(chord) if r in TYPED_QUALITIES), None)
    if root is None:
        return None
    label = make(name_to_pc(root[0]), TYPED_QUALITIES[root[1]])
    if not bass_text:
        return label, None
    bass = next((n for n, r in _roots(bass_text) if not r), None)
    if bass is None:
        return None
    return label, SHARP_NAMES[name_to_pc(bass)]
