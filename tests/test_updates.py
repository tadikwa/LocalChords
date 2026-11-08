"""Updates: GitHub's answers are made up here, nothing goes online. A file is kept only when
it is the one published, and nothing is installed or launched without a yes."""

import hashlib
import io
import json
import os
import time
import urllib.error

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import pytest
from PySide6.QtWidgets import QMessageBox
from test_ui import app, isolated, wait_for  # noqa: F401 - fixtures

from localchords import library, updates
from localchords.ui import update_banner as B
from localchords.ui.main_window import MainWindow

TAG = "v9.9.9"
DL = f"https://github.com/tadikwa/LocalChords/releases/download/{TAG}/"
PORTABLE = f"LocalChords-{TAG}-portable.exe"
SETUP = f"LocalChords-Setup-{TAG}.exe"
FILES = {PORTABLE: b"MZ portable " * 5000, SETUP: b"MZ setup " * 7000}
SUMS = "".join(
    f"{hashlib.sha256(data).hexdigest()}  {name}\r\n" for name, data in FILES.items()
).encode()
FILES["SHA256SUMS.txt"] = SUMS


def asset(name, data=None, **change):
    data = FILES[name] if data is None else data
    a = {
        "name": name,
        "size": len(data),
        "state": "uploaded",
        "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        "browser_download_url": DL + name,
    }
    return {**a, **change}


def answer(tag=TAG, **change):
    data = {
        "tag_name": tag,
        "name": f"LocalChords {tag}",
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/tadikwa/LocalChords/releases/tag/{tag}",
        "published_at": "2026-11-08T10:00:00Z",
        "body": "## Nouveautés\n\n- Des choses ![x](https://evil.example/x.png) <b>gras</b>",
        "assets": [asset(n) for n in FILES],
    }
    return {**data, **change}


class Response(io.BytesIO):
    def __init__(self, data, url, etag=None):
        super().__init__(data)
        self.url = url
        self.headers = {"ETag": etag} if etag else {}

    def geturl(self):
        return self.url


class GitHub:
    """An opener: the release JSON, then the files; records what was asked."""

    def __init__(self, release=None, files=None, etag='W/"1"', final=None):
        self.release = answer() if release is None else release
        self.files = dict(FILES if files is None else files)
        self.etag = etag
        self.final = final
        self.asked = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.asked.append((url, dict(request.header_items())))
        assert url.startswith("https://")
        if url == updates.API:
            if isinstance(self.release, Exception):
                raise self.release
            if self.etag and request.get_header("If-none-match") == self.etag:
                raise urllib.error.HTTPError(url, 304, "Not Modified", {}, None)
            body = self.release if isinstance(self.release, bytes) else json.dumps(self.release)
            return Response(body.encode() if isinstance(body, str) else body, url, self.etag)
        name = url.rsplit("/", 1)[1]
        return Response(self.files[name], self.final or "https://release-assets.example/" + name)


class Task:
    cancelled = False
    progress = 0.0
    status = ""


# Versions and the API's answer


def test_versions_compare_as_numbers():
    assert updates.parse_version("v1.5.1") == (1, 5, 1, 0)
    assert updates.newer("v1.5.1", "1.5") and updates.newer("v1.10", "1.9")
    assert not updates.newer("v1.5", "1.5.0") and not updates.newer("v1.4.9", "1.5")
    assert not updates.newer("v2.0-beta", "1.5") and not updates.newer("nightly", "1.5")


def test_only_a_published_stable_release_with_github_links_counts():
    assert updates.release_of(answer())["assets"][PORTABLE]["size"] == len(FILES[PORTABLE])
    assert updates.release_of(answer(draft=True)) is None
    assert updates.release_of(answer(prerelease=True)) is None
    assert updates.release_of(answer(html_url="https://evil.example/tag/v9.9.9")) is None
    assert updates.release_of("nonsense") is None
    moved = answer(assets=[asset(PORTABLE, browser_download_url="https://evil.example/x.exe")])
    assert updates.release_of(moved)["assets"] == {}
    sneaky = answer(assets=[{**asset(PORTABLE), "name": "..\\x.exe"}])
    assert updates.release_of(sneaky)["assets"] == {}


