import json
import wave

import numpy as np
import pytest

from localchords import audio, export, rhythm
from localchords.chords import key_name, make, parse, spell_root, symbol
from localchords.project import Project, ProjectError, decode_waveform, encode_waveform


def analysis(chords=("C:maj", "A:min", "F:maj", "G:7"), beats_each=4, bpm=120.0):
    period = 60.0 / bpm
    n = len(chords) * beats_each
    beats = [round(i * period, 3) for i in range(n)]
    segments = []
    for i, chord in enumerate(chords):
        start_beat = i * beats_each
        end_beat = start_beat + beats_each
        segments.append(
            {
                "start_beat": start_beat,
                "end_beat": end_beat,
                "start_time": beats[start_beat],
                "end_time": beats[end_beat] if end_beat < n else round(n * period, 3),
                "chord": chord,
                "bass": None,
                "candidates": [chord, "D:min"],
            }
        )
    return {
        "engine": {"name": "test", "version": "0"},
        "beats": beats,
        "segments": segments,
        "meter": {"beats_per_bar": 4, "first_downbeat": 0, "confidence": 0.5},
    }


def project(**kw):
    a = analysis(**kw)
    return Project(
        {"path": "x.mp3", "title": "Été à Noël", "duration": a["segments"][-1]["end_time"]}, a
    )


@pytest.mark.parametrize(
    "label,bass,kw,text",
    [
        ("C:maj", None, {}, "C"),
        ("A:min", None, {}, "Am"),
        ("F#:hdim7", None, {"key": "E:min"}, "F♯m7♭5"),
        ("A:sus4(b7)", None, {"key": "D:maj"}, "A7sus4"),
        ("C:maj", "E", {"key": "C:maj"}, "C/E"),
        ("A#:maj", None, {"key": "C:maj"}, "B♭"),  # bVII in C is B♭, not A♯
        ("E:7", "G#", {"key": "A:min"}, "E7/G♯"),
        ("C:maj", None, {"key": "C:maj", "semitones": 2}, "D"),
        ("G:7", None, {"key": "C:maj", "semitones": 1}, "A♭7"),
        ("G:7", None, {"key": "C:maj", "simplify": True}, "G"),
        ("A#:maj", None, {"accidentals": "sharps"}, "A♯"),
        ("C#:min", None, {"accidentals": "flats"}, "D♭m"),
        ("A#:maj", None, {"key": "C:maj", "ascii_only": True}, "Bb"),
        ("C:maj", None, {"latin": True}, "Do"),
        ("N", None, {}, "N.C."),
    ],
)
def test_symbol(label, bass, kw, text):
    assert symbol(label, bass, **kw) == text


def test_key_spelling_covers_all_keys_without_double_accidentals():
    for tonic in range(12):
        for mode in ("maj", "min"):
            for pc in range(12):
                name = spell_root(pc, (tonic, mode))
                assert len(name) <= 2


def test_key_name():
    assert key_name("A:min") == "A mineur"
    assert key_name("C:maj", 1) == "D♭ majeur"
    assert key_name("A:min", latin=True) == "La mineur"
    assert key_name(None) == "—"


def test_parse_rejects_unknown():
    assert parse("N") is None
    assert parse("Bb:min7") == (10, "min7")
    assert make(10, "min7") == "A#:min7"
    with pytest.raises(ValueError):
        parse("C:wat")


def test_edit_keeps_raw_analysis_and_undoes():
    p = project()
    raw = json.dumps(p.analysis)
    p.set_chord(p.grid()[4], p.grid()[8], "D:min7")
    assert p.analysis == json.loads(raw)
    assert [s.chord for s in p.segments()][:3] == ["C:maj", "D:min7", "F:maj"]
    assert p.segments()[1].edited
    p.undo()
    assert [s.chord for s in p.segments()][:2] == ["C:maj", "A:min"]
    p.redo()
    assert p.segments()[1].chord == "D:min7"


def test_edit_of_part_of_a_segment_splits_it():
    p = project()
    g = p.grid()
    p.set_chord(g[1], g[2], "E:min")
    assert [(s.chord, s.start_beat, s.end_beat) for s in p.segments()][:3] == [
        ("C:maj", 0, 1), ("E:min", 1, 2), ("C:maj", 2, 4),
    ]  # fmt: skip


