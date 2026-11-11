"""The interface language (docs/LOCALISATION.md). The program is written in French; English comes
from Qt's own catalogue `translations/localchords_en.qm`, made from the `.ts` file by
pyside6-lrelease. Only labels are translated: songs, lyrics, chord names and the user's own names
never go through here, and no stored value or setting key depends on the language."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

SOURCE = "fr"
# A Windows in a language LocalChords does not have gets English: the wider-read of the two.
FALLBACK = "en"
LANGUAGES = ("fr", "en")
CHOICES = ("auto", *LANGUAGES)
# Each language names itself, so that anyone can find theirs whatever the interface says.
NAMES = {"fr": "Français", "en": "English"}
ENV = "LOCALCHORDS_LANG"  # set for this run's analysis processes; a test may set it too

_current = SOURCE


def translate(context: str, text: str, disambiguation: str | None = None, n: int = -1) -> str:
    """Qt's translate under the name pyside6-lupdate looks for. With n, `%n` becomes the number
    and the catalogue picks the right plural form."""
    return QCoreApplication.translate(context, text, disambiguation, n)


def number(value: float, decimals: int = 1) -> str:
    """A decimal number the interface's way: 1,5 in French, 1.5 in English."""
    return QLocale(_current).toString(float(value), "f", decimals)


def size(n: int) -> str:
    """A file size: whole megabytes below a gigabyte, one decimal above."""
    if n >= 2**30:
        return translate("Units", "{size} Go").format(size=number(n / 2**30))
    return translate("Units", "{size} Mo").format(size=max(1, round(n / 2**20)))


def progress(done: int, total: int) -> str:
    """Megabytes downloaded out of the total."""
    return translate("Units", "{done} / {total} Mo").format(
        done=f"{done / 2**20:.0f}", total=f"{total / 2**20:.0f}"
    )


def folder() -> Path:
    # Next to this module, in the sources as in the built program (localchords.spec).
    return Path(__file__).resolve().parent / "translations"


def system_language(ui_languages: list[str] | None = None) -> str:
    """Windows' display language: the first one of the user's list that LocalChords has, else
    English."""
    for tag in QLocale.system().uiLanguages() if ui_languages is None else ui_languages:
        code = tag.replace("_", "-").split("-")[0].lower()
        if code in LANGUAGES:
            return code
    return FALLBACK


def migrate(settings: dict, existing_user: bool) -> bool:
    """Gives the settings a language once: French for someone who used LocalChords before it had
    a choice (it was all French then), Windows' language for a new user. True if it changed."""
    if settings.get("language") in CHOICES:
        return False
    settings["language"] = SOURCE if existing_user else "auto"
    return True


def resolve(choice: str | None, ui_languages: list[str] | None = None) -> str:
    override = os.environ.get(ENV)
    if override in LANGUAGES:
        return override
    if choice in LANGUAGES:
        return choice
    return system_language(ui_languages)


def current() -> str:
    return _current


def install(app: QCoreApplication, language: str) -> str:
    """Load the catalogues of one language once per run: Qt's buttons and LocalChords' own. A
    missing catalogue leaves the French text, never an empty label. Returns the language used."""
    global _current
    if getattr(app, "_localchords_language", None) is not None:
        return app._localchords_language
    language = language if language in LANGUAGES else FALLBACK
    app._translators = []
    qt = QTranslator(app)
    # English is Qt's own source language: there is no qtbase_en.
    if language != "en" and qt.load(
        f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ):
        app.installTranslator(qt)
        app._translators.append(qt)
    ours = QTranslator(app)
    # The French catalogue holds only plural forms: every other text is already French.
    if ours.load(f"localchords_{language}", str(folder())):
        app.installTranslator(ours)
        app._translators.append(ours)
    app._localchords_language = _current = language
    os.environ[ENV] = language
    return language


def install_worker() -> None:
    """An analysis process speaks the interface's language: it inherits ENV from the program."""
    language = resolve(None)
    app = QCoreApplication.instance()
    if app is None:
        if language == SOURCE:
            return  # its messages are French already; and a test may run it in its own process
        app = QCoreApplication([sys.argv[0]])
    install(app, language)
