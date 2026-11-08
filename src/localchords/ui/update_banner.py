"""The new-version strip above the pages: asks once before looking online, then tells, fetches
and installs only when asked. The work runs in threads (updates.py); a timer reads their result.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, library, transcribe, updates
from . import theme
from .widgets import ElidedLabel

SAID = 6000  # ms a "nothing new" message stays

CHANGED = (
    "Le fichier téléchargé a changé depuis sa vérification : il a été supprimé, rien n'a été "
    "lancé. Téléchargez-le à nouveau."
)

NOT_SIGNED = (
    "LocalChords n'est pas signé numériquement : Windows SmartScreen peut afficher un "
    "avertissement. Le fichier a été vérifié (taille et SHA-256 identiques à ceux publiés sur "
    "GitHub), ce qui garantit qu'il est intact, pas qui l'a publié."
)


def _run(fn) -> transcribe.Task:
    def work(task):
        try:
            return fn(task)
        except updates.UpdateError as exc:
            raise transcribe.TranscribeError(str(exc)) from exc

    return transcribe.run(work)


class UpdateBanner(QWidget):
    """One line: a message, a progress bar while fetching, a few link buttons, and a close."""

    def __init__(self):
        super().__init__()
        self.setObjectName("bar")
        self.setAccessibleName("Mise à jour de LocalChords")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 8, 6)
        row.setSpacing(6)
        self.text = ElidedLabel()
        self.text.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(140, 6)
        self.bar.setAccessibleName("Progression du téléchargement")
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(2)
        self.close_button = QToolButton()
        self.close_button.setObjectName("step")
        self.close_button.setIcon(theme.icon("close", size=14))
        self.close_button.setToolTip("Masquer jusqu'au prochain démarrage")
        self.close_button.setAccessibleName("Masquer le message de mise à jour")
        row.addWidget(self.text, 1)
        row.addWidget(self.bar)
        row.addLayout(self.buttons)
        row.addWidget(self.close_button)
        self._shown: list = []
        self.actions: dict = {}
        self.hide()

    def show_state(
        self, text: str, actions: list, progress: float | None = None, show: bool = True
    ) -> None:
        """actions: (label, fn) pairs, in order of importance. The same actions again keep their
        buttons, so a click, the focus and a screen reader are not lost while progress moves."""
        if text != self.text._full:
            self.text.set_full_text(text)
            self.text.setAccessibleName(text)
        self.bar.setVisible(progress is not None)
        if progress is not None:
            self.bar.setValue(int(progress * 1000))
        if show:
            self.show()
        if actions == self._shown:
            return
        self._shown = list(actions)
        while self.buttons.count():
            widget = self.buttons.takeAt(0).widget()
            if widget is not None:
                widget.hide()  # at once: deleted only once back in the event loop
                widget.deleteLater()
        self.actions = {}
        for label, fn in actions:
            button = QPushButton(label)
            button.setObjectName("link")
            button.clicked.connect(fn)
            self.buttons.addWidget(button)
            self.actions[label] = button

    def hide_state(self) -> None:
        """Hidden with nothing left to click if it shows again before a new state."""
        self.show_state("", [], show=False)
        self.hide()


class SafeBrowser(QTextBrowser):
    """The release's notes as GitHub wrote them, but never their pictures or other remote
    files, nor any HTML: text, and links that open in the browser once clicked, https only."""

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open)
        palette = self.palette()
        for role, color in (
            (QPalette.ColorRole.Base, theme.SURFACE),
            (QPalette.ColorRole.Text, theme.TEXT),
            (QPalette.ColorRole.Link, theme.SELECT),
        ):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self.setStyleSheet(
            f"QTextBrowser {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
            " border-radius: 6px; padding: 6px 10px; }"
        )

    def loadResource(self, kind, url):  # noqa: N802 - Qt's name
        return None

    @staticmethod
    def _open(url: QUrl) -> None:
        if url.scheme() == "https":
            QDesktopServices.openUrl(url)


def _theme_links(doc: QTextDocument) -> None:
    """Qt's Markdown reader colours links from the application's light palette: retinted."""
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.charFormat().isAnchor():
                cursor = QTextCursor(doc)
                cursor.setPosition(frag.position())
                cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(theme.SELECT))
                cursor.mergeCharFormat(fmt)
            it += 1
        block = block.next()


def notes_dialog(parent, release: dict) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Nouveautés de {release['name']}")
    dialog.resize(620, 520)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 14)
    title = QLabel(release["name"])
    title.setTextFormat(Qt.TextFormat.PlainText)  # a name from the web: never read as HTML
    title.setObjectName("h1")
    layout.addWidget(title)
    when = f"Publiée le {release['published']} · " if release["published"] else ""
    sub = QLabel(f"{when}vous avez la version {__version__}")
    sub.setObjectName("muted")
    layout.addWidget(sub)
    browser = SafeBrowser()
    browser.document().setMarkdown(
        release["body"] or "_Pas de notes pour cette version._",
        QTextDocument.MarkdownFeature.MarkdownDialectGitHub
        | QTextDocument.MarkdownFeature.MarkdownNoHTML,
    )
    _theme_links(browser.document())
    layout.addWidget(browser, 1)
    link = QPushButton("Voir la version sur GitHub")
    link.setObjectName("link")
    link.clicked.connect(lambda: SafeBrowser._open(QUrl(release["url"])))
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    row = QHBoxLayout()
    row.addWidget(link)
    row.addStretch(1)
    row.addWidget(buttons)
    layout.addLayout(row)
    dialog.browser = browser
    return dialog


class UpdateController:
    """Settings kept: update_auto (None until the user answers), update_cache (the last answer
    and its ETag), update_skip (a version not to mention again), update_ready (a file fetched
    and verified, waiting to be installed)."""

    def __init__(self, window):
        self.w = window
        self.settings = window.settings
        self.kind = updates.distribution()
        self.banner = UpdateBanner()
        self.banner.close_button.clicked.connect(self.later)
        self.release: dict | None = None
        self.task: transcribe.Task | None = None
        self._job = ""
        self._dismissed = None  # the version put off until the next start
        self._quiet = False  # the strip closed during a download: back once it ends
        self._manual = False
        self.timer = QTimer(window)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.check_action = QAction("Rechercher des mises à jour…", window)
        self.check_action.triggered.connect(lambda: self.check(manual=True))
        self.auto_action = QAction(
            "Vérifier automatiquement les mises à jour au démarrage", window, checkable=True
        )
        self.auto_action.setToolTip(
            "Une requête anonyme à GitHub au plus une fois par jour : aucun identifiant, rien "
            "sur vos morceaux. Rien n'est téléchargé sans votre accord."
        )
        self.sync()
        self.auto_action.toggled.connect(self._auto_changed)

    def add_to(self, menu) -> None:
        """Into a "more" menu, just before its keyboard shortcuts and about entries."""
        before = next((a for a in menu.actions() if a.text() == "Raccourcis clavier"), None)
        menu.insertAction(before, self.check_action)
        menu.insertAction(before, self.auto_action)
        menu.insertSeparator(before)

    def sync(self) -> None:
        self.auto_action.blockSignals(True)
        self.auto_action.setChecked(self.settings.get("update_auto") is True)
        self.auto_action.blockSignals(False)

    def _auto_changed(self, on: bool) -> None:
        self.w._remember("update_auto", on)
        if self.banner.isVisible() and self._job == "" and self.release is None:
            self.banner.hide_state()  # the question asked at first start: answered here

    # At start ----------------------------------------------------------------------------------
    def start(self, delay_ms: int = 4000) -> None:
        if self.kind != "source":
            QTimer.singleShot(delay_ms, self._startup)

    def _startup(self) -> None:
        if self.task is not None or not self.w.isVisible():
            return
        ready = self.settings.get("update_ready")
        if isinstance(ready, dict):
            if updates.newer(str(ready.get("tag")), __version__) and updates.ready_ok(ready):
                self._show_ready(ready)
                return
            self.w._remember("update_ready", None)  # installed since, or the file is gone
        if self.kind == "installed":
            updates.clean_temp()
        else:
            updates.clean_parts(updates.destination(self.kind)[0])
        auto = self.settings.get("update_auto")
        if auto is None:
            self.banner.show_state(
                "Voulez-vous que LocalChords vérifie au démarrage si une nouvelle version est "
                "publiée ? Une requête anonyme à GitHub, au plus une fois par jour.",
                [("Oui, vérifier", self._consent), ("Non merci", self._decline)],
            )
        elif auto:
            self.check(manual=False)

    def _consent(self) -> None:
        self.w._remember("update_auto", True)
        self.sync()
        self.banner.show_state("Recherche d'une nouvelle version…", [])
        self.check(manual=False)

    def _decline(self) -> None:
        self.w._remember("update_auto", False)
        self.sync()
        self.banner.hide_state()

    def later(self) -> None:
        """Out of sight until the next start; nothing is lost."""
        if self.release is not None:
            self._dismissed = self.release["tag"]
        self._quiet = self._job == "fetch"
        self.banner.hide()

    # Looking -----------------------------------------------------------------------------------
    def check(self, manual: bool) -> None:
        if self.task is not None:
            if manual and self._job == "check":
                self._manual = True  # its answer is said, as asked
                self.banner.show_state("Recherche d'une nouvelle version…", [])
            elif manual:
                self._quiet = False
                self.banner.show()
            return
        if manual:
            self.banner.show_state("Recherche d'une nouvelle version…", [])
        cache = self.settings.get("update_cache")
        self._manual = manual
        self._job = "check"
        self.task = _run(lambda task: updates.check(cache, force=manual))
        self.timer.start()

    def _checked(self, task) -> None:
        if task.error:
            if self._manual:
                self._failed(task.error, self.check_again)
            elif self.release is None:
                self.banner.hide_state()  # not when starting: no network is no news
            return
        found, cache = task.result
        self.w._remember("update_cache", cache)
        if found and (
            self._manual or found["tag"] not in (self.settings.get("update_skip"), self._dismissed)
        ):
            self._offer(found)
        elif self._manual:
            self.release = None
            self.banner.show_state(f"LocalChords {__version__} est à jour.", [])
            QTimer.singleShot(SAID, self._hide_said)
        elif self.banner.isVisible() and self.release is None:
            self.banner.hide_state()

    def check_again(self) -> None:
        self.check(manual=True)

    def _hide_said(self) -> None:
        if self.task is None and self.release is None:
            self.banner.hide_state()

    def _offer(self, release: dict) -> None:
        self.release = release
        self.banner.show_state(
            f"LocalChords {release['version']} est disponible (vous avez la {__version__}).",
            [
                ("Nouveautés", self.show_notes),
                ("Télécharger", self.fetch),
                ("Plus tard", self.later),
                ("Ignorer cette version", self.skip),
            ],
        )

    def show_notes(self) -> None:
        if self.release is not None:
            notes_dialog(self.w, self.release).exec()

    def skip(self) -> None:
        if self.release is not None:
            self.w._remember("update_skip", self.release["tag"])
        self.release = None
        self.banner.hide_state()

    # Fetching ----------------------------------------------------------------------------------
    def fetch(self) -> None:
        release = self.release
        if release is None or self.task is not None:
            return
        if self.kind == "source":
            SafeBrowser._open(QUrl(release["url"]))
            return
        asset = updates.asset_for(release, self.kind)
        if asset is None:
            self._failed(
                f"La version {release['tag']} ne propose pas de fichier pour cette installation.",
                self.fetch,
            )
            return
        folder = self._folder(asset)
        if folder is None:
            return
        self._job = "fetch"
        self._quiet = False
        self.task = _run(lambda task: updates.download(release, self.kind, folder, task))
        self._downloading(0.0, "Vérification des sommes de contrôle…")
        self.timer.start()

    def _folder(self, asset: dict) -> Path | None:
        """Where the file goes; when that is not possible, another folder the user chooses."""
        folder, why = updates.destination(self.kind)
        need = asset["size"] // 2**20 + updates.SPACE_MARGIN_MB
        free = library.free_mb(folder) if why is None else 0
        if why is None and (not free or free >= need):
            return folder
        problem = why or f"il ne reste que {free} Mo libres ({need} Mo nécessaires)"
        text = f"Le fichier ne peut pas être enregistré dans {folder} : {problem}."
        if self.kind == "portable":
            text += (
                "\n\nVous pouvez choisir un autre dossier. Attention : la nouvelle version, "
                "lancée depuis ailleurs, n'utilisera pas le dossier Data d'ici, sauf si vous "
                "la replacez à côté de l'ancienne. LocalChords ne copie ni ne déplace Data."
            )
        box = QMessageBox(self.w)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Mise à jour")
        box.setText(text)
        choose = box.addButton("Choisir un dossier…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not choose:
            return None
        chosen = QFileDialog.getExistingDirectory(self.w, "Enregistrer la nouvelle version dans")
        return Path(chosen) if chosen else None

    def _downloading(self, progress: float, status: str) -> None:
        name = self.release["version"] if self.release else ""
        self.banner.show_state(
            f"Téléchargement de LocalChords {name} : {status}",
            [("Annuler", self.cancel)],
            progress,
            show=not self._quiet,
        )

    def cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def _fetched(self, task) -> None:
        self._quiet = False
        if task.error:
            if task.cancelled:
                self._offer(self.release)
            else:
                self._failed(task.error, self.fetch)
            return
        self.w._remember("update_ready", task.result)
        self._show_ready(task.result)

    # Ready -------------------------------------------------------------------------------------
    def _show_ready(self, ready: dict) -> None:
        self.ready = ready
        version = str(ready["tag"]).lstrip("v")
        path = Path(ready["path"])
        if ready["kind"] == "installed":
            text = f"LocalChords {version} est téléchargé et vérifié, prêt à être installé."
            actions = [("Installer maintenant", self.install), ("Plus tard", self.later)]
        elif ready["kind"] == "portable":
            text = f"La nouvelle version est prête : {path.name}, à côté de l'actuelle."
            if path.parent != Path(sys.executable).parent:
                text = f"La nouvelle version est prête : {path}."
            actions = [
                ("Lancer la nouvelle version", self.install),
                ("Ouvrir le dossier", self.reveal),
                ("Plus tard", self.later),
            ]
        else:
            text = f"Archive de LocalChords {version} vérifiée : {path.name}."
            actions = [
                ("Ouvrir le dossier", self.reveal),
                ("Comment la mettre en place ?", self.explain_zip),
                ("Plus tard", self.later),
            ]
        self.banner.show_state(text, actions)

    def reveal(self) -> None:
        try:
            subprocess.Popen(["explorer", "/select,", str(self.ready["path"])])  # noqa: S603, S607
        except OSError as exc:
            self._failed(f"L'Explorateur ne s'ouvre pas : {exc}", self.reveal)

    def explain_zip(self) -> None:
        QMessageBox.information(
            self.w,
            "Mettre en place la nouvelle version",
            "1. Fermez LocalChords.\n"
            "2. Décompressez l'archive dans un nouveau dossier.\n"
            "3. Si votre dossier actuel contient LocalChords.portable et un dossier Data, "
            "copiez-les dans le nouveau dossier.\n"
            "4. Lancez LocalChords.exe depuis le nouveau dossier, puis supprimez l'ancien "
            "quand tout va bien.\n\n"
            "Sans LocalChords.portable, vos projets restent dans %LOCALAPPDATA%\\LocalChords et "
            "sont retrouvés par la nouvelle version.\n\n" + NOT_SIGNED,
        )

    def install(self) -> None:
        """Only once confirmed: save, close, then open the file Windows' own way."""
        ready = self.ready
        version = str(ready["tag"]).lstrip("v")
        if ready["kind"] == "installed":
            title = "Installer la mise à jour"
            text = (
                f"Installer LocalChords {version} maintenant ?\n\n"
                "Votre travail est enregistré, LocalChords se ferme et l'installateur officiel "
                "s'ouvre. Vos projets, paroles corrigées et préférences sont conservés."
            )
            go = "Installer"
        else:
            title = "Lancer la nouvelle version"
            text = (
                f"Lancer LocalChords {version} ?\n\nVotre travail est enregistré, cette version "
                "se ferme et la nouvelle s'ouvre. L'ancien programme reste en place : vous "
                "pourrez le supprimer ensuite."
            )
            go = "Lancer"
        box = QMessageBox(self.w)
        box.setWindowTitle(title)
        box.setText(text)
        box.setInformativeText(NOT_SIGNED)
        yes = box.addButton(go, QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        path = Path(ready["path"])
        if not self._intact(path, ready):
            self._failed(CHANGED, self.check_again)
            return
        self.w._remember("update_ready", None if ready["kind"] != "installed" else ready)
        self.w.close()
        if self.w.isVisible():
            return
        if not self._intact(path, ready):  # once more, as late as possible: closing takes time
            QMessageBox.warning(None, "Mise à jour", CHANGED)
            return
        launch(path)

    def _intact(self, path: Path, ready: dict) -> bool:
        if updates.verified(path, ready["sha256"], ready.get("size")):
            return True
        self.w._remember("update_ready", None)
        path.unlink(missing_ok=True)
        return False

    # Plumbing ----------------------------------------------------------------------------------
    def _failed(self, error: str, retry) -> None:
        self.banner.show_state(error, [("Réessayer", retry), ("Ouvrir GitHub", self.open_github)])

    def open_github(self) -> None:
        url = self.release["url"] if self.release else updates.RELEASES + "/latest"
        SafeBrowser._open(QUrl(url))

    def _poll(self) -> None:
        task = self.task
        if task is None:
            self.timer.stop()
            return
        if not task.done:
            if self._job == "fetch":
                self._downloading(task.progress, task.status)
            return
        self.timer.stop()
        self.task = None
        if self._job == "check":
            self._checked(task)
        else:
            self._fetched(task)
        self._job = ""

    def stop(self) -> None:
        """On closing: a download in progress stops and leaves no part behind (a part a
        stalled connection keeps is removed at the next start)."""
        task = self.task
        if task is not None:
            task.cancel()
            until = time.monotonic() + 1.5
            while not task.done and time.monotonic() < until:
                time.sleep(0.02)
        self.timer.stop()


def launch(path: Path) -> None:
    """As a double click would: Windows checks the file (SmartScreen, its mark from the web)."""
    os.startfile(str(path))  # noqa: S606
