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
