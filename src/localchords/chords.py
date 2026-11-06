"""Chord labels: from the engine's Harte labels (`F#:hdim7`) to what a musician reads (`F♯m7♭5`)."""

from __future__ import annotations

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
MODE_NAMES = {"maj": "majeur", "min": "mineur"}


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
    if abs(diff) > 1:
        flat_side = tonic == "F" or "b" in tonic
        return (FLAT_NAMES if flat_side else SHARP_NAMES)[pc]
    return letter + ("#" if diff > 0 else "b")


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
    return f"{pretty_note(spell_tonic(*moved), latin=latin)} {MODE_NAMES[moved[1]]}"


def simplified(quality: str) -> str:
    """The triad a beginner would play: Dm7 → Dm, G7 → G, F♯m7♭5 → F♯°."""
    return QUALITIES[quality][3]


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
            bass_name = spell_root(bass_pc + semitones, moved_key, accidentals)
            text += "/" + pretty_note(bass_name, ascii_only=ascii_only, latin=latin)
    return text
