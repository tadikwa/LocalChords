"""Guitar and piano positions, each checked by the notes it really makes, not by its picture."""

import pytest

from localchords import voicings as v
from localchords.chords import QUALITIES, name_to_pc

ALL = [(r, q) for r in range(12) for q in QUALITIES]


def basses(root, quality):
    """No other bass, each chord note, and two notes outside the chord (the engine can say so)."""
    return [None, *v.tones(root, quality), (root + 2) % 12, (root + 10) % 12]


def assert_plays(f: v.Fingering, chord_tones, bass, capo=0):
    notes = f.notes(capo)
    assert len(notes) >= 4
    lowest = min(notes)
    assert lowest % 12 == bass, f"{f.text}: lowest note is not the bass"
    above = list(notes)
    above.remove(lowest)
    assert all(n % 12 in chord_tones for n in above), f"{f.text}: a note outside the chord"
    missing = set(chord_tones) - {n % 12 for n in notes}
    assert not missing or (missing == {(chord_tones[0] + 7) % 12} and len(chord_tones) >= 4), (
        f"{f.text}: missing {missing}"
    )
    # One hand: every fretted string has a finger, four fingers at most, within reach.
    fretted = [s for s, x in enumerate(f.frets) if x]
    assert all(f.fingers[s] in (1, 2, 3, 4) for s in fretted)
    assert all(f.fingers[s] is None for s, x in enumerate(f.frets) if not x)
    assert f.highest_fret - f.lowest_fret <= v.REACH
    if f.barre:
        fret, first, last = f.barre
        assert all(f.frets[s] is not None and f.frets[s] >= fret for s in range(first, last + 1))
        assert all(f.fingers[s] == 1 for s in range(first, last + 1) if f.frets[s] == fret)
        assert len({f.fingers[s] for s in fretted if f.fingers[s] != 1}) == len(
            [s for s in fretted if f.fingers[s] != 1]
        ), "one finger, one string, outside the barre"
    else:
        assert len({f.fingers[s] for s in fretted}) == len(fretted)


@pytest.mark.parametrize(("root", "quality"), ALL)
def test_every_guitar_position_plays_the_chord_over_its_bass(root, quality):
    chord_tones = v.tones(root, quality)
    for bass in basses(root, quality):
        positions = v.guitar(root, quality, bass)
        assert positions, "a position exists for every chord in standard tuning"
        for f in positions:
            assert_plays(f, chord_tones, root if bass is None else bass)
        assert len(set(positions)) == len(positions)


# What a guitarist expects first, and its fingers (low E first, . for none).
FIRST = {
    "C": ("x32010", ".32.1."),
    "Cm": ("x35543", ".13421"),
    "D": ("xx0232", "...132"),
    "Dm": ("xx0231", "...231"),
    "E": ("022100", ".231.."),
    "Em": ("022000", ".12..."),
    "F": ("133211", "134211"),
    "F#m": ("244222", "134111"),
    "G": ("320003", "21...3"),
    "G7": ("320001", "32...1"),
    "A": ("x02220", "..123."),
    "Am": ("x02210", "..231."),
    "Bm": ("x24432", ".13421"),
    "C7": ("x32310", ".3241."),
    "A7": ("x02020", "..1.2."),
    "Dm7": ("xx0211", "...211"),
    "Am7": ("x02010", "..2.1."),
    "Asus2": ("x02200", "..12.."),
    "Dsus4": ("xx0233", "...123"),
    "Esus4": ("022200", ".123.."),
    "E7sus4": ("020200", ".1.2.."),
    "C+": ("x32110", ".4312."),
    "Cmaj7": ("x32000", ".21..."),
    "Fmaj7": ("xx3210", "..321."),
    "Am6": ("x02212", "..2314"),
    "B7": ("x21202", ".213.4"),
    "Cadd9": ("x32030", ".21.3."),
}


def label_of(text):
    from localchords.chords import parse_symbol

    label, bass = parse_symbol(text)
    root, quality = label.split(":")
    return name_to_pc(root), quality, None if bass is None else name_to_pc(bass)


@pytest.mark.parametrize("name", FIRST)
def test_the_usual_shape_comes_first_with_its_usual_fingers(name):
    root, quality, bass = label_of(name)
    first = v.guitar(root, quality, bass)[0]
    frets, fingers = FIRST[name]
    assert first.text == frets
    assert "".join(str(x) if x else "." for x in first.fingers) == fingers