def test_check_asks_once_a_day_with_the_etag():
    github = GitHub()
    found, cache = updates.check({}, current="1.5", opener=github, now=1000.0)
    assert found["tag"] == TAG and cache["etag"] == 'W/"1"'
    headers = github.asked[0][1]
    assert "Authorization" not in headers and headers["User-agent"].startswith("LocalChords/")
    found, cache = updates.check(cache, current="1.5", opener=github, now=2000.0)
    assert found and len(github.asked) == 1  # within the day: not asked again
    found, cache = updates.check(cache, current="1.5", opener=github, now=2000.0 + updates.DAY)
    assert found and len(github.asked) == 2 and cache["checked"] == 2000.0 + updates.DAY  # 304
    found, cache = updates.check(
        cache, current="1.5", opener=github, now=2001.0 + updates.DAY, force=True
    )
    assert found and len(github.asked) == 3
    assert updates.check(cache, current="9.9.9", opener=github, now=2002.0 + updates.DAY)[0] is None


@pytest.mark.parametrize(
    ("trouble", "says"),
    [
        (urllib.error.HTTPError(updates.API, 403, "rate", {}, None), "limite"),
        (urllib.error.HTTPError(updates.API, 429, "rate", {}, None), "limite"),
        (urllib.error.HTTPError(updates.API, 500, "oops", {}, None), "500"),
        (urllib.error.URLError("offline"), "injoignable"),
        (TimeoutError(), "injoignable"),
        (b"<html>", "illisible"),
    ],
)
def test_check_failures_say_why(trouble, says):
    with pytest.raises(updates.UpdateError, match=says):
        updates.check({}, current="1.5", opener=GitHub(release=trouble), now=0.0)


def test_no_release_yet_and_a_prerelease_are_no_news():
    gone = urllib.error.HTTPError(updates.API, 404, "none", {}, None)
    assert updates.check({}, current="1.5", opener=GitHub(release=gone), now=0.0)[0] is None
    pre = GitHub(release=answer(prerelease=True))
    assert updates.check({}, current="1.5", opener=pre, now=0.0)[0] is None


# How LocalChords runs


def test_distribution(tmp_path):
    exe = tmp_path / "LocalChords.exe"
    assert updates.distribution(exe, frozen=False) == "source"
    assert updates.distribution(exe, frozen=True, location=tmp_path) == "installed"
    assert updates.distribution(exe, frozen=True, location=None) == "portable"
    (tmp_path / "_internal").mkdir()
    assert updates.distribution(exe, frozen=True, location=None) == "zip"
    # Installed elsewhere: this folder is not the installed copy.
    assert updates.distribution(exe, frozen=True, location=tmp_path / "other") == "zip"


def test_the_portable_goes_next_to_the_program(tmp_path):
    folder, why = updates.destination("portable", tmp_path / "LocalChords.exe")
    assert folder == tmp_path and why is None


# Downloading


def test_download_keeps_only_a_verified_file(tmp_path):
    tmp_path = tmp_path / "dl"
    release = updates.release_of(answer())
    ready = updates.download(release, "portable", tmp_path, Task(), GitHub())
    path = tmp_path / PORTABLE
    assert ready["path"] == str(path) and path.read_bytes() == FILES[PORTABLE]
    assert ready["sha256"] == hashlib.sha256(FILES[PORTABLE]).hexdigest()
    assert not (tmp_path / (PORTABLE + ".part")).exists()
    assert updates.verified(path, ready["sha256"], ready["size"])
    path.write_bytes(b"MZ other")
    assert not updates.verified(path, ready["sha256"], ready["size"])


@pytest.mark.parametrize(
    ("files", "says"),
    [
        ({PORTABLE: b"MZ portable " * 4999 + b"MZ portablX "}, "SHA-256"),
        ({PORTABLE: b"MZ portable " * 100}, "interrompu"),
        ({PORTABLE: b"MZ portable " * 5001}, "plus gros"),
    ],
)
def test_a_wrong_file_is_removed(tmp_path, files, says):
    tmp_path = tmp_path / "dl"
    release = updates.release_of(answer())
    with pytest.raises(updates.UpdateError, match=says):
        updates.download(release, "portable", tmp_path, Task(), GitHub(files={**FILES, **files}))
    assert list(tmp_path.iterdir()) == []


def test_a_cancelled_download_leaves_nothing(tmp_path):
    tmp_path = tmp_path / "dl"
    task = Task()
    task.cancelled = True
    with pytest.raises(updates.UpdateError, match="annulé"):
        updates.download(updates.release_of(answer()), "portable", tmp_path, task, GitHub())
    assert list(tmp_path.iterdir()) == []