def test_later_edit_lies_over_earlier():
    p = project()
    g = p.grid()
    p.set_chord(g[0], g[4], "D:min")
    p.set_chord(g[1], g[2], "E:min")
    assert [s.chord for s in p.segments()][:3] == ["D:min", "E:min", "D:min"]


def test_save_and_reload_unicode_keeps_everything(tmp_path):
    p = project()
    p.set_chord(p.grid()[4], p.grid()[8], "D:min7", "F")
    p.set_view(transpose=3, capo=2)
    p.set_meter(3, 1)
    path = tmp_path / "été à Noël — 日本語" / "chanson.lchords"
    p.save(path)
    q = Project.load(path)
    assert q.edits == p.edits and q.analysis == p.analysis and q.view == p.view
    assert [s.chord for s in q.segments()] == [s.chord for s in p.segments()]
    assert q.meter()["beats_per_bar"] == 3 and q.bars()[0].number == 0


@pytest.mark.parametrize(
    "content", ["", "not json", "[]", '{"format": "other"}', '{"format": "localchords"}']
)
def test_bad_project_file_is_refused(tmp_path, content):
    path = tmp_path / "x.lchords"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ProjectError):
        Project.load(path)


def test_newer_project_version_is_refused(tmp_path):
    p = project()
    d = p.to_dict() | {"version": 99}
    path = tmp_path / "x.lchords"
    path.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ProjectError, match="récente"):
        Project.load(path)


def test_bars_with_pickup_and_end_padding():
    p = project()
    p.set_meter(3, 1)
    bars = p.bars()
    assert bars[0].number == 0 and bars[0].beats == [None, None, 0]
    assert bars[1].beats == [1, 2, 3]
    last = bars[-1].beats
    assert len(last) == 3 and sorted(b for b in last if b is not None)[-1] == 15


def test_grid_scale_shift_and_bpm_keep_chords_in_time():
    p = project()
    n = len(p.grid())
    p.set_grid(scale=2)
    assert len(p.grid()) == 2 * n - 1
    assert p.segments()[1].chord == "A:min" and p.segments()[1].start == pytest.approx(2.0)
    p.set_grid(scale=0.5)
    assert len(p.grid()) == n // 2
    p.set_grid(scale=1, offset=0.25)
    assert p.grid()[0] == pytest.approx(0.25)
    p.set_grid(offset=0, bpm=60)
    assert p.tempo()["bpm"] == 60
    p.set_grid(bpm=0)
    assert p.edits["grid"] is None and len(p.grid()) == n


def test_edits_survive_a_new_grid():
    p = project()
    g = p.grid()
    p.set_chord(g[4], g[8], "D:min7")
    p.set_grid(scale=2)
    assert any(s.chord == "D:min7" and s.start == pytest.approx(g[4]) for s in p.segments())


def test_min_beats_absorbs_short_runs_but_not_corrections():
    p = project(chords=("C:maj", "D:min"), beats_each=8)
    p.analysis["segments"][0]["end_time"] = p.grid()[1]
    p.analysis["segments"].insert(
        1,
        {
            **p.analysis["segments"][0],
            "start_time": p.grid()[1],
            "end_time": p.grid()[2],
            "chord": "E:min",
        },
    )
    p.analysis["segments"].insert(
        2,
        {
            **p.analysis["segments"][0],
            "start_time": p.grid()[2],
            "end_time": p.grid()[8],
            "chord": "C:maj",
        },
    )
    assert [s.chord for s in p.segments()] == ["C:maj", "E:min", "C:maj", "D:min"]
    p.set_view(min_beats=2)
    assert [s.chord for s in p.segments()] == ["C:maj", "D:min"]
    p.set_chord(p.grid()[1], p.grid()[2], "E:min")
    assert [s.chord for s in p.segments()] == ["C:maj", "E:min", "C:maj", "D:min"]