def test_b_minor_is_the_barre_on_the_second_fret():
    bm = v.guitar(11, "min")[0]
    assert bm.frets == (None, 2, 4, 4, 3, 2)
    assert bm.barre == (2, 1, 5)
    assert bm.kind == "Barré en case 2"
    assert sorted(n % 12 for n in bm.notes()) == sorted([11, 6, 11, 2, 6])
    # Other places on the neck, going up: the barre on the 7th fret is among them.
    assert "799777" in [f.text for f in v.guitar(11, "min")]
    frets = [f.lowest_fret for f in v.guitar(11, "min")[1:]]
    assert frets == sorted(frets)


def test_open_and_muted_strings():
    c = v.guitar(0, "maj")[0]
    assert c.frets[0] is None and c.frets[3] == 0 and c.frets[5] == 0
    assert c.kind == "Position ouverte" and c.barre is None
    f = v.guitar(5, "maj")[0]
    assert f.barre == (1, 0, 5) and 0 not in f.frets


@pytest.mark.parametrize(
    ("name", "frets"),
    [("C/E", "032010"), ("D/F#", "2x0232"), ("Bm/F#", "224432"), ("G/B", "x20003"),
     ("Am/G", "3x2210"), ("Am/C", "x32210"), ("F/C", "x33211")],
)  # fmt: skip
def test_chords_over_another_bass_put_it_at_the_bottom(name, frets):
    root, quality, bass = label_of(name)
    positions = v.guitar(root, quality, bass)
    assert positions[0].text == frets
    for f in positions:
        assert min(f.notes()) % 12 == bass


def test_a_wrong_bass_is_never_offered_as_the_inversion():
    # x32010 is C, but its bass is C: it must not stand for C/E or C/G.
    for bass in (4, 7):
        assert "x32010" not in [f.text for f in v.guitar(0, "maj", bass)]
    # The lowest note is the lowest pitch, not the lowest string.
    assert v.check((None, 10, 0, None, None, None), (2, 7, 11), 7) is None


def test_a_high_capo_can_leave_no_position_and_says_so():
    assert v.guitar(0, "min", 2, capo=11) == ()
    assert v.guitar(0, "min", None, capo=11)  # without the odd bass there is one


def test_classics_are_checked_like_the_rest():
    for label, shapes in v.CLASSICS.items():
        chord, _, bass = label.partition("/")
        root, quality = chord.split(":")
        r = name_to_pc(root)
        b = name_to_pc(bass) if bass else r
        for text in shapes:
            f = v.check(v.parse_frets(text), v.tones(r, quality), b)
            assert f is not None, label
            assert v.guitar(r, quality, None if b == r else b)[0].text == text, label


@pytest.mark.parametrize("capo", [0, 2, 5, 7])
def test_with_a_capo_the_shape_sounds_as_the_heard_chord(capo):
    # F♯m heard, capo on the 2nd fret: an E minor shape.
    shown = v.describe("F#:min", capo=capo)
    shape, sound = shown.shape, shown.sound
    assert sound.root == 6 and sound.title == "F♯m"
    assert shape.root == (6 - capo) % 12
    for f in v.guitar(shape.root, shape.quality, shape.bass, capo):
        assert {n % 12 for n in f.notes(capo)} <= set(sound.tones)
        assert min(f.notes(capo)) % 12 == sound.bass
    if capo == 2:
        assert shape.title == "Em"
        assert v.guitar(shape.root, shape.quality, shape.bass, capo)[0].text == "022000"


def test_transposition_and_capo_together():
    shown = v.describe("C:maj", "E", transpose=2, capo=2)
    assert shown.shape.title == "C/E" and shown.sound.title == "D/F♯"
    assert (shown.sound.root, shown.sound.bass) == (2, 6)
    assert v.guitar(shown.shape.root, "maj", shown.shape.bass, 2)[0].text == "032010"


def test_no_chord_has_no_diagram():
    assert v.describe("N") is None
    assert v.describe(None) is None


