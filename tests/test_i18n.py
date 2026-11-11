"""The interface language (v1.7, docs/LOCALISATION.md): choosing it, the catalogues' completeness,
and the program really running in English and in French. A window in another language runs in its
own process: Qt's translators are global, and the other tests expect French."""

import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from localchords import backup, i18n, library
from localchords.catalog import open_catalog
from localchords.ui import update_banner

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "src" / "localchords" / "translations"
TOOLS = Path(sys.executable).parent


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path / "data"))
    return library.data_dir()


# ---- choosing the language ----


@pytest.mark.parametrize(
    "ui,expected",
    [
        (["fr-FR"], "fr"),
        (["fr-CA", "en-US"], "fr"),
        (["en-GB"], "en"),
        (["de-DE"], "en"),  # a language LocalChords does not have: English
        (["de-DE", "fr-FR"], "fr"),  # the first one of the user's list that it has
        (["pt_BR"], "en"),
        ([], "en"),
    ],
)
def test_the_system_language_picks_the_first_known_one(ui, expected):
    assert i18n.system_language(ui) == expected


def test_someone_who_used_localchords_before_keeps_french(data):
    (data / "projects").mkdir(parents=True)
    (data / "projects" / "song.lchords").write_text("{}", encoding="utf-8")
    assert library.existing_user()
    settings = library.load_settings()
    assert i18n.migrate(settings, library.existing_user())
    assert settings["language"] == "fr"
    # Once set, never touched again.
    assert not i18n.migrate(settings, False)
    assert settings["language"] == "fr"


def test_a_new_user_follows_windows(data, monkeypatch):
    assert not library.existing_user()
    settings = library.load_settings()
    assert i18n.migrate(settings, library.existing_user())
    assert settings["language"] == "auto"
    monkeypatch.delenv(i18n.ENV)
    assert i18n.resolve(settings["language"], ["en-US"]) == "en"
    assert i18n.resolve(settings["language"], ["fr-FR"]) == "fr"


def test_a_settings_file_alone_marks_an_existing_user(data):
    data.mkdir(parents=True, exist_ok=True)
    library.save_settings({"volume": 0.5})
    assert library.existing_user()


def test_the_choice_is_kept_and_wins_over_windows(data, monkeypatch):
    monkeypatch.delenv(i18n.ENV)
    data.mkdir(parents=True, exist_ok=True)
    settings = library.load_settings()
    settings["language"] = "en"
    library.save_settings(settings)
    again = library.load_settings()
    assert not i18n.migrate(again, True)
    assert i18n.resolve(again["language"], ["fr-FR"]) == "en"
    # Unknown or damaged values fall back to Windows' language, then English.
    assert i18n.resolve("xx", ["fr-FR"]) == "fr"
    assert i18n.resolve(None, ["it-IT"]) == "en"
    bad = {"language": "klingon"}
    assert i18n.migrate(bad, True) and bad["language"] == "fr"


def test_the_environment_overrides_for_analysis_processes(monkeypatch):
    monkeypatch.setenv(i18n.ENV, "en")
    assert i18n.resolve("fr") == "en"
    monkeypatch.setenv(i18n.ENV, "zz")
    assert i18n.resolve("fr") == "fr"


def test_restoring_a_backup_keeps_the_interface_language(data, tmp_path):
    data.mkdir(parents=True, exist_ok=True)
    library.save_settings({**library.load_settings(), "language": "en", "volume": 0.3})
    archive = tmp_path / "backup.zip"
    c, _ = open_catalog(data)
    backup.write(archive, c, with_audio=False)
    with zipfile.ZipFile(archive) as z:
        assert json.loads(z.read(backup.SETTINGS))["language"] == "en"
    library.save_settings({**library.load_settings(), "language": "fr", "volume": 0.9})
    backup.restore(archive, c, settings=True)
    c.close()
    restored = library.load_settings()
    assert restored["volume"] == 0.3  # the backup's preferences came back...
    assert restored["language"] == "fr"  # ...but not its language


def test_every_language_has_an_installer_language():
    assert set(update_banner.INSTALLER_LANGUAGES) == set(i18n.LANGUAGES)
    iss = (ROOT / "installer" / "LocalChords.iss").read_text(encoding="utf-8")
    for name in update_banner.INSTALLER_LANGUAGES.values():
        assert f'Name: "{name}"' in iss
    assert "AppId={{C21679FE-1659-4CB0-872C-E0A24C7766C0}" in iss  # the v1.6.1 one: never changes


def test_the_build_packs_the_catalogues():
    spec = (ROOT / "localchords.spec").read_text(encoding="utf-8")
    assert '"src/localchords/translations/*.qm"' in spec
    assert "qtbase_fr.qm" in spec
    for language in i18n.LANGUAGES:
        if language != i18n.SOURCE or (TRANSLATIONS / f"localchords_{language}.ts").exists():
            assert (TRANSLATIONS / f"localchords_{language}.qm").exists()


# ---- the catalogues ----


