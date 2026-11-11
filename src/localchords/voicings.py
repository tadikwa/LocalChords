"""How to play a chord: guitar fingerings and piano voicings, worked out from its notes.

Nothing here is drawn. Every position is a list of real notes, kept only if those notes are the
chord's, with the requested bass at the bottom; tests check it for every root, quality and bass.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from PySide6.QtCore import QT_TRANSLATE_NOOP

from .chords import (
    QUALITIES,
    SHARP_NAMES,
    name_to_pc,
    parse,
    pretty_note,
    spell,
    spell_root,
    symbol,
    transpose_key,
)
from .i18n import translate

# Standard tuning, low string first: E2 A2 D3 G3 B3 E4.
TUNING = (40, 45, 50, 55, 59, 64)
MAX_FRET = 15  # on the neck, capo included: higher, frets are too narrow to read
REACH = 3  # frets between the lowest and the highest finger, a hand's span
MAX_POSITIONS = 6

# Letters above the root for each interval, for spelling: a minor third is a third (E♭, not D♯).

# Shapes a guitarist learns first, preferred when they are valid. Low string first, x = muted.
# They still go through the same checks as the generated ones (tests/test_voicings.py).
CLASSICS = {
    "C:maj": ["x32010"], "A:maj": ["x02220"], "G:maj": ["320003"], "E:maj": ["022100"],
    "D:maj": ["xx0232"], "F:maj": ["133211"],
    "A:min": ["x02210"], "E:min": ["022000"], "D:min": ["xx0231"], "B:min": ["x24432"],
    "C:min": ["x35543"], "F#:min": ["244222"], "F:min": ["133111"], "G:min": ["355333"],
    "C#:min": ["x46654"],
    "C:7": ["x32310"], "A:7": ["x02020"], "G:7": ["320001"], "E:7": ["020100"],
    "D:7": ["xx0212"], "B:7": ["x21202"], "F:7": ["131211"],
    "C:maj7": ["x32000"], "A:maj7": ["x02120"], "G:maj7": ["320002"], "E:maj7": ["021100"],
    "D:maj7": ["xx0222"], "F:maj7": ["xx3210"],
    "A:min7": ["x02010"], "E:min7": ["020000"], "D:min7": ["xx0211"], "B:min7": ["x20202"],
    "F#:min7": ["242222"], "C:min7": ["x35343"],
    "A:sus2": ["x02200"], "D:sus2": ["xx0230"], "C:sus2": ["x30013"],
    "A:sus4": ["x02230"], "D:sus4": ["xx0233"], "E:sus4": ["022200"], "C:sus4": ["x33011"],
    "A:sus4(b7)": ["x02030"], "D:sus4(b7)": ["xx0213"], "E:sus4(b7)": ["020200"],
    "C:aug": ["x32110"], "E:aug": ["032110"],
    "A:min6": ["x02212"], "E:min6": ["022020"], "D:min6": ["xx0201"],
    "C:maj(9)": ["x32030"], "G:maj(9)": ["320203"],
    "B:maj": ["x24442"], "A#:maj": ["x13331"], "C#:maj": ["x46664"], "D#:maj": ["x68886"],
    "F#:maj": ["244322"], "G#:maj": ["466544"],
    "A#:min": ["x13321"], "D#:min": ["x68876"], "G#:min": ["466444"],
    "F#:7": ["242322"], "C#:7": ["x46464"],
    "C:maj/E": ["032010"], "C:maj/G": ["332010"], "D:maj/F#": ["2x0232"],
    "G:maj/B": ["x20003"], "A:min/C": ["x32210"], "A:min/G": ["3x2210"], "F:maj/C": ["x33211"],
    "B:min/F#": ["224432"],
}  # fmt: skip


def tones(root: int, quality: str) -> tuple[int, ...]:
    """The chord's pitch classes, root first, in the order of its intervals."""
    return tuple((root + t) % 12 for t in QUALITIES[quality][2])


@dataclass(frozen=True)
class Chord:
    """A chord to play: what the diagrams need, already transposed."""

    root: int
    quality: str
    bass: int  # the root when there is no other bass
    title: str  # as the grid writes it
    names: dict  # pitch class → note name as the interface writes it (bass included)

    @property
    def tones(self) -> tuple[int, ...]:
        return tones(self.root, self.quality)

    @property
    def inverted(self) -> bool:
        return self.bass != self.root


