# Localisation

*La localisation de LocalChords (1.7) : architecture, mise à jour des catalogues, ajout d'une langue.
Ce document est en anglais pour les traducteurs qui ne lisent pas le français.*

LocalChords is written in French. Every other language comes from Qt's own translation system:
`.ts` catalogues (XML, edited by hand or in Qt Linguist) compiled into `.qm` files that a `QTranslator`
loads at startup. No other library, no online service.

## What is translated, and what never is

| Translated | Never translated |
|---|---|
| Labels, buttons, menus, tooltips, accessible names, dialogs, messages, errors | Titles, artists, albums, lyrics, tags, collection names, file names |
| Headings of exports (PDF chord sheet, Lyrics & Chords PDF, text and ChordPro headers) | Chord names (`F♯m7`, `D/F♯`), the Do/Ré/Mi notation (its own setting) |
| Qt's built-in buttons (OK, Cancel, Yes, No) through `qtbase_<lang>.qm` | Settings keys, stored values, project files, log messages, IDs |
| The installer (Inno Setup `[Languages]` and `[CustomMessages]`) | Stored genres and tags: a suggested one (`Classique`, `À apprendre`) is saved in French and shown translated; library search finds it under both names |

A rule follows from this: **no stored value depends on the language.** Code compares keys
(`"sheet"`, `"vocals"`, `"auto"`), never displayed text, and translates at display time.

## How it works

- `src/localchords/i18n.py`
  - `SOURCE = "fr"`, `FALLBACK = "en"`, `LANGUAGES = ("fr", "en")`, `NAMES` (each language in its own
    name), `CHOICES = ("auto", "fr", "en")`.
  - `translate(context, text, disambiguation=None, n=-1)`: `QCoreApplication.translate` under the name
    `pyside6-lupdate` looks for. Every module does `from ..i18n import translate`.
  - `number`, `size`, `progress`: decimals and sizes the interface's way (1,5 Go / 1.5 GB).
  - `system_language()`: the first of Windows' display languages that LocalChords has, else English.
  - `migrate(settings, existing_user)`: gives `settings["language"]` a value once. Someone who already
    had LocalChords data (settings, library or projects) gets `"fr"`, since everything was French before
    1.7; a new user gets `"auto"`.
  - `resolve(choice)`: `LOCALCHORDS_LANG` if the user set it, else the choice, else (`"auto"`) the
    system language.
  - `install(app, language)`: loads `qtbase_<lang>.qm` (from PySide6) and
    `translations/localchords_<lang>.qm`, then sets `LOCALCHORDS_LANG` so that analysis and separation
    processes started afterwards speak the same language (`install_worker()` in those processes).
    `resolve` ignores that value of its own, and `without_ours()` keeps it from the new program and
    installer the updater starts: they read the language from the settings.
- `ui/main_window.py: app_instance()` runs `migrate` then `install` before any window is built.
- The **☰ menu → Langue / Language** submenu (`ui/widgets.py: language_menu`, in the song page and the
  library) saves the choice. The new language takes effect at the next start: a bilingual message says
  so. The submenu's own title stays “Langue / Language” in every language, so that anyone can find it.
- A missing message, or a missing `.qm`, shows the French source: nothing crashes.
- Restoring a library backup never changes the language (`backup.py`).
- The updater passes `/LANG=english` or `/LANG=french` to the installer it runs, in the language chosen
  for the next start (`ui/update_banner.py: INSTALLER_LANGUAGES`).
- Suggested genres and tags go through `catalog.shown()`: only those of `GENRES` and `TAGS` are
  translated, never a name the user typed.

## Writing translatable code

```python
from ..i18n import translate

label.setText(translate("Mixer", "Séparer les instruments"))
# Placeholders: always named, never concatenated.
translate("Library", "Supprimer la collection « {name} » ?").format(name=name)
# Plurals: %n, and the number as the fourth argument.
translate("Library", "%n morceau(x)", None, count)
# A text defined at import time: mark it, translate it where it is shown.
MODES = {"sheet": QT_TRANSLATE_NOOP("LyricsView", "Paroles et accords")}
button.setText(translate("LyricsView", MODES[mode]))
```