def test_checksums_must_exist_and_agree(tmp_path):
    tmp_path = tmp_path / "dl"
    tmp_path.mkdir()
    no_sums = answer(assets=[asset(PORTABLE)])
    with pytest.raises(updates.UpdateError, match="SHA256SUMS"):
        updates.download(updates.release_of(no_sums), "portable", tmp_path, Task(), GitHub())
    other = hashlib.sha256(b"x").hexdigest()
    lying = answer(assets=[asset(PORTABLE, digest="sha256:" + other), asset("SHA256SUMS.txt")])
    with pytest.raises(updates.UpdateError, match="concordent"):
        updates.download(updates.release_of(lying), "portable", tmp_path, Task(), GitHub())
    swapped = {**FILES, "SHA256SUMS.txt": SUMS.replace(b"  ", b"   ", 1)}
    with pytest.raises(updates.UpdateError, match="SHA256SUMS"):
        updates.download(
            updates.release_of(answer()), "portable", tmp_path, Task(), GitHub(files=swapped)
        )
    with pytest.raises(updates.UpdateError, match="chiffr"):
        updates.download(
            updates.release_of(answer()),
            "portable",
            tmp_path,
            Task(),
            GitHub(final="http://plain.example/x"),
        )
    assert list(tmp_path.iterdir()) == []


def test_clean_temp_removes_only_old_installers_from_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    folder = tmp_path / updates.TEMP_FOLDER
    folder.mkdir()
    for name in (
        "LocalChords-Setup-v1.5.exe",
        "LocalChords-Setup-v1.6.exe.part",
        "LocalChords-Setup-v1.6.exe",
        "notes.txt",
    ):
        (folder / name).write_bytes(b"x")
    (tmp_path / "LocalChords-Setup-v1.4.exe").write_bytes(b"x")  # not ours: stays
    updates.clean_temp(current="1.5.1")
    assert sorted(p.name for p in folder.iterdir()) == ["LocalChords-Setup-v1.6.exe", "notes.txt"]
    assert (tmp_path / "LocalChords-Setup-v1.4.exe").exists()


# In the window


@pytest.fixture
def online(monkeypatch, tmp_path):
    github = GitHub()
    monkeypatch.setattr(updates.urllib.request, "urlopen", github)
    monkeypatch.setattr(updates, "distribution", lambda *a, **k: "portable")
    monkeypatch.setattr(updates, "destination", lambda kind, exe=None: (tmp_path / "prog", None))
    return github


def opened(app):
    window = MainWindow(muted=True)
    window.show()
    app.processEvents()
    return window


def wait_idle(app, c):
    assert wait_for(app, lambda: c.task is None, 10)


def test_nothing_goes_online_before_the_user_agrees(app, online):
    window = opened(app)
    c = window.updates
    c._startup()
    assert c.banner.isVisible() and "Oui, vérifier" in c.banner.actions
    assert online.asked == []
    c.banner.actions["Non merci"].click()
    assert library.load_settings()["update_auto"] is False and not c.banner.isVisible()
    c._startup()
    assert online.asked == [] and not c.banner.isVisible()
    window.close()


def test_consent_then_offer_skip_and_manual_check(app, online):
    window = opened(app)
    c = window.updates
    c._startup()
    c.banner.actions["Oui, vérifier"].click()
    wait_idle(app, c)
    assert library.load_settings()["update_auto"] is True and c.auto_action.isChecked()
    assert set(c.banner.actions) == {
        "Nouveautés",
        "Télécharger",
        "Plus tard",
        "Ignorer cette version",
    }
    assert "9.9.9" in c.banner.text._full
    dialog = B.notes_dialog(window, c.release)
    shown = dialog.browser.toPlainText()
    assert "Des choses" in shown and "<b>gras</b>" in shown  # HTML shown as text, never applied
    assert dialog.browser.loadResource(2, None) is None  # no picture fetched from elsewhere
    dialog.close()
    c.banner.actions["Ignorer cette version"].click()
    assert library.load_settings()["update_skip"] == TAG and not c.banner.isVisible()
    c.check(manual=False)
    wait_idle(app, c)
    assert not c.banner.isVisible()  # skipped: not mentioned again at start
    c.check(manual=True)
    wait_idle(app, c)
    assert c.banner.isVisible() and "Télécharger" in c.banner.actions  # but asked: told
    assert c.check_action in window.home.menu_button.menu().actions()
    assert c.auto_action in window.song.menu.menu().actions()
    window.close()