def messages(language: str) -> list[dict]:
    root = ET.parse(TRANSLATIONS / f"localchords_{language}.ts").getroot()
    out = []
    for context in root.iter("context"):
        for m in context.iter("message"):
            t = m.find("translation")
            forms = [f.text or "" for f in t.iter("numerusform")]
            out.append(
                {
                    "context": context.findtext("name"),
                    "source": m.findtext("source"),
                    "numerus": m.get("numerus") == "yes",
                    "type": t.get("type"),
                    "text": t.text or "",
                    "forms": forms,
                }
            )
    return out


PLACEHOLDER = re.compile(r"\{(\w*)(?:[:!][^}]*)?\}")


def fields(text: str) -> list[str]:
    return sorted(PLACEHOLDER.findall(text))


def test_every_english_message_is_translated_with_the_same_placeholders():
    found = messages("en")
    assert len(found) > 1000
    problems = []
    for m in found:
        texts = m["forms"] if m["numerus"] else [m["text"]]
        if m["type"] in ("unfinished", "vanished", "obsolete") or not all(t.strip() for t in texts):
            problems.append(("untranslated", m["context"], m["source"]))
            continue
        for t in texts:
            if fields(t) != fields(m["source"]):
                problems.append(("placeholders", m["context"], m["source"], t))
            if t.count("\n") != m["source"].count("\n") and m["source"].startswith("\n"):
                problems.append(("line breaks", m["context"], m["source"], t))
        if m["numerus"]:
            if len(texts) != 2 or "%n" not in m["source"]:
                problems.append(("plural", m["context"], m["source"]))
            # Each form may say the number or not (“1 song” / “%n songs”), never another number.
            if not any("%n" in t for t in texts):
                problems.append(("plural without %n", m["context"], m["source"]))
    assert not problems, problems


def test_french_plurals_have_both_forms():
    english = {(m["context"], m["source"]) for m in messages("en") if m["numerus"]}
    french = {(m["context"], m["source"]): m for m in messages("fr") if m["numerus"]}
    assert english == set(french)
    for m in french.values():
        assert len(m["forms"]) == 2 and all(f.strip() for f in m["forms"]), m
        assert "(s)" not in "".join(m["forms"]) and "(x)" not in "".join(m["forms"]), m


def test_ampersands_are_doubled_where_qt_reads_a_mnemonic():
    # A lone & on a button or in a menu underlines the next letter and disappears.
    titles = {"Paroles et accords (PDF)", "Exporter les paroles et accords"}  # window titles
    lone = re.compile(r"(?<!&)&(?!&)")
    for m in messages("en"):
        for t in m["forms"] or [m["text"]]:
            if lone.search(t) and m["source"] not in titles:
                pytest.fail(f"lone & in {m['context']}: {t!r}")


def test_user_data_words_are_not_in_the_catalogue():
    # Nothing a user typed or a song carries can reach a catalogue: only the program's own words.
    sources = {m["source"] for m in messages("en")}
    for chord in ("Am", "C/E", "F♯m7", "N.C."):
        assert chord not in sources


def lupdate():
    exe = TOOLS / ("pyside6-lupdate.exe" if os.name == "nt" else "pyside6-lupdate")
    if not exe.exists():
        pytest.skip("pyside6-lupdate is not installed here")
    return exe


def sources() -> list[str]:
    files = sorted((ROOT / "src" / "localchords").glob("*.py"))
    files += sorted((ROOT / "src" / "localchords" / "ui").glob("*.py"))
    return [str(f) for f in files if f.name != "selftest.py"]


