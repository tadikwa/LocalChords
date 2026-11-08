"""Knowing the song from what the recording says of itself: yt-dlp's fields, tags, names."""

import sys
import types

from localchords import identify, worker


def info(**fields):
    base = {"id": "aBcD3fGh1jK", "duration": 201, "formats": [{"url": "x"}], "thumbnails": []}
    return {**base, **fields}


def test_the_sites_music_fields_come_first_and_are_sure():
    who = identify.from_info(
        info(
            title="Roch Voisine - Tant pis (Official Video)",
            track="Tant pis",
            artist="Roch Voisine",
            album="Un album",
            channel="Some Fan Channel",
        )
    )
    assert (who["title"], who["artist"], who["album"]) == ("Tant pis", "Roch Voisine", "Un album")
    assert who["how"] == "music" and who["sure"]


def test_a_title_split_at_its_dash_without_noise_or_id():
    who = identify.from_info(
        info(title="Roch Voisine - Tant pis (Official Video) [aBcD3fGh1jK]", channel="Roch Voisine")
    )
    assert (who["artist"], who["title"]) == ("Roch Voisine", "Tant pis")
    assert who["how"] == "title" and who["sure"]  # the artist's own channel posted it


def test_a_channel_is_not_the_artist():
    who = identify.from_info(info(title="Tant pis (clip officiel)", channel="Mes Vidéos 1987"))
    assert who["title"] == "Tant pis" and who["artist"] == "" and not who["sure"]
    other = identify.from_info(info(title="Roch Voisine - Tant pis", channel="Karaoke World"))
    assert other["artist"] == "Roch Voisine" and not other["sure"]  # a guess, said as one
    assert other["channel"] == "Karaoke World"


def test_youtubes_artist_channels_name_the_artist():
    who = identify.from_info(info(title="Tant pis", channel="Roch Voisine - Topic"))
    assert (who["artist"], who["title"], who["sure"]) == ("Roch Voisine", "Tant pis", True)


def test_a_track_without_artist_takes_the_title_s_own():
    who = identify.from_info(info(title="Roch Voisine - Tant pis", track="Tant pis", channel="X"))
    assert (who["artist"], who["title"], who["sure"]) == ("Roch Voisine", "Tant pis", False)


def test_ambiguous_titles_are_not_split():
    for title in ("A - B - C", "Juste un titre", " - ", "Live at the Hall 2019"):
        who = identify.from_info(info(title=title))
        assert who["artist"] == "" and not who["sure"], title


def test_well_tagged_mp3_is_sure_and_its_name_is_only_a_fallback():
    tags = {"title": "Ma chanson", "artist": "Quelqu'un", "album": "Disque"}
    who = identify.from_file(tags, "01 - piste inconnue")
    assert (who["title"], who["artist"], who["album"], who["how"], who["sure"]) == (
        "Ma chanson",
        "Quelqu'un",
        "Disque",
        "tags",
        True,
    )
    named = identify.from_file({"title": "", "artist": ""}, "Quelqu'un - Ma chanson [aBcD3fGh1jK]")
    assert (named["artist"], named["title"], named["how"], named["sure"]) == (
        "Quelqu'un",
        "Ma chanson",
        "filename",
        False,
    )


def test_a_generated_song_stays_unknown():
    who = identify.from_file({"title": "", "artist": ""}, "yue_output_03")
    assert who["title"] == "yue output 03" and who["artist"] == ""
    assert not identify.searchable(who)


def test_lives_and_covers_are_told_apart():
    assert identify.is_version("Tant pis (Live à l'Olympia)")
    assert identify.is_version("Tant pis - cover acoustique")
    assert identify.is_version(identify.clean_title("Tant pis [Unplugged]"))  # not taken for an id
    assert not identify.is_version("Tant pis")
    assert not identify.is_version("Liveline")  # a word, not a part of one


def test_only_plain_fields_cross_from_the_download_process():
    kept = identify.keep(info(title="t", artists=["A", "B"], webpage_url="https://e.org/w"))
    assert kept["artists"] == ["A", "B"] and "formats" not in kept and "thumbnails" not in kept
    assert identify.from_info(kept)["title"] == "t"


def test_the_download_message_carries_the_music_fields(tmp_path, monkeypatch):
    class YDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            return info(title="X - Y (Official Audio)", track="Y", artist="X", channel="C")

        def prepare_filename(self, i):
            return str(tmp_path / "X - Y (Official Audio) [aBcD3fGh1jK].m4a")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL))
    sent = []
    conn = types.SimpleNamespace(send=sent.append, close=lambda: None)
    worker._download_job("https://example.org/watch?v=1", str(tmp_path), conn)
    kind, path, url, fields = sent[-1]
    assert kind == "downloaded" and path.endswith(".m4a") and url == "https://example.org/watch?v=1"
    assert fields["track"] == "Y" and fields["artist"] == "X" and "formats" not in fields