def test_transposition_capo_and_exports_agree():
    p = project()
    p.set_view(transpose=2, capo=2)
    assert p.sounding_shift() == 0
    p.set_view(capo=0)
    text = export.to_text(p)
    assert "D" in text and "Bm" in text and "Tonalité : D majeur" in text
    assert "| D" in text
    cho = export.to_chordpro(p)
    assert "{key: D}" in cho and "[D]" in cho and "[Bm]" in cho and "{time: 4/4}" in cho
    assert "{title: Été à Noël}" in cho


def test_export_repeats_chord_name_at_bar_start_only_when_it_opens_the_bar():
    p = project()
    bars = export.bar_symbols(p)
    assert bars[0] == ["C", "", "", ""]
    assert bars[3] == ["G7", "", "", ""]


def test_key_after_correction_is_recomputed():
    p = project(chords=("A:min", "D:min", "E:7", "A:min"))
    assert p.key()["label"] == "A:min"
    p.set_key("C:maj")
    assert p.key()["label"] == "C:maj" and p.key()["source"] == "given"


def test_tempo_and_grid_fit():
    grid = np.arange(0, 30, 0.5)
    assert rhythm.tempo(grid)["bpm"] == 120 and rhythm.tempo(grid)["steadiness"] > 0.95
    assert rhythm.grid_fit(grid, grid + 0.01) > 0.95
    assert rhythm.grid_fit(grid, grid + 0.2) < 0.1


def test_peak_times():
    a = np.zeros(100)
    a[[10, 60]] = [0.9, 0.8]
    assert list(rhythm.peak_times(a, 50)) == [0.2, 1.2]


@pytest.mark.parametrize("meter,phase", [(4, 0), (4, 2), (3, 0), (3, 1), (6, 3)])
def test_infer_meter_reads_strong_evidence(meter, phase):
    n = 96
    downbeat = np.full(n, 0.1)
    downbeat[phase::meter] = 0.9
    changes = np.zeros(n)
    changes[phase::meter] = 1
    found = rhythm.infer_meter(downbeat, changes)
    assert (found["beats_per_bar"], found["first_downbeat"]) == (meter, phase)


def test_infer_meter_without_evidence_says_so():
    found = rhythm.infer_meter(np.zeros(96), np.zeros(96))
    assert found["beats_per_bar"] == 4 and found["confidence"] < 0.5


def test_waveform_round_trip():
    v = np.array([0, 10, 255], dtype=np.uint8)
    assert (decode_waveform(encode_waveform(v)) == v).all()


def _wav(path, seconds=1.0, rate=44100):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        t = np.arange(int(seconds * rate)) / rate
        f.writeframes((np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16).tobytes())
    return path


def test_decode_resamples_unicode_path(tmp_path):
    folder = tmp_path / "Éric & Zoë 音楽 (1)"
    folder.mkdir()
    y = audio.decode(_wav(folder / "chanson d'été #1.wav"), 22050, channels=1)
    assert y.shape[1] == 1 and abs(len(y) - 22050) < 1200 and y.dtype == np.float32
    assert audio.metadata(folder / "chanson d'été #1.wav")["title"] == "chanson d'été #1"


@pytest.mark.parametrize("data", [b"", b"this is not audio" * 100, b"RIFF\x00\x00\x00\x00WAVEfmt "])
def test_corrupt_file_gives_a_clear_error(tmp_path, data):
    path = tmp_path / "abîmé.mp3"
    path.write_bytes(data)
    with pytest.raises(audio.AudioError, match="abîmé"):
        audio.decode(path, 44100)


def test_missing_file(tmp_path):
    with pytest.raises(audio.AudioError, match="introuvable"):
        audio.decode(tmp_path / "absent.wav", 44100)


def test_peaks_scale():
    y = np.zeros((1000, 2), dtype=np.float32)
    y[500] = 0.5
    p = audio.peaks(y, 10)
    assert len(p) == 10 and p.max() == 255 and p[0] == 0


def test_fingerprint_changes_with_content(tmp_path):
    a = tmp_path / "a"
    a.write_bytes(b"x" * 3_000_000)
    first = audio.fingerprint(a)
    a.write_bytes(b"x" * 2_999_999 + b"y")
    assert audio.fingerprint(a) != first