def test_no_text_in_the_code_is_missing_from_the_catalogue(tmp_path):
    copy = tmp_path / "en.ts"
    shutil.copy(TRANSLATIONS / "localchords_en.ts", copy)
    run = subprocess.run(
        [
            str(lupdate()),
            *sources(),
            "-source-language",
            "fr",
            "-target-language",
            "en",
            "-no-obsolete",
            "-locations",
            "none",
            "-ts",
            str(copy),
        ],  # fmt: skip
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    root = ET.parse(copy).getroot()
    unfinished = [
        m.findtext("source")
        for m in root.iter("message")
        if m.find("translation").get("type") == "unfinished"
    ]
    assert not unfinished, f"translate these in localchords_en.ts: {unfinished}"


def test_the_compiled_catalogues_match_their_sources(tmp_path):
    exe = TOOLS / ("pyside6-lrelease.exe" if os.name == "nt" else "pyside6-lrelease")
    if not exe.exists():
        pytest.skip("pyside6-lrelease is not installed here")
    for ts in TRANSLATIONS.glob("*.ts"):
        qm = tmp_path / (ts.stem + ".qm")
        run = subprocess.run([str(exe), str(ts), "-qm", str(qm)], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert qm.read_bytes() == (TRANSLATIONS / qm.name).read_bytes(), (
            f"run lrelease on {ts.name}"
        )


# ---- the program in each language, each in its own process ----

PROBE = r"""
import json, os
from pathlib import Path
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLabel, QLineEdit, QMenu, QMessageBox,
                               QWidget)
from localchords import export, i18n
from localchords.i18n import translate
from localchords.ui.main_window import MainWindow, app_instance
from localchords.ui.pdf import write_pdf
from test_core import project

app = app_instance()
w = MainWindow(muted=True)
w.resize(1280, 800)
w.show()
app.processEvents()
for menu in w.findChildren(QMenu):
    menu.aboutToShow.emit()  # menus filled when they open
texts = set()
for x in w.findChildren(QWidget) + [w]:
    texts.update((x.toolTip(), x.accessibleName(), x.accessibleDescription(), x.windowTitle()))
    for a in QWidget.actions(x):
        texts.update((a.text(), a.toolTip()))
    if isinstance(x, (QAbstractButton, QLabel)):
        texts.add(x.text())
    if isinstance(x, QComboBox):
        texts.update(x.itemText(i) for i in range(x.count()))
    if isinstance(x, QLineEdit):
        texts.add(x.placeholderText())
    if isinstance(x, QMenu):
        texts.add(x.title())
for a in w.findChildren(QAction):
    texts.update((a.text(), a.toolTip()))
box = QMessageBox(QMessageBox.Icon.Question, "", "",
                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
p = project()
pdf = Path(os.environ["LOCALCHORDS_DATA"]) / "sheet.pdf"
write_pdf(p, pdf)
print("RESULT" + json.dumps({
    "language": i18n.current(),
    "texts": sorted(t for t in texts if t),
    "buttons": [box.button(b).text().replace("&", "") for b in
                (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Cancel)],
    "plural": [translate("Library", "%n morceau(x)", None, n) for n in (1, 2)],
    "number": i18n.number(1.5),
    "size": i18n.size(3 * 2**29),
    "text": export.to_text(p),
    "pdf": pdf.read_bytes()[:5].decode("latin-1"),
}, ensure_ascii=False))
"""


@pytest.fixture(scope="module")
def run_in(tmp_path_factory):
    results = {}

    def run(language):
        if language not in results:
            data = tmp_path_factory.mktemp(f"data-{language}")
            env = {
                **os.environ,
                "LOCALCHORDS_LANG": language,
                "LOCALCHORDS_DATA": str(data),
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests")]),
                "PYTHONIOENCODING": "utf-8",
            }
            done = subprocess.run(
                [sys.executable, "-c", PROBE], env=env, cwd=ROOT, capture_output=True,
                text=True, encoding="utf-8", timeout=300,
            )  # fmt: skip
            line = [x for x in done.stdout.splitlines() if x.startswith("RESULT")]
            assert line, done.stderr[-3000:]
            results[language] = json.loads(line[0][len("RESULT") :])
        return results[language]

    return run


FRENCH = re.compile(
    r"[éèêàùçôîœ«»]|\b(le|la|les|des|du|une|et|pour|avec|dans|sur|pas|ou|aux|vos|votre)\b", re.I
)
# French on purpose in the English interface: each language's own name, and the solfège syllables.
ALLOWED = {
    "Français",
    "Automatic (Français)",
    "Solfège Note Names (Do, Ré, Mi)",
    "Langue / Language",
}


def test_the_english_interface_has_no_french_left(run_in):
    english = run_in("en")
    assert english["language"] == "en"
    left = [t for t in english["texts"] if FRENCH.search(t) and t not in ALLOWED]
    assert not left, left
    assert {"My Library", "All Songs", "Mixer", "Lyrics", "Export"} <= set(english["texts"])


def test_the_french_interface_is_unchanged(run_in):
    french = run_in("fr")
    assert french["language"] == "fr"
    assert {"Ma bibliothèque", "Tous les morceaux", "Mixage", "Paroles", "Exporter"} <= set(
        french["texts"]
    )
    assert "My Library" not in french["texts"]


def test_qt_buttons_plurals_and_numbers_follow_the_language(run_in):
    english, french = run_in("en"), run_in("fr")
    assert english["buttons"] == ["Yes", "Cancel"]
    assert french["buttons"] == ["Oui", "Annuler"]
    assert english["plural"] == ["1 song", "2 songs"]
    assert french["plural"] == ["1 morceau", "2 morceaux"]
    assert (english["number"], french["number"]) == ("1.5", "1,5")
    assert (english["size"], french["size"]) == ("1.5 GB", "1,5 Go")


def test_exports_translate_labels_but_never_the_music(run_in):
    english, french = run_in("en"), run_in("fr")
    assert english["pdf"] == french["pdf"] == "%PDF-"
    assert "Title" in english["text"] and "Titre" not in english["text"]
    assert "Titre" in french["text"]
    # The song's own title and its chords are the same in both languages.
    assert "Été à Noël" in english["text"] and "Été à Noël" in french["text"]
    grid = [line for line in english["text"].splitlines() if "|" in line]
    assert grid and grid == [line for line in french["text"].splitlines() if "|" in line]