@dataclass(frozen=True)
class Shown:
    """A grid cell's chord, for the guitar (a shape above the capo) and the piano (the sound)."""

    shape: Chord  # what the guitar plays: the grid's chord, with the capo taken into account
    sound: Chord  # what is heard: the chord the piano plays
    capo: int


def describe(
    label: str | None,
    bass: str | None = None,
    *,
    key: str | None = None,
    transpose: int = 0,
    capo: int = 0,
    accidentals: str = "auto",
    simplify: bool = False,
    show_bass: bool = True,
    latin: bool = False,
) -> Shown | None:
    """The chord of a grid cell as the grid shows it, or None for N.C. The bass is kept as the grid
    shows it: hidden or simplified away, the diagrams drop it too, so that they never disagree."""
    parsed = parse(label)
    if parsed is None:
        return None
    pc, quality = parsed
    if simplify:
        quality = QUALITIES[quality][3]
    bass_pc = name_to_pc(bass) if bass and show_bass and not simplify else pc

    def chord(shift: int) -> Chord:
        moved_key = transpose_key(key, shift)
        root_name = spell_root(pc + shift, moved_key, accidentals)
        names = spell(root_name, quality, accidentals)
        b = (bass_pc + shift) % 12
        if b not in names:
            names[b] = spell_root(b, moved_key, accidentals)
        names = {k: pretty_note(v, latin=latin) for k, v in names.items()}
        title = symbol(
            label,
            bass,
            key=key,
            semitones=shift,
            accidentals=accidentals,
            simplify=simplify,
            show_bass=show_bass,
            latin=latin,
        )
        return Chord((pc + shift) % 12, quality, b, title, names)

    return Shown(chord(transpose - capo), chord(transpose), capo)


# Guitar ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fingering:
    frets: tuple  # per string, low E first: None muted, 0 open, else the fret above the capo
    fingers: tuple  # 1 (index) to 4 (little finger) per fretted string, None elsewhere
    barre: tuple | None  # (fret, first string, last string), strings counted from the low E

    def notes(self, capo: int = 0) -> list[int]:
        """The MIDI notes that sound, low string first."""
        return [TUNING[s] + capo + f for s, f in enumerate(self.frets) if f is not None]

    @property
    def lowest_fret(self) -> int:
        return min((f for f in self.frets if f), default=0)

    @property
    def highest_fret(self) -> int:
        return max((f for f in self.frets if f), default=0)

    @property
    def kind(self) -> str:
        if self.barre:
            return translate("Voicings", "Barré en case {fret}").format(fret=self.barre[0])
        if 0 in self.frets and self.highest_fret <= 4:
            return translate("Voicings", "Position ouverte")
        return translate("Voicings", "Case {fret}").format(fret=self.lowest_fret)

    @property
    def text(self) -> str:
        """`x24432`, or with dashes when a fret has two digits: `x-10-12-12-12-10`."""
        parts = ["x" if f is None else str(f) for f in self.frets]
        return "-".join(parts) if any(len(p) > 1 for p in parts) else "".join(parts)


def parse_frets(text: str) -> tuple:
    parts = text.split("-") if "-" in text else list(text)
    return tuple(None if p in "xX" else int(p) for p in parts)


