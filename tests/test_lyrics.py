# The lyrics here are written for these tests (no song's words).
import pytest

from localchords import lyrics as L

LRC = """[ti:Petite chanson]
[ar:Personne]
[offset:+500]
[Couplet]
[00:10.00]Le café refroidit sur la table
[00:14.50]et la radio parle toute seule

[Refrain]
[00:20.00][00:40.00]Reviens demain, reviens
[00:30.00]
"""


def test_lrc_reads_sections_breaks_repeats_and_offset():
    lines = L.parse(LRC)
    texts = [(x["text"], x["start"], bool(x.get("section"))) for x in lines]
    assert texts == [
        ("Couplet", None, True),
        ("Le café refroidit sur la table", 9.5, False),
        ("et la radio parle toute seule", 14.0, False),
        ("", None, False),
        ("Refrain", None, True),
        ("Reviens demain, reviens", 19.5, False),
        ("", 29.5, False),
        ("Reviens demain, reviens", 39.5, False),
    ]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1252"])
def test_encodings(encoding):
    text = "[00:01.00]Été, où êtes-vous ?\n"
    assert L.parse(L.decode(text.encode(encoding)))[0]["text"] == "Été, où êtes-vous ?"


def test_plain_text_keeps_one_break_between_stanzas():
    lines = L.parse("Une ligne\n\n\n\nDeux lignes\n\n")
    assert [x["text"] for x in lines] == ["Une ligne", "", "Deux lignes"]
    assert all(x["start"] is None for x in lines)
    assert not L.timed({"lines": lines})


def test_srt():
    srt = (
        "1\n00:00:01,500 --> 00:00:03,000\nPremière <i>ligne</i>\n\n"
        "2\n00:01:02,250 --> 00:01:04,000\nSeconde\nsuite\n"
    )
    lines = L.parse(srt)
    assert lines == [
        {"text": "Première ligne", "start": 1.5, "end": 3.0},
        {"text": "Seconde suite", "start": 62.25, "end": 64.0},
    ]


def test_enhanced_lrc_word_times():
    (line,) = L.parse("[00:05.00]<00:05.00>Lune <00:05.80>pâle <00:06.40>au loin\n")
    assert line["text"] == "Lune pâle au loin"
    assert line["words"] == [[0, 5.0], [5, 5.8], [10, 6.4]]


def test_lrc_round_trip_applies_offset():
    lyr = L.new(L.parse("[00:10.00]Un\n[Pont]\nsans heure\n[00:12.34]Deux\n"), {"kind": "file"})
    lyr["offset"] = 0.5
    text = L.to_lrc(lyr, "T", "A")
    assert text.splitlines() == [
        "[ti:T]",
        "[ar:A]",
        "[00:10.50]Un",
        "[Pont]",
        "sans heure",
        "[00:12.84]Deux",
    ]
    assert [x["start"] for x in L.parse(text)] == [10.5, None, None, 12.84]


def test_line_at_follows_the_clock_with_offset():
    lyr = L.new(L.parse("[00:02.00]a\nb\n[00:05.00]c\n"), {"kind": "file"})
    assert L.line_at(lyr, 1.0) is None
    assert L.line_at(lyr, 2.0) == 0
    assert L.line_at(lyr, 4.9) == 0  # an untimed line is never "being sung"
    assert L.line_at(lyr, 5.0) == 2
    lyr["offset"] = 1.0
    assert L.line_at(lyr, 2.5) is None
    assert L.line_at(lyr, 3.0) == 0


def test_editor_round_trip_keeps_word_times_only_on_unchanged_lines():
    before = L.parse(
        "[00:05.00]<00:05.00>Lune <00:05.80>pâle\n[00:08.00]<00:08.00>Mer <00:08.50>grise\n"
    )
    text = L.to_editor(before).replace("Mer grise", "Mer bleue")
    after = L.from_editor(text, before)
    assert after[0]["words"] == before[0]["words"]
    assert after[1] == {"text": "Mer bleue", "start": 8.0}


def test_replaced_keeps_one_previous_version():
    a = L.new([{"text": "a", "start": None}], {"kind": "user"})
    b = L.replaced(a, [{"text": "b", "start": None}], {"kind": "file"})
    c = L.replaced(b, [{"text": "c", "start": None}], {"kind": "file"})
    assert c["previous"]["lines"][0]["text"] == "b"
    assert "previous" not in c["previous"]


def test_catalog_lyrics_are_never_exportable():
    assert not L.exportable(L.new([], {"kind": "catalog", "exportable": False}))
    assert L.exportable(L.new([], {"kind": "user", "exportable": True}))
    assert not L.exportable(None)