def test_the_diagrams_drop_the_bass_when_the_grid_does():
    assert v.describe("C:maj", "E", show_bass=False).shape.bass == 0
    simple = v.describe("G:7", "F", simplify=True).shape
    assert (simple.quality, simple.bass, simple.title) == ("maj", 7, "G")


def test_note_names_follow_the_spelling_and_the_notation():
    bm = v.describe("B:min").sound
    assert [bm.names[pc] for pc in bm.tones] == ["B", "D", "F♯"]
    assert [v.describe("B:min", latin=True).sound.names[pc] for pc in bm.tones] == [
        "Si",
        "Ré",
        "Fa♯",
    ]
    eb = v.describe("D#:maj", key="Eb:maj").sound
    assert eb.title == "E♭" and [eb.names[pc] for pc in eb.tones] == ["E♭", "G", "B♭"]
    # The same keys, written as asked: sounds do not change, names do.
    sharp = v.describe("A#:min", accidentals="sharps").sound
    flat = v.describe("A#:min", accidentals="flats").sound
    assert sharp.tones == flat.tones == (10, 1, 5)
    assert [sharp.names[p] for p in sharp.tones] == ["A♯", "C♯", "F"]
    assert [flat.names[p] for p in flat.tones] == ["B♭", "D♭", "F"]
    # A slash bass outside the chord gets a name too.
    am_g = v.describe("A:min", "G").sound
    assert am_g.names[7] == "G"


def test_spelling_by_interval():
    assert v.spell("C", "dim7") == {0: "C", 3: "Eb", 6: "Gb", 9: "A"}
    assert v.spell("C", "aug")[8] == "G#"
    assert v.spell("C#", "maj")[5] == "F"  # E♯ is never written


@pytest.mark.parametrize(("root", "quality"), ALL)
def test_every_piano_voicing_has_the_chord_and_the_bass_at_the_bottom(root, quality):
    chord_tones = set(v.tones(root, quality))
    for bass in basses(root, quality):
        b = root if bass is None else bass
        voicings = v.piano(root, quality, bass)
        assert voicings
        for voicing in voicings:
            notes = voicing.notes
            # Without another bass, the inversions are the pianist's choice; with one, never.
            if b == root and voicing.name in v.INVERSIONS[1:]:
                k = v.INVERSIONS.index(voicing.name)
                assert min(notes) % 12 == v.tones(root, quality)[k]
            else:
                assert min(notes) % 12 == b, voicing.name
            assert {n % 12 for n in notes} >= chord_tones
            assert {n % 12 for n in notes} <= chord_tones | {b}
            assert min(notes) >= v.LOW_KEY and max(notes) <= v.HIGH_KEY
            assert list(notes) == sorted(notes) and len(set(notes)) == len(notes)
            if voicing.left:
                assert max(voicing.left) < min(voicing.right)


def test_piano_inversions_of_b_minor():
    names = [x.name for x in v.piano(11, "min")]
    assert names[:3] == ["Position fondamentale", "1er renversement", "2e renversement"]
    lows = [min(x.notes) % 12 for x in v.piano(11, "min")[:3]]
    assert lows == [11, 2, 6]
    assert v.piano(11, "min")[0].notes == (59, 62, 66)  # B3 D4 F♯4, close position
    assert len(v.piano(7, "7")) == 5  # four inversions and the two hands


def test_piano_c_over_e():
    first, *two_hands = v.piano(0, "maj", 4)
    assert first.name == "1er renversement" and first.notes == (64, 67, 72)
    assert all(x.left == (52,) for x in two_hands)
    assert two_hands[0].right == (60, 64, 67)


def test_the_title_and_the_notes_name_the_bass_alike():
    assert v.describe("E:maj", "G#", key="C:maj").sound.title == "E/G♯"
    assert v.describe("D:maj", "F#", key="A#:maj").sound.title == "D/F♯"
    # Every key, every chord-note bass: the title and the note under the string agree.
    for key in [f"{n}:{m}" for n in v.SHARP_NAMES for m in ("maj", "min")]:
        for root, quality in ALL:
            for bass in v.tones(root, quality)[1:]:
                s = v.describe(f"{v.SHARP_NAMES[root]}:{quality}", v.SHARP_NAMES[bass], key=key)
                if s:
                    assert s.sound.title.endswith("/" + s.sound.names[bass]), (key, s.sound.title)