def _fingers(frets: tuple) -> tuple[tuple, tuple | None] | None:
    """Which finger presses which string, or None if one hand cannot hold it.

    The index lies flat across the lowest fret (a barre) when more than four strings are fretted;
    the index also covers the top strings when they share its fret. The others take the notes in
    order of fret, then from the low string, a finger per fret when there are fingers to spare."""
    fretted = [(s, f) for s, f in enumerate(frets) if f]
    if not fretted:
        return tuple(None for _ in frets), None
    low = min(f for _, f in fretted)
    if max(f for _, f in fretted) - low > REACH:
        return None
    barre = None
    rest = fretted
    first_finger = 1
    on_low = [s for s, f in fretted if f == low]
    first, last = min(on_low), max(on_low)
    # Under a barre every string sounds at least at its fret: nothing open, nothing muted.
    can_barre = last > first and all(
        frets[s] is not None and frets[s] >= low for s in range(first, last + 1)
    )
    top = max(s for s, f in enumerate(frets) if f is not None)
    # Needed past four fretted strings; taken too when the index can cover the top strings (Dm7).
    flat = can_barre and all(frets[s] == low for s in range(first, last + 1))
    if len(fretted) > 4 or (flat and last == top):
        if not can_barre:
            return None
        barre = (low, first, last)
        rest = [(s, f) for s, f in fretted if not (first <= s <= last and f == low)]
        first_finger = 2
    order = sorted(rest, key=lambda sf: (sf[1], sf[0]))
    if len(order) > 5 - first_finger:
        return None
    spaced, sequential, previous = [], [], first_finger - 1
    for i, (_, f) in enumerate(order):
        spaced.append(max(previous + 1, 1 + f - low))
        previous = spaced[-1]
        sequential.append(first_finger + i)
    chosen = spaced if spaced and spaced[-1] <= 4 else sequential
    fingers = [None] * len(frets)
    for (s, _), finger in zip(order, chosen, strict=True):
        fingers[s] = finger
    if barre:
        for s in range(barre[1], barre[2] + 1):
            if frets[s] == low:
                fingers[s] = 1
    return tuple(fingers), barre


def check(frets: tuple, chord_tones: tuple, bass: int) -> Fingering | None:
    """The fingering, if `frets` really plays this chord over this bass and one hand can hold it."""
    played = [s for s, f in enumerate(frets) if f is not None]
    if len(played) < 4:
        return None
    notes = [TUNING[s] + frets[s] for s in played]
    lowest = notes.index(min(notes))
    if notes[lowest] % 12 != bass:
        return None
    # Above the bass, only the chord's notes: a foreign bass sounds once, at the bottom.
    if any(n % 12 not in chord_tones for i, n in enumerate(notes) if i != lowest):
        return None
    heard = {n % 12 for n in notes}
    missing = set(chord_tones) - heard
    fifth = (chord_tones[0] + 7) % 12
    # In a chord of four notes or more, the fifth may go, as guitarists do; nothing else.
    if missing and not (missing == {fifth} and len(chord_tones) >= 4 and fifth != bass):
        return None
    # Mutes on the low side are fine; inside the chord, one at most.
    if sum(1 for s in range(played[0], played[-1] + 1) if frets[s] is None) > 1:
        return None
    if 0 in frets and max(f for f in frets if f is not None) > 4:
        return None  # open strings with the hand up the neck: hard to make ring together
    hand = _fingers(frets)
    if hand is None:
        return None
    return Fingering(tuple(frets), *hand)


def _cost(f: Fingering, chord_tones: tuple) -> float:
    """Lower is easier: low on the neck, many strings, few fingers, no barre, no gaps."""
    played = [x for x in f.frets if x is not None]
    first = next(i for i, x in enumerate(f.frets) if x is not None)
    last = max(i for i, x in enumerate(f.frets) if x is not None)
    inner_mutes = sum(1 for x in f.frets[first : last + 1] if x is None)
    heard = {(TUNING[s] + x) % 12 for s, x in enumerate(f.frets) if x is not None}
    cost = 2.0 * f.lowest_fret + 3.0 * (6 - len(played)) + 4.0 * inner_mutes
    cost += 3.0 * (5 - last)  # a muted top string is rare
    cost += 3.0 if f.barre else 0.0
    if f.barre and any(f.frets[i] for i in range(f.barre[1])):
        cost += 6.0  # a partial barre with a finger on a lower string: the hand twists
    span = f.highest_fret - f.lowest_fret
    cost += 2.0 * span + (6.0 if span >= 3 else 0.0)  # four frets apart is a real stretch
    cost += 1.0 * sum(1 for x in f.fingers if x)
    cost += 6.0 * len(set(chord_tones) - heard)
    if f.highest_fret <= 4:
        cost -= 1.0 * played.count(0)
    return cost


