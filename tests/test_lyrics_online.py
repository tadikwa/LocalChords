# LRCLIB answers are faked here: the tests never reach the network.
import io
import json
import urllib.error

import pytest

from localchords import lyrics_online as O


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(routes, seen=None):
    def open_(request, timeout):
        url = request.full_url
        if seen is not None:
            seen.append((url, request.get_header("User-agent")))
        for prefix, answer in routes.items():
            if prefix in url:
                if isinstance(answer, Exception):
                    raise answer
                return Response(
                    answer if isinstance(answer, bytes) else json.dumps(answer).encode()
                )
        raise urllib.error.HTTPError(url, 404, "nf", None, None)

    return open_


REC = {
    "id": 7,
    "trackName": "Chanson inventée",
    "artistName": "Personne",
    "albumName": "",
    "duration": 181.0,
    "instrumental": False,
    "plainLyrics": "Une ligne\nUne autre",
    "syncedLyrics": "[00:01.00]Une ligne\n[00:03.00]Une autre",
}
COVER = {**REC, "id": 8, "duration": 240.0, "syncedLyrics": None}


def test_search_sends_only_the_names_and_ranks_by_duration():
    seen = []
    found = O.search(
        "Chanson inventée",
        "Personne",
        "",
        180.4,
        opener({"/get?": REC, "/search?": [COVER, REC]}, seen),
    )
    assert [r["id"] for r in found] == [7, 8]
    assert all("lrclib.net/api/" in u and ua.startswith("LocalChords/") for u, ua in seen)
    assert "duration=180" in seen[0][0]


def test_synced_lines_or_words_only_for_another_recording():
    assert O.lines_of(REC)[1] == {"text": "Une autre", "start": 3.0}
    assert all(x["start"] is None for x in O.lines_of(REC, synced=False))
    src = O.source_of(REC, synced=True)
    assert src["kind"] == "catalog" and src["synced"] and src["exportable"] is False


def test_nothing_found_is_an_empty_list():
    assert O.search("Rien", "Personne", "", 100, opener({})) == []


@pytest.mark.parametrize(
    "error, words",
    [
        (urllib.error.HTTPError("u", 429, "busy", {"Retry-After": "30"}, None), "30 s"),
        (urllib.error.HTTPError("u", 503, "down", None, None), "503"),
        (urllib.error.URLError("offline"), "connexion"),
        (TimeoutError(), "connexion"),
    ],
)
def test_errors_are_explained(error, words):
    with pytest.raises(O.OnlineError, match=words):
        O.search("Titre", "", "", 0, opener({"/search?": error}))


def test_a_non_json_answer_is_an_error_not_a_crash():
    with pytest.raises(O.OnlineError, match="illisible"):
        O.search("Titre", "", "", 0, opener({"/search?": b"<html>oops</html>"}))


def test_a_title_is_required():
    with pytest.raises(O.OnlineError):
        O.search("  ", "", "", 0, opener({}))


# Choosing a suggestion among the candidates ------------------------------------------------------


def rec(i, title="Chanson inventée", artist="Personne", duration=181.0, synced=True, text="A"):
    return {
        "id": i,
        "trackName": title,
        "artistName": artist,
        "albumName": "",
        "duration": duration,
        "instrumental": False,
        "plainLyrics": f"{text} une ligne\n{text} une autre",
        "syncedLyrics": f"[00:01.00]{text} une ligne\n[00:03.00]{text} une autre"
        if synced
        else None,
    }


WHO = {"title": "Chanson inventée", "artist": "Personne", "album": "", "how": "tags", "sure": True}


def test_a_convincing_match_is_offered_synced():
    s = O.suggest([rec(1, duration=240.0, text="B"), rec(2)], WHO, 181.5)
    assert s["verdict"] == "sure" and s["candidates"][0]["id"] == 2 and s["synced"]


def test_the_same_lyrics_twice_is_no_ambiguity_but_two_versions_are():
    twins = O.suggest([rec(1), rec(2, duration=182.0)], WHO, 181.0)
    assert twins["verdict"] == "sure"
    rivals = O.suggest([rec(1, synced=False), rec(2, text="Autres paroles")], WHO, 0.0)
    assert rivals["verdict"] == "choose" and len(rivals["candidates"]) == 2


def test_a_duration_alone_proves_nothing():
    s = O.suggest([rec(1, title="Rien à voir", artist="Quelqu'un d'autre")], WHO, 181.0)
    assert s["verdict"] == "none" and s["candidates"] == []


def test_nothing_found_or_only_instrumentals_suggest_nothing():
    assert O.suggest([], WHO, 181.0)["verdict"] == "none"
    assert O.suggest([{**rec(1), "instrumental": True}], WHO, 181.0)["verdict"] == "none"


def test_a_live_keeps_the_words_not_the_studio_times():
    live = {**WHO, "title": "Chanson inventée (Live)"}
    s = O.suggest([rec(1)], live, 181.0)
    assert s["candidates"] and not s["synced"] and s["verdict"] == "choose"
    studio_for_a_cover = O.suggest([rec(1, title="Chanson inventée (Live)")], WHO, 181.0)
    assert studio_for_a_cover["verdict"] != "sure" and not studio_for_a_cover["synced"]


def test_a_far_duration_is_another_recording():
    s = O.suggest([rec(1, duration=260.0)], WHO, 181.0)
    assert s["verdict"] == "choose" and not s["synced"]


def test_a_guessed_title_read_backwards_is_still_found():
    backwards = {"title": "Personne", "artist": "Chanson inventée", "album": "", "how": "title"}
    assert O.suggest([rec(1)], backwards, 181.0)["verdict"] == "sure"
    sure = {**backwards, "sure": True}
    assert O.suggest([rec(1)], sure, 181.0)["verdict"] == "none"  # names that are sure stay so


def test_one_artist_is_not_another_with_a_longer_name():
    assert O._like("Personne", "Personne & Ami", True) >= 0.85
    assert O._like("Personne", "Personne Inconnue", True) < 0.85
    s = O.suggest([rec(1, artist="Personne Inconnue")], WHO, 181.0)
    assert s["verdict"] != "sure"
