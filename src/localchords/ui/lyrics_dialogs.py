"""The dialogs of the lyrics: searching the free catalog, managing the speech models, editing the
text, and choosing what the printed lyrics and chords sheet holds."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .. import library, lyrics_online, transcribe
from . import theme
from .widgets import fmt_time

LOOSE_GAP = 3.0  # seconds: another recording, whose times would not fit


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.TEXT_2};")
    return label


def _buttons(ok: str, dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok)
    box.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class SearchDialog(QDialog):
    """Candidates from LRCLIB, for the user to choose: none is taken for the right one."""

    def __init__(self, title: str, artist: str, album: str, duration: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chercher les paroles en ligne")
        self.resize(760, 620)
        self.duration = duration
        self.choice: tuple[dict, bool] | None = None
        self.task: transcribe.Task | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(
            _note(
                "Seuls le titre, l'artiste, l'album et la durée sont envoyés à "
                f"{lyrics_online.NAME}, jamais l'audio. Les paroles trouvées s'affichent et "
                "s'enregistrent dans le projet, mais ne s'exportent pas : leurs droits "
                "appartiennent à leurs auteurs."
            )
        )
        form = QFormLayout()
        self.title = QLineEdit(title)
        self.artist = QLineEdit(artist)
        self.album = QLineEdit(album)
        for label, field in (
            ("Titre", self.title),
            ("Artiste", self.artist),
            ("Album", self.album),
        ):
            field.returnPressed.connect(self.search)
            form.addRow(label, field)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.go = QPushButton("Chercher")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.search)
        self.status = QLabel()
        self.status.setStyleSheet(f"color: {theme.TEXT_2};")
        row.addWidget(self.go)
        row.addWidget(self.status, 1)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.currentRowChanged.connect(self._show)
        self.results.itemDoubleClicked.connect(lambda _i: self._accept())
        layout.addWidget(self.results, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)  # no copy
        layout.addWidget(self.preview, 2)
        self.plain = QCheckBox("Garder le texte seul, sans les horodatages du catalogue")
        self.plain.setToolTip(
            "Pour une reprise, un enregistrement live, une autre durée ou une version générée : "
            "les horodatages d'un autre enregistrement ne tombent pas juste."
        )
        layout.addWidget(self.plain)
        self.box = _buttons("Utiliser ces paroles", self)
        self.box.accepted.disconnect()
        self.box.accepted.connect(self._accept)
        self.ok = self.box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        layout.addWidget(self.box)
        self.records: list[dict] = []
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)

    def search(self) -> None:
        if self.task is not None:
            return
        title, artist, album = (f.text().strip() for f in (self.title, self.artist, self.album))
        duration = self.duration

        def work(_task):
            try:
                return lyrics_online.search(title, artist, album, duration)
            except lyrics_online.OnlineError as exc:
                raise transcribe.TranscribeError(str(exc)) from exc

        self.go.setEnabled(False)
        self.status.setText("Recherche…")
        self.task = transcribe.run(work)
        self.timer.start()

    def _poll(self) -> None:
        task = self.task
        if task is None or not task.done:
            return
        self.timer.stop()
        self.task = None
        self.go.setEnabled(True)
        if task.error:
            self.status.setText(task.error)
            return
        self.records = task.result or []
        self.results.clear()
        for r in self.records:
            self.results.addItem(QListWidgetItem(self._describe(r)))
        self.status.setText(
            f"{len(self.records)} résultat(s) : vérifiez qu'il s'agit bien du même enregistrement."
            if self.records
            else "Rien trouvé. Essayez sans l'album, ou une autre orthographe."
        )
        if self.records:
            self.results.setCurrentRow(0)

    def _gap(self, r: dict) -> float | None:
        if not self.duration or not r.get("duration"):
            return None
        return abs(float(r["duration"]) - self.duration)

    def _describe(self, r: dict) -> str:
        parts = [f"{r.get('artistName') or '?'} – {r.get('trackName') or '?'}"]
        if r.get("albumName"):
            parts.append(r["albumName"])
        if r.get("duration"):
            parts.append(fmt_time(float(r["duration"])))
        parts.append(
            "instrumental"
            if r.get("instrumental")
            else "synchronisées"
            if r.get("syncedLyrics")
            else "texte seul"
        )
        gap = self._gap(r)
        if gap is not None:
            parts.append("même durée" if gap < 1 else f"écart {gap:.0f} s")
        return " · ".join(parts)

    def _show(self, row: int) -> None:
        r = self.records[row] if 0 <= row < len(self.records) else None
        usable = bool(r and (r.get("plainLyrics") or r.get("syncedLyrics")))
        self.ok.setEnabled(usable)
        if r is None:
            self.preview.clear()
            return
        self.preview.setPlainText(
            r.get("syncedLyrics")
            or r.get("plainLyrics")
            or "(morceau instrumental : pas de paroles)"
        )
        gap = self._gap(r)
        loose = not r.get("syncedLyrics") or (gap is not None and gap > LOOSE_GAP)
        self.plain.setChecked(loose)
        self.plain.setEnabled(bool(r.get("syncedLyrics")))

    def _accept(self) -> None:
        row = self.results.currentRow()
        if 0 <= row < len(self.records) and self.ok.isEnabled():
            self.choice = (self.records[row], not self.plain.isChecked())
            self.accept()


class TranscribeDialog(QDialog):
    """The speech models (downloaded only here, checked, deletable) and the language."""

    def __init__(self, model: str, language: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transcrire les paroles avec l'IA, sur cet ordinateur")
        self.setMinimumWidth(640)
        self.task: transcribe.Task | None = None
        self.loading: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(
            _note(
                "La transcription se fait entièrement sur cet ordinateur avec whisper.cpp : "
                "l'audio n'est envoyé nulle part. Il faut une fois un modèle de reconnaissance "
                "de la parole, téléchargé depuis Hugging Face (huggingface.co) et vérifié. "
                "Le résultat est un brouillon : le chant est plus difficile que la parole, "
                "relisez-le."
            )
        )
        if not transcribe.engine_ready():
            warn = QLabel("Le moteur de transcription manque dans cette installation.")
            warn.setStyleSheet(f"color: {theme.ERROR};")
            layout.addWidget(warn)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.group = QButtonGroup(self)
        self.rows: dict[str, tuple] = {}
        for i, m in enumerate(transcribe.MODELS):
            radio = QRadioButton(m["label"])
            radio.setProperty("model", m["id"])
            self.group.addButton(radio)
            status = QLabel()
            status.setStyleSheet(f"color: {theme.TEXT_2};")
            button = QPushButton()
            button.clicked.connect(lambda _c=False, mid=m["id"]: self._model_action(mid))
            grid.addWidget(radio, 2 * i, 0)
            grid.addWidget(status, 2 * i, 1)
            grid.addWidget(button, 2 * i, 2)
            grid.addWidget(_note(m["note"]), 2 * i + 1, 0, 1, 3)
            self.rows[m["id"]] = (radio, status, button)
        layout.addLayout(grid)
        chosen = self.rows.get(model) or self.rows[transcribe.DEFAULT_MODEL]
        chosen[0].setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self._refresh())

        work = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress_text = QLabel()
        self.cancel_button = QPushButton("Annuler le téléchargement")
        self.cancel_button.clicked.connect(self._cancel)
        work.addWidget(self.progress, 1)
        work.addWidget(self.progress_text)
        work.addWidget(self.cancel_button)
        layout.addLayout(work)
        self.folder = _note("")
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.folder)

        form = QFormLayout()
        self.language_box = QComboBox()
        for value, text in transcribe.LANGUAGES.items():
            self.language_box.addItem(text, value)
        self.language_box.setCurrentIndex(max(0, self.language_box.findData(language)))
        form.addRow("Langue chantée", self.language_box)
        layout.addLayout(form)
        layout.addWidget(
            _note(
                "Selon l'ordinateur, compter de quelques dizaines de secondes à "
                "quelques minutes par morceau. La lecture reste possible pendant "
                "ce temps."
            )
        )
        self.box = _buttons("Transcrire", self)
        self.ok = self.box.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(self.box)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll)
        self._refresh()

    @property
    def model(self) -> str:
        return self.group.checkedButton().property("model")

    @property
    def language(self) -> str:
        return self.language_box.currentData()

    def _refresh(self) -> None:
        for mid, (_radio, status, button) in self.rows.items():
            have = transcribe.installed(mid)
            if mid == self.loading:
                status.setText("Téléchargement…")
            else:
                status.setText("Installé" if have else "Non téléchargé")
            button.setText("Supprimer" if have else "Télécharger")
            button.setEnabled(self.loading is None)
        busy = self.loading is not None
        for w in (self.progress, self.progress_text, self.cancel_button):
            w.setVisible(busy)
        folder = transcribe.models_dir()
        self.folder.setStyleSheet(f"color: {theme.TEXT_2};")
        free = library.free_mb(folder if folder.exists() else library.data_dir())
        self.folder.setText(
            f"Dossier des modèles : {folder}" + (f" · {free / 1024:.1f} Go libres" if free else "")
        )
        self.ok.setEnabled(
            not busy and transcribe.engine_ready() and transcribe.installed(self.model)
        )

    def _model_action(self, mid: str) -> None:
        if transcribe.installed(mid):
            info = transcribe.model_info(mid)
            sure = QMessageBox.question(
                self,
                "Supprimer le modèle",
                f"Supprimer le modèle « {info['label']} » ? Les paroles déjà transcrites restent ; "
                "il faudra le retélécharger pour transcrire à nouveau.",
            )
            if sure != QMessageBox.StandardButton.Yes:
                return
            transcribe.delete_model(mid)  # the transcriptions stay in their projects
            self._refresh()
            return
        self.loading = mid
        self.rows[mid][0].setChecked(True)
        self.task = transcribe.run(lambda t: transcribe.download(mid, t))
        self.timer.start()
        self._refresh()

    def _poll(self) -> None:
        task = self.task
        if task is None:
            return
        self.progress.setValue(int(task.progress * 1000))
        self.progress_text.setText(task.status)
        if not task.done:
            return
        self.timer.stop()
        self.task, self.loading = None, None
        self._refresh()
        if task.error and not task.cancelled:
            self.folder.setText(task.error)
            self.folder.setStyleSheet(f"color: {theme.ERROR};")

    def _cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def done(self, result: int) -> None:
        self._cancel()  # closing the dialog stops a download; a transcription has not begun
        super().done(result)


class _NoCopyEdit(QPlainTextEdit):
    """Editable, but nothing copied or dragged out: catalog lyrics stay in the program."""

    def createMimeDataFromSelection(self):  # noqa: N802 (Qt's name)
        return QMimeData()


class LyricsEditor(QDialog):
    """The whole text at once: a line per line, `[Refrain]` for a section, LRC times kept."""

    def __init__(self, text: str, parent=None, copyable: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Paroles")
        self.resize(680, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(
            _note(
                "Une ligne par ligne chantée ; une ligne vide sépare les couplets ; "
                "« [Refrain] » seul sur une ligne nomme une partie. Un temps « [01:23.45] » au "
                "début d'une ligne la fait commencer là. Une ligne modifiée perd le minutage "
                "de ses mots."
            )
        )
        self.edit = (QPlainTextEdit if copyable else _NoCopyEdit)(text)
        font = QFont(theme.app_font(15))
        self.edit.setFont(font)
        layout.addWidget(self.edit, 1)
        layout.addWidget(_buttons("Enregistrer", self))

    def text(self) -> str:
        return self.edit.toPlainText()


class LyricsPdfDialog(QDialog):
    """What the printed lyrics and chords sheet holds."""

    DIAGRAMS = (
        ("guitar", "Guitare"),
        ("piano", "Piano"),
        ("both", "Guitare et piano"),
        ("none", "Aucun"),
    )
    SIZES = (("small", "Petit"), ("medium", "Moyen"), ("large", "Grand"))
    DEFAULTS = {
        "diagrams": "guitar",
        "landscape": False,
        "size": "medium",
        "diagrams_first": True,
        "details": True,
    }

    def __init__(self, saved: dict, parent=None):
        super().__init__(parent)
        o = {**self.DEFAULTS, **{k: v for k, v in saved.items() if k in self.DEFAULTS}}
        self.setWindowTitle("Paroles et accords (PDF)")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        form = QFormLayout()
        self.diagrams = QComboBox()
        self.size = QComboBox()
        for box, items, value in (
            (self.diagrams, self.DIAGRAMS, o["diagrams"]),
            (self.size, self.SIZES, o["size"]),
        ):
            for v, text in items:
                box.addItem(text, v)
            box.setCurrentIndex(max(0, box.findData(value)))
        self.orientation = QComboBox()
        self.orientation.addItem("A4 portrait", False)
        self.orientation.addItem("A4 paysage", True)
        self.orientation.setCurrentIndex(1 if o["landscape"] else 0)
        self.place = QComboBox()
        self.place.addItem("En tête de la première page", True)
        self.place.addItem("En annexe, après les paroles", False)
        self.place.setCurrentIndex(0 if o["diagrams_first"] else 1)
        form.addRow("Diagrammes", self.diagrams)
        form.addRow("Diagrammes placés", self.place)
        form.addRow("Format", self.orientation)
        form.addRow("Taille du texte", self.size)
        layout.addLayout(form)
        self.details = QCheckBox("Tonalité, tempo, mesure et capodastre en tête")
        self.details.setChecked(bool(o["details"]))
        layout.addWidget(self.details)
        self.diagrams.currentIndexChanged.connect(
            lambda: self.place.setEnabled(self.diagrams.currentData() != "none")
        )
        self.place.setEnabled(o["diagrams"] != "none")
        layout.addWidget(
            _note(
                "Les accords sont ceux de la grille, transposition, capodastre et "
                "corrections compris ; les positions sont celles choisies dans "
                "le programme."
            )
        )
        layout.addWidget(_buttons("Exporter…", self))

    def options(self) -> dict:
        return {
            "diagrams": self.diagrams.currentData(),
            "landscape": bool(self.orientation.currentData()),
            "size": self.size.currentData(),
            "diagrams_first": bool(self.place.currentData()),
            "details": self.details.isChecked(),
        }