@lru_cache(maxsize=1024)
def guitar(root: int, quality: str, bass: int | None = None, capo: int = 0) -> tuple:
    """Fingerings for the chord in standard tuning, easiest first: the classic shape when there is
    one, then others up the neck. Empty when no valid position holds this bass."""
    chord_tones = tones(root, quality)
    bass = root if bass is None else bass
    allowed = set(chord_tones) | {bass}
    found: dict[tuple, Fingering] = {}
    for low in range(1, MAX_FRET - capo - REACH + 1):
        options = []
        for open_note in TUNING:
            choice = [None]
            if open_note % 12 in allowed and low <= 4:
                choice.append(0)
            choice += [f for f in range(low, low + REACH + 1) if (open_note + f) % 12 in allowed]
            options.append(choice)
        for frets in product(*options):
            if frets in found or low not in frets:
                continue
            fingering = check(frets, chord_tones, bass)
            if fingering:
                found[frets] = fingering
    ranked = sorted(found.values(), key=lambda f: (_cost(f, chord_tones), f.text))
    label = f"{SHARP_NAMES[root]}:{quality}" + (f"/{SHARP_NAMES[bass]}" if bass != root else "")
    classics = [
        found[frets] for frets in map(parse_frets, CLASSICS.get(label, [])) if frets in found
    ]
    out: list[Fingering] = []
    for f in [*classics, *ranked]:
        if f in out:
            continue
        # The same shape with one more string muted adds nothing.
        if any(_covers(o.frets, f.frets) for o in out):
            continue
        if any(o.kind == f.kind for o in out):
            continue  # one per place on the neck: the alternatives are other places
        out.append(f)
        if len(out) == MAX_POSITIONS:
            break
    # The easiest first, then up the neck, so that "next" means "higher".
    return tuple(out[:1] + sorted(out[1:], key=lambda f: (f.lowest_fret, f.highest_fret)))


def _covers(better: tuple, other: tuple) -> bool:
    return all(o is None or o == b for b, o in zip(better, other, strict=True))


# Piano ----------------------------------------------------------------------------------------
LOW_KEY, HIGH_KEY = 48, 83  # the keyboard drawn: C3 to B5
INVERSIONS = (
    QT_TRANSLATE_NOOP("Voicings", "Position fondamentale"),
    QT_TRANSLATE_NOOP("Voicings", "1er renversement"),
    QT_TRANSLATE_NOOP("Voicings", "2e renversement"),
    QT_TRANSLATE_NOOP("Voicings", "3e renversement"),
)


@dataclass(frozen=True)
class PianoVoicing:
    name: str
    left: tuple  # MIDI notes for the left hand, empty for a one-hand voicing
    right: tuple

    @property
    def notes(self) -> tuple:
        return self.left + self.right


def _stack(pcs, lowest_from: int) -> tuple:
    """The pitch classes upward in order, close together, the first at or above `lowest_from`."""
    notes = []
    for pc in pcs:
        floor = notes[-1] + 1 if notes else lowest_from
        notes.append(floor + (pc - floor) % 12)
    return tuple(notes)


@lru_cache(maxsize=1024)
def piano(root: int, quality: str, bass: int | None = None) -> tuple:
    """Close voicings around middle C: the inversions with one hand, then the bass in the left hand
    under the chord in the right. With another bass, only voicings that put it at the bottom."""
    chord_tones = tones(root, quality)
    bass = root if bass is None else bass
    out = []
    if bass == root:
        for k in range(len(chord_tones)):
            order = chord_tones[k:] + chord_tones[:k]
            out.append(PianoVoicing(translate("Voicings", INVERSIONS[k]), (), _stack(order, 55)))
    else:
        if bass in chord_tones:
            k = chord_tones.index(bass)
            name, order = translate("Voicings", INVERSIONS[k]), chord_tones[k:] + chord_tones[:k]
        else:
            name, order = translate("Voicings", "Basse ajoutée"), (bass, *chord_tones)
        # A foreign bass under the whole chord spans more: start it lower to stay on the keys.
        out.append(PianoVoicing(name, (), _stack(order, 55 if bass in chord_tones else 48)))
    left = _stack([bass], 48)
    for k in range(len(chord_tones) if bass != root else 1):
        order = chord_tones[k:] + chord_tones[:k]
        hand = (
            translate("Voicings", "accord")
            if k == 0
            else translate("Voicings", INVERSIONS[k]).lower()
        )
        out.append(
            PianoVoicing(
                translate("Voicings", "Deux mains : basse et {hand}").format(hand=hand),
                left,
                _stack(order, 60),
            )
        )
    return tuple(out)