@pytest.mark.parametrize(
    "typed,expected",
    [
        ("Am7", ("A:min7", None)),
        ("F#m7b5/A", ("F#:hdim7", "A")),
        ("Bb", ("A#:maj", None)),
        ("Bbm", ("A#:min", None)),
        ("c", ("C:maj", None)),
        ("D/F#", ("D:maj", "F#")),
        ("G7sus4", ("G:sus4(b7)", None)),
        ("Rém7", ("D:min7", None)),
        ("Sol", ("G:maj", None)),
        ("Sib", ("A#:maj", None)),
        ("N.C.", ("N", None)),
        ("Cmaj7", ("C:maj7", None)),
        ("C°7", ("C:dim7", None)),
        ("Cadd9", ("C:maj(9)", None)),
        ("H", None),
        ("Cxyz", None),
        ("", None),
        ("C/", ("C:maj", None)),
        ("C/xyz", None),
    ],
)
def test_parse_symbol(typed, expected):
    from localchords.chords import parse_symbol

    assert parse_symbol(typed) == expected


def test_place_bar_lines_follows_a_regular_count():
    d = np.full(40, 0.1)
    d[2::4] = 0.9
    assert rhythm.place_bar_lines(d, np.zeros(40), 4) == list(range(2, 40, 4))


def test_place_bar_lines_ignores_a_stray_activation():
    d = np.full(40, 0.1)
    d[0::4] = 0.8
    d[13] = 0.95
    assert rhythm.place_bar_lines(d, np.zeros(40), 4) == list(range(0, 40, 4))


def test_place_bar_lines_recovers_after_a_missed_beat():
    # A beat is missing at 20: from there on the bar lines sit one beat earlier.
    lines = [*range(0, 20, 4), *range(19, 80, 4)]
    d = np.full(80, 0.05)
    d[lines] = 0.95
    found = rhythm.place_bar_lines(d, np.zeros(80), 4)
    assert found[:4] == [0, 4, 8, 12] and found[-4:] == lines[-4:]


def test_bars_from_irregular_bar_lines_keep_every_beat_once():
    p = project()
    p.analysis["meter"]["bar_lines"] = [1, 5, 8, 12]
    bars = p.bars()
    assert bars[0].number == 0 and bars[0].beats == [None, None, None, 0]
    assert bars[1].beats == [1, 2, 3, 4]
    assert bars[2].beats == [5, 6, 7, None]  # a bar cut short by the next bar line
    cells = [b for bar in bars for b in bar.beats if b is not None]
    assert cells == list(range(16))
    assert p.bar_position(6) == (2, 2)
    assert p.bar_position(0) == (0, 1)


def test_long_intro_is_counted_back_from_the_first_bar_line():
    p = project()
    p.analysis["meter"]["bar_lines"] = [6, 10, 14]
    bars = p.bars()
    assert bars[0].beats == [None, None, 0, 1]
    assert bars[1].beats == [2, 3, 4, 5] and bars[1].number == 0
    assert bars[2].beats == [6, 7, 8, 9] and bars[2].number == 1


def test_user_meter_overrides_the_bar_lines():
    p = project()
    p.analysis["meter"]["bar_lines"] = [1, 5, 8, 12]
    p.set_meter(3, 0)
    assert p.bars()[0].beats == [0, 1, 2] and p.bars()[1].number == 2


def test_find_repeats_names_the_main_progression():
    from localchords.project import find_repeats

    verse = ["C", "G", "Am", "F"]
    chorus = ["F", "G", "C"]
    song = verse * 4 + chorus * 3 + verse * 2
    found = find_repeats(song)
    first = song[found[0]["at"][0] : found[0]["at"][0] + found[0]["size"]]
    assert sorted(first) == sorted(verse)
    assert len(found[0]["at"]) >= 6


def test_find_repeats_on_nothing_repeated():
    from localchords.project import find_repeats

    assert find_repeats(["C", "D", "E", "F"]) == []
    assert find_repeats([]) == []