# Chords over words -----------------------------------------------------------------------------

SONG = "[00:04.00]Le vent tourne au coin de la rue\n[00:08.00]\n[00:10.00]et je reste là\n"
CHORDS = [
    (0.0, 4.0, "C"),
    (4.0, 6.0, "Am"),
    (6.0, 8.0, "F"),
    (8.0, 10.0, "G"),
    (10.0, 14.0, "C"),
    (14.0, 16.0, None),
]


def rows_of(lyr, chords=CHORDS, duration=16.0):
    return L.sheet(lyr, chords, duration)


def test_chords_go_over_the_line_sung_when_they_start():
    rows = rows_of(L.new(L.parse(SONG), {"kind": "file"}))
    kinds = [
        (r["kind"], r["text"], [(c["label"], c["char"], c["how"]) for c in r["chords"]])
        for r in rows
    ]
    assert kinds == [
        ("chords", "", [("C", 0, "approx")]),  # the intro, before any word
        (
            "line",
            "Le vent tourne au coin de la rue",
            [("Am", 0, "approx"), ("F", 15, "approx")],
        ),  # F halfway: "au", by proportion only
        ("chords", "", [("G", 0, "approx")]),  # the timed empty line: a gap with no words
        ("line", "et je reste là", [("C", 0, "approx")]),
    ]


def test_word_times_place_chords_exactly():
    text = "[00:04.00]<00:04.00>Le <00:04.30>vent <00:05.90>tourne <00:07.00>encore\n"
    rows = rows_of(L.new(L.parse(text), {"kind": "file"}), [(4.0, 6.0, "Am"), (6.0, 9.0, "F")])
    (line,) = [r for r in rows if r["kind"] == "line"]
    assert [(c["label"], c["char"], c["how"]) for c in line["chords"]] == [
        ("Am", 0, "word"),
        ("F", 8, "word"),
    ]  # F lands on "tourne", begun at 5.90


def test_manual_anchor_moves_the_chord_but_not_its_time():
    lyr = L.new(L.parse(SONG), {"kind": "file"})
    lyr["anchors"][L.chord_key(6.0)] = {"line": 0, "char": 3}
    line = [r for r in rows_of(lyr) if r["kind"] == "line"][0]
    f = [c for c in line["chords"] if c["label"] == "F"][0]
    assert (f["char"], f["how"], f["time"]) == (3, "manual", 6.0)


def test_a_chord_still_sounding_when_a_line_begins_is_shown_at_its_start():
    lyr = L.new(L.parse("[00:02.00]un\n[00:05.00]deux mots ici\n"), {"kind": "file"})
    rows = L.sheet(lyr, [(0.0, 3.0, "C"), (3.0, 9.0, "G"), (9.0, 12.0, "D")], 12.0)
    second = [r for r in rows if r["text"] == "deux mots ici"][0]
    assert [(c["label"], c["char"], c["how"]) for c in second["chords"]] == [
        ("G", 0, "held"),
        ("D", 5, "approx"),
    ]


def test_untimed_lyrics_get_no_chords_rather_than_invented_places():
    lyr = L.new(L.parse("une\ndeux\n"), {"kind": "user"})
    assert all(not r["chords"] for r in rows_of(lyr))


# Layout -----------------------------------------------------------------------------------------


def mono(s):
    return 10.0 * len(s)


def test_layout_widens_a_word_under_a_long_chord_name_and_keeps_names_apart():
    chords = [{"label": "Cmaj7/G", "char": 0}, {"label": "D", "char": 3}]
    (line,) = L.layout("ah oui", chords, 1000, mono, mono, 5)
    (x0, i0), (x1, i1) = line["chords"]
    assert x1 >= x0 + mono("Cmaj7/G") + 5  # never overlapping
    assert dict((first, x) for x, _, first in line["runs"])[3] == x1  # D stays over "oui"


def test_layout_leaves_no_hole_after_a_chord_when_the_next_word_has_none():
    text = "le long du canal"
    (line,) = L.layout(text, [{"label": "A/C#", "char": 0}], 1000, mono, mono, 5)
    assert [x for x, _, _ in line["runs"]] == [0.0, 30.0, 80.0, 110.0]  # as written


def test_layout_wraps_between_words_and_never_loses_text():
    text = "une ligne assez longue pour ne pas tenir sur une seule rangée"
    chords = [{"label": "Am", "char": 10}, {"label": "E7", "char": 50}]
    lines = L.layout(text, chords, 200, mono, mono, 5)
    assert len(lines) > 1
    assert "".join(p for ln in lines for _, p, _ in ln["runs"]) == text
    assert sum(len(ln["chords"]) for ln in lines) == 2
    for ln in lines:
        assert max(x + mono(p.rstrip()) for x, p, _ in ln["runs"]) <= 200