def test_up_to_date_and_offline_on_a_manual_check(app, online, monkeypatch):
    window = opened(app)
    c = window.updates
    online.release = answer(tag="v1.0")
    c.check(manual=True)
    wait_idle(app, c)
    assert "à jour" in c.banner.text._full
    online.release = urllib.error.URLError("offline")
    c.check(manual=True)
    wait_idle(app, c)
    assert "injoignable" in c.banner.text._full and "Ouvrir GitHub" in c.banner.actions
    window.close()


def choose(monkeypatch, role):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(b for b in self.buttons() if self.buttonRole(b) == role),
    )


def test_download_then_launch_only_once_confirmed(app, online, monkeypatch, tmp_path):
    marker = library.data_dir() / "projects"
    marker.mkdir(parents=True)
    (marker / "mine.lchords").write_text("{}", encoding="utf-8")
    launched = []
    monkeypatch.setattr(B, "launch", lambda path: launched.append(path))
    window = opened(app)
    c = window.updates
    c.check(manual=True)
    wait_idle(app, c)
    c.banner.actions["Télécharger"].click()
    assert c.banner.bar.isVisible() and "Annuler" in c.banner.actions
    wait_idle(app, c)
    target = tmp_path / "prog" / PORTABLE
    assert target.read_bytes() == FILES[PORTABLE]
    assert library.load_settings()["update_ready"]["path"] == str(target)
    assert "Lancer la nouvelle version" in c.banner.actions
    choose(monkeypatch, QMessageBox.ButtonRole.RejectRole)
    c.banner.actions["Lancer la nouvelle version"].click()
    assert launched == [] and window.isVisible()  # no yes, nothing launched
    target.write_bytes(b"MZ changed")
    choose(monkeypatch, QMessageBox.ButtonRole.AcceptRole)
    c.banner.actions["Lancer la nouvelle version"].click()
    assert launched == [] and not target.exists()  # changed since checked: never run
    assert "Réessayer" in c.banner.actions
    c.check(manual=True)
    wait_idle(app, c)
    c.banner.actions["Télécharger"].click()
    wait_idle(app, c)
    c.banner.actions["Lancer la nouvelle version"].click()
    assert launched == [target] and not window.isVisible()  # saved, closed, then launched
    assert (marker / "mine.lchords").read_text(encoding="utf-8") == "{}"  # the data untouched


def test_a_cancelled_download_offers_again(app, online, monkeypatch, tmp_path):
    window = opened(app)
    c = window.updates
    c.check(manual=True)
    wait_idle(app, c)
    real = updates.download

    def slow(release, kind, folder, task, opener=None):
        for _ in range(500):  # in the worker thread: no Qt here
            if task.cancelled:
                break
            time.sleep(0.01)
        return real(release, kind, folder, task, opener)

    monkeypatch.setattr(updates, "download", slow)
    c.banner.actions["Télécharger"].click()
    c.banner.actions["Annuler"].click()
    wait_idle(app, c)
    assert "Télécharger" in c.banner.actions
    assert not list((tmp_path / "prog").glob("*"))
    window.close()


def test_the_installer_waits_for_its_yes_and_the_ready_state_survives_a_restart(
    app, online, monkeypatch, tmp_path
):
    monkeypatch.setattr(updates, "distribution", lambda *a, **k: "installed")
    launched = []
    monkeypatch.setattr(B, "launch", lambda path: launched.append(path))
    window = opened(app)
    c = window.updates
    c.check(manual=True)
    wait_idle(app, c)
    c.banner.actions["Télécharger"].click()
    wait_idle(app, c)
    assert "Installer maintenant" in c.banner.actions
    window.close()
    again = opened(app)  # closed before installing: offered again at the next start
    again.updates._startup()
    assert "Installer maintenant" in again.updates.banner.actions
    choose(monkeypatch, QMessageBox.ButtonRole.AcceptRole)
    again.updates.banner.actions["Installer maintenant"].click()
    assert launched == [tmp_path / "prog" / SETUP] and not again.isVisible()