def test_project_progressions_and_agreement():
    p = project(chords=("C:maj", "A:min", "F:maj", "G:7") * 3)
    found = p.progressions()
    assert found[0]["count"] == 3 and len(found[0]["chords"]) == 4
    same = p.agreement_with(p.analysis)
    assert same["exact"] == 1.0 and same["triads"] == 1.0 and same["differences"] == []
    other = analysis(chords=("C:maj7", "A:min", "F:maj", "G:maj") * 3)
    other["segments"][1]["chord"] = "E:min"
    compared = p.agreement_with(other)
    assert compared["exact"] < 1.0
    assert compared["triads"] == pytest.approx((48 - 4) / 48)
    assert len(compared["differences"]) == 4


@pytest.mark.parametrize("key", ["Db:maj", "Eb:maj", "Ab:maj", "Bb:maj", "Eb:min", "Bb:min"])
def test_flat_key_chosen_by_hand_keeps_the_project_working(key, tmp_path):
    p = project()
    p.set_key(key)
    assert p.key()["source"] == "given"
    assert p.segments()
    p.save(tmp_path / "k.lchords")
    assert Project.load(tmp_path / "k.lchords").segments()


def test_fadd9_can_be_typed_and_latin_still_works():
    from localchords.chords import parse_symbol

    assert parse_symbol("Fadd9") == ("F:maj(9)", None)
    assert parse_symbol("Fa") == ("F:maj", None)
    assert parse_symbol("Fam") == ("F:min", None)
    assert parse_symbol("Do7") == ("C:7", None)
    assert parse_symbol("Dom7") == ("C:min7", None)
    assert parse_symbol("Dm7") == ("D:min7", None)
    assert parse_symbol("La/Do#") == ("A:maj", "C#")
    assert parse_symbol("Sib7") == ("A#:7", None)


@pytest.mark.parametrize("key", ["D#:maj", "G#:maj", "C#:min", "G#:min"])
def test_no_chart_root_is_spelled_cb_fb_es_or_bs(key):
    from localchords.chords import parse_key

    for pc in range(12):
        assert spell_root(pc, parse_key(key)) not in ("Cb", "Fb", "E#", "B#")


def test_a_seek_to_a_beat_lands_in_that_beat():
    p = project()
    sr = 44100
    for i, t in enumerate(p.grid()):
        assert p.beat_at(float(int(t * sr)) / sr) == i


def test_a_halved_grid_keeps_the_downbeat_where_it_was():
    p = project()
    p.analysis["meter"].update({"first_downbeat": 2, "bar_lines": list(range(2, 16, 4))})
    p.set_grid(scale=0.5)
    grid = p.grid()
    first_full = next(b for b in p.bars() if b.number == 1)
    assert grid[first_full.beats[0]] == p.analysis["beats"][2]


def test_portable_mode_keeps_data_next_to_the_program_only_when_asked(tmp_path, monkeypatch):
    from localchords import app, library

    exe = tmp_path / "Clé USB" / "LocalChords.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "pc"))
    # setenv first so monkeypatch restores the original value: _data_location() sets it itself.
    monkeypatch.setenv("LOCALCHORDS_DATA", "")
    monkeypatch.delenv("LOCALCHORDS_DATA")

    assert library.portable_dir() is None  # no marker: the classic folder
    assert app._data_location() is None
    assert library.data_dir() == tmp_path / "pc" / "LocalChords"

    (exe.parent / library.PORTABLE_MARKER).write_text("")
    assert app._data_location() is None
    assert library.data_dir() == exe.parent / "Data"
    assert library.save_settings({"volume": 0.5})
    assert library.load_settings()["volume"] == 0.5

    # Data cannot be created (a file is in the way, as a read-only medium would refuse it):
    # the PC's folder for this run, with the reason, and nothing touched in either place.
    monkeypatch.delenv("LOCALCHORDS_DATA")
    (exe.parent / "Data" / "settings.json").unlink()
    (exe.parent / "Data").rmdir()
    (exe.parent / "Data").write_text("in the way")
    assert app._data_location()
    assert library.data_dir() == tmp_path / "pc" / "LocalChords"
    assert (exe.parent / "Data").read_text() == "in the way"