def test_layout_of_chords_at_the_very_end_of_a_line():
    (line,) = L.layout("fin", [{"label": "G", "char": 3}], 1000, mono, mono, 5)
    assert line["chords"] == [(30.0, 0)]


def test_char_at_finds_the_letter_under_a_drop():
    (line,) = L.layout("ah oui", [], 1000, mono, mono, 5)
    assert L.char_at(line["runs"], 0, mono) == 0
    assert L.char_at(line["runs"], 31, mono) == 3
    assert L.char_at(line["runs"], 46, mono) == 5


# In the project -----------------------------------------------------------------------------------


def test_project_keeps_lyrics_undo_and_old_version_when_none(tmp_path):
    from test_core import project

    p = project()
    p.save(tmp_path / "a.lchords")
    assert '"version": 1' in (tmp_path / "a.lchords").read_text(encoding="utf-8")
    lyr = L.new(L.parse("[00:01.00]Ça commence ici\n"), {"kind": "user", "exportable": True})
    p.set_lyrics(lyr)
    p.set_chord(0.0, 2.0, "D:min")
    changed = dict(p.lyrics, lines=[{"text": "Ça change", "start": 1.2}])
    p.set_lyrics(changed)
    p.save(tmp_path / "b.lchords")
    q = type(p).load(tmp_path / "b.lchords")
    assert q.to_dict()["version"] == 2
    assert q.lyrics["lines"] == [{"text": "Ça change", "start": 1.2}]
    assert q.lyrics["original"][0]["text"] == "Ça commence ici"
    p.undo()
    assert p.lyrics["lines"][0]["text"] == "Ça commence ici"
    assert p.edits["chords"]  # the chord edit came after the first lyrics
    p.undo()
    assert not p.edits["chords"] and p.lyrics["lines"][0]["text"] == "Ça commence ici"
    p.reset_edits()
    assert p.lyrics  # resetting chords keeps the words
    p.replace_analysis(p.analysis)
    assert p.lyrics


def test_damaged_lyrics_refuse_the_file_rather_than_lose_them(tmp_path):
    import json

    from test_core import project

    from localchords.project import ProjectError

    d = project().to_dict()
    d["lyrics"] = {"source": {}, "lines": [{"text": 3}]}
    (tmp_path / "x.lchords").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ProjectError):
        type(project()).load(tmp_path / "x.lchords")
    d["lyrics"] = {"source": {"kind": "user"}, "lines": [{"text": "ok", "start": None}]}
    (tmp_path / "x.lchords").write_text(json.dumps(d), encoding="utf-8")
    q = type(project()).load(tmp_path / "x.lchords")
    assert q.lyrics["offset"] == 0.0 and q.lyrics["anchors"] == {}


def test_find_local_prefers_a_side_file_then_the_tags(tmp_path):
    song = tmp_path / "Ma chanson.mp3"
    song.write_bytes(b"")
    assert L.find_local(song, "") is None
    lines, source = L.find_local(song, "Dans les tags\n")
    assert source["kind"] == "embedded" and lines[0]["text"] == "Dans les tags"
    (tmp_path / "Ma chanson.txt").write_bytes("Écrit à côté\n".encode("cp1252"))
    lines, source = L.find_local(song, "Dans les tags\n")
    assert (source["kind"], source["name"], lines[0]["text"]) == (
        "file",
        "Ma chanson.txt",
        "Écrit à côté",
    )
    (tmp_path / "Ma chanson.lrc").write_text("[00:01.00]Synchronisé\n", encoding="utf-8")
    lines, source = L.find_local(song)
    assert source["name"] == "Ma chanson.lrc" and lines[0]["start"] == 1.0


def test_lyrics_tag_is_read_from_the_recording(tmp_path):
    import av
    import numpy as np

    from localchords import audio

    path = tmp_path / "tagged.flac"
    with av.open(str(path), "w") as c:
        c.metadata["title"] = "Essai"
        c.metadata["LYRICS"] = "Première ligne\nDeuxième ligne"
        s = c.add_stream("flac", rate=44100, layout="mono")
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, 4410), dtype=np.int16), format="s16", layout="mono"
        )
        frame.rate = 44100
        for packet in s.encode(frame):
            c.mux(packet)
        for packet in s.encode(None):
            c.mux(packet)
    info = audio.metadata(path)
    assert info["lyrics"] == "Première ligne\nDeuxième ligne"