- The **context** is the area of the interface (`Library`, `Mixer`, `LyricsView`, `Export`…): the same
  French word may need two English ones in two places.
- **Never build a sentence from pieces** (`"Supprimer " + what`): word order differs between languages.
  Translate the whole sentence with named `{placeholders}`.
- **Plurals**: write the French source with `(s)` / `(x)` and `%n`; each language's catalogue holds the
  real forms (`localchords_fr.ts` holds the French singular and plural for these messages only).
- **`&` in a button or a menu** marks a keyboard mnemonic: an English “Lyrics & Chords” on a button must
  be written `Lyrics && Chords` in the catalogue. In a window title or a PDF, a single `&`.
- Keep translations about as long as the French: the interface is checked at 800 px wide.

## Updating the catalogues

After changing or adding texts, from the repository root:

```powershell
$files = Get-ChildItem src\localchords\*.py, src\localchords\ui\*.py | Where-Object Name -ne selftest.py
.venv\Scripts\pyside6-lupdate $files -source-language fr -target-language en -no-obsolete -locations none -ts src\localchords\translations\localchords_en.ts
.venv\Scripts\pyside6-lupdate $files -source-language fr -target-language fr -pluralonly -no-obsolete -locations none -ts src\localchords\translations\localchords_fr.ts
```

Translate the new (`type="unfinished"`) messages in `localchords_en.ts`, with Qt Linguist
(`.venv\Scripts\pyside6-linguist`) or a text editor, then compile:

```powershell
.venv\Scripts\pyside6-lrelease src\localchords\translations\localchords_en.ts src\localchords\translations\localchords_fr.ts
```

Commit the `.ts` **and** the `.qm` files: the build (`localchords.spec`) packs the `.qm` files as they
are. `tests/test_i18n.py` fails if a message is untranslated, if a translation loses or invents a
`{placeholder}` or `%n`, if a plural lacks a form, or if a `.qm` is older than its `.ts`.

`selftest.py` is left out on purpose: its texts are for the developer only.

## Adding a third language

Say German (`de`):

1. `i18n.py`: add `"de"` to `LANGUAGES` and `"de": "Deutsch"` to `NAMES`. The ☰ menu lists it on its own.
2. Create the catalogue: run the first `lupdate` command above with `-target-language de` and
   `-ts src\localchords\translations\localchords_de.ts`. Translate it from the French source; in Qt
   Linguist, *File → Open Read-Only* on `localchords_en.ts` shows the English beside it as a reference.
3. Plurals: German has the same two forms as English. A language with more (Polish, Russian…) gets as
   many `<numerusform>` as Qt asks for; lupdate writes the right number of empty forms.
4. Compile with `lrelease` and commit `localchords_de.ts` and `localchords_de.qm`.
5. Qt's own buttons: `localchords.spec` keeps only `qtbase_fr.qm` from PySide6; add `qtbase_de.qm` to
   its filter.
6. The installer (`installer/LocalChords.iss`): add a `[Languages]` line
   (`Name: "german"; MessagesFile: "compiler:Languages\German.isl"`), a `german.` line for
   `WelcomeLabel2` and for each `[CustomMessages]` entry.
7. `ui/update_banner.py`: add `"de": "german"` to `INSTALLER_LANGUAGES`.
8. Run `tests/test_i18n.py`, then look at the interface for real:
   `$env:LOCALCHORDS_LANG = "de"; .venv\Scripts\python -m localchords` (with `LOCALCHORDS_DATA` set to a
   test folder), at 800 px wide and full screen, and export a PDF.
9. README: a `README.de.md` is welcome, linked from the top of `README.md` and `README.en.md`.

## Known limits

- Changing the language takes effect at the next start (Qt widgets would otherwise all need to
  re-translate themselves live).
- Most technical documents in `docs/` are in French only.
