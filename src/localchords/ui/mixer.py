"""The Mixage panel in the song screen: separate a song's instruments once, on request, then set
each stem's level while it plays. The separation runs in its own process (worker), the stems are
kept on disk (stems.py) and mixed by the player (player.Mix), so nothing here touches the audio
thread or runs the model again."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import library, stems, transcribe, worker
from ..i18n import translate
from ..player import Mix
from . import theme
from .widgets import segmented

HONEST = QT_TRANSLATE_NOOP(
    "Mixer",
    "Séparation par IA, sur cet ordinateur : jamais parfaite, un peu de chaque instrument reste "
    "audible dans les autres pistes.",
)
SHORT_MODE = {
    "karaoke": QT_TRANSLATE_NOOP("Mixer", "Karaoké · 2 pistes"),
    "musician": QT_TRANSLATE_NOOP("Mixer", "Musicien · 4 pistes"),
}
ROW_WIDTH = 400  # a stem's row needs about this much to keep its slider usable


def _other(mode: str) -> str:
    return "karaoke" if mode == "musician" else "musician"


def _confirm(parent, title: str, text: str, yes: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Question)
    ok = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    return box.clickedButton() is ok


class LevelSlider(QSlider):
    """A stem's fader; a double click brings it back to the level it was separated at."""

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setRange(0, stems.TOP)
        self.setPageStep(5)

    def mouseDoubleClickEvent(self, event):
        self.setValue(stems.UNITY)


class StemRow(QWidget):
    changed = Signal(str, str, object)  # stem, "level" | "mute" | "solo", value

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        label = translate("Stems", stems.NAMES[name])
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.label = QLabel(label)
        self.label.setFixedWidth(84)
        self.slider = LevelSlider()
        self.slider.setAccessibleName(translate("Mixer", "Volume : {label}").format(label=label))
        self.slider.setToolTip(
            translate(
                "Mixer", "Volume de la piste {label} (double-clic : niveau d'origine)"
            ).format(label=label)
        )
        self.db = QLabel()
        self.db.setObjectName("caption")
        self.db.setFixedWidth(48)
        self.db.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.reset = QToolButton()
        self.reset.setIcon(theme.icon("undo", size=14))
        self.reset.setToolTip(
            translate(
                "Mixer",
                "Remettre {label} à 0 dB (aussi : double-clic sur le curseur) ; les "
                "autres pistes, Muet et Solo ne changent pas",
            ).format(label=label)
        )
        self.reset.setAccessibleName(
            translate("Mixer", "Remettre {label} à 0 dB").format(label=label)
        )
        self.reset.clicked.connect(lambda: self.slider.setValue(stems.UNITY))
        self.mute = QPushButton("M")
        self.mute.setToolTip(translate("Mixer", "Couper : {label}").format(label=label))
        self.mute.setAccessibleName(translate("Mixer", "Couper {label}").format(label=label))
        self.solo = QPushButton("S")
        self.solo.setToolTip(
            translate(
                "Mixer", "Écouter seule : {label} (les réglages des autres sont gardés)"
            ).format(label=label)
        )
        self.solo.setAccessibleName(translate("Mixer", "Solo {label}").format(label=label))
        for b in (self.mute, self.solo):
            b.setCheckable(True)
            b.setFixedWidth(34)
        row.addWidget(self.label)
        row.addWidget(self.slider, 1)
        row.addWidget(self.db)
        row.addWidget(self.reset)
        row.addWidget(self.mute)
        row.addWidget(self.solo)
        self.slider.valueChanged.connect(lambda v: self.changed.emit(name, "level", v))
        self.mute.toggled.connect(lambda on: self.changed.emit(name, "mute", on))
        self.solo.toggled.connect(lambda on: self.changed.emit(name, "solo", on))

    def show_settings(self, settings: dict) -> None:
        level = settings["levels"][self.name]
        for widget in (self.slider, self.mute, self.solo):
            widget.blockSignals(True)
        self.slider.setValue(level)
        self.mute.setChecked(self.name in settings["mute"])
        self.solo.setChecked(self.name in settings["solo"])
        for widget in (self.slider, self.mute, self.solo):
            widget.blockSignals(False)
        self.db.setText(stems.db_text(level))
        self.reset.setEnabled(level != stems.UNITY)
        # What is not heard is drawn as such, whatever the reason (its own mute, another's solo).
        heard = stems.gains(settings)[stems.MODES[settings["mode"]]["stems"].index(self.name)] > 0
        self.label.setObjectName("" if heard and settings["on"] else "muted")
        theme.restyle(self.label)


class MixerPanel(QFrame):
    rowChanged = Signal(str, str, object)  # from any stem's row

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self.setProperty("edge", "top")
        # As tall as what it shows, never squeezed: the grid above gives way instead.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 12)
        outer.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(translate("Mixer", "Mixage"))
        title.setObjectName("h2")
        self.state = QLabel()
        self.state.setObjectName("caption")
        self.more = QToolButton()
        self.more.setIcon(theme.icon("more", size=16))
        self.more.setToolTip(translate("Mixer", "Exporter, autre mode, supprimer les pistes"))
        self.more.setAccessibleName(translate("Mixer", "Plus d'options du mixage"))
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more.setMenu(QMenu(self.more))
        self.close_button = QToolButton()
        self.close_button.setIcon(theme.icon("close", size=16))
        self.close_button.setToolTip(
            translate("Mixer", "Fermer le mixage (M) : le mix reste actif")
        )
        self.close_button.setAccessibleName(translate("Mixer", "Fermer le mixage"))
        head.addWidget(title)
        head.addWidget(self.state)
        head.addStretch(1)
        head.addWidget(self.more)
        head.addWidget(self.close_button)
        outer.addLayout(head)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages)

        # Before separating.
        self.intro = QWidget()
        col = QVBoxLayout(self.intro)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        ask = QLabel(translate("Mixer", "Séparer les instruments de ce morceau"))
        ask.setObjectName("sectionHead")
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for mode, text in SHORT_MODE.items():
            text = translate("Mixer", text)
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(translate("Stems", stems.MODES[mode]["label"]))
            self.mode_group.addButton(b)
            self.mode_buttons[mode] = b
        row = QHBoxLayout()
        row.addWidget(segmented(self.mode_buttons.values()))
        self.separate = QPushButton(translate("Mixer", "Séparer les instruments"))
        self.separate.setObjectName("primary")
        row.addWidget(self.separate)
        row.addStretch(1)
        self.facts = QLabel()
        self.facts.setObjectName("caption")
        self.facts.setWordWrap(True)
        self.warn = QLabel()
        self.warn.setObjectName("error")
        self.warn.setWordWrap(True)
        self.warn.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(ask)
        col.addLayout(row)
        col.addWidget(self.facts)
        col.addWidget(self.warn)
        self.pages.addWidget(self.intro)

        # Downloading the model, separating, or reading the stems.
        self.work = QWidget()
        col = QVBoxLayout(self.work)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        row = QHBoxLayout()
        self.step = QLabel()
        self.cancel = QPushButton(translate("Mixer", "Annuler"))
        row.addWidget(self.step, 1)
        row.addWidget(self.cancel)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.work_note = QLabel()
        self.work_note.setObjectName("caption")
        self.work_note.setWordWrap(True)
        col.addLayout(row)
        col.addWidget(self.progress)
        col.addWidget(self.work_note)
        col.addStretch(1)
        self.pages.addWidget(self.work)

        # The console.
        self.console = QWidget()
        col = QVBoxLayout(self.console)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        row = self.top = QHBoxLayout()
        self.ab_group = QButtonGroup(self)
        self.original = QPushButton(translate("Mixer", "Original"))
        self.original.setToolTip(
            translate("Mixer", "Écouter l'enregistrement tel quel (Maj + M pour basculer)")
        )
        self.mixed = QPushButton(translate("Mixer", "Mix personnalisé"))
        self.mixed.setToolTip(
            translate("Mixer", "Écouter les pistes à vos niveaux (Maj + M pour basculer)")
        )
        for b in (self.original, self.mixed):
            b.setCheckable(True)
            self.ab_group.addButton(b)
        self.ab_frame = segmented([self.original, self.mixed])
        row.addWidget(self.ab_frame, 0, Qt.AlignmentFlag.AlignLeft)
        row.addSpacing(8)
        self.preset_group = QButtonGroup(self)
        self.presets_frame = segmented([])
        row.addWidget(self.presets_frame, 0, Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        col.addLayout(row)
        self.rows_box = QWidget()
        self.rows = QGridLayout(self.rows_box)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setHorizontalSpacing(24)
        self.rows.setVerticalSpacing(6)
        col.addWidget(self.rows_box)
        self.note = QLabel(translate("Mixer", HONEST))
        self.note.setObjectName("caption")
        self.note.setWordWrap(True)
        col.addWidget(self.note)
        self.pages.addWidget(self.console)
        self.stem_rows: list[StemRow] = []
        self.preset_buttons: dict[str, QPushButton] = {}

    def build_console(self, mode: str) -> None:
        """The rows and presets of this mode, made again only when the mode changes."""
        names = stems.MODES[mode]["stems"]
        if [r.name for r in self.stem_rows] == names:
            return
        for r in self.stem_rows:
            r.setParent(None)
            r.deleteLater()
        self.stem_rows = [StemRow(n) for n in names]
        for r in self.stem_rows:
            r.changed.connect(self.rowChanged)
        for b in self.preset_buttons.values():
            self.preset_group.removeButton(b)
            b.setParent(None)
            b.deleteLater()
        self.preset_buttons = {}
        track = self.presets_frame.layout()
        keys = [k for k in stems.presets_for(mode) if k != "original"] + ["custom"]
        for key in keys:
            text = (
                translate("Mixer", "Personnalisé")
                if key == "custom"
                else translate("Stems", stems.PRESETS[key][0])
            )
            b = QPushButton(text)
            b.setCheckable(True)
            if key == "custom":
                b.setToolTip(translate("Mixer", "Revenir à votre propre réglage"))
            elif key == "all":
                b.setToolTip(
                    translate(
                        "Mixer",
                        "Toutes les pistes séparées à 0 dB, sans Muet ni Solo. Ce n'est pas "
                        "l'enregistrement d'origine : pour lui, choisissez « Original ».",
                    )
                )
            self.preset_group.addButton(b)
            self.preset_buttons[key] = b
            track.addWidget(b)
        self.reflow(self.width())

    def reflow(self, width: int) -> None:
        n = len(self.stem_rows)
        if not n:
            return
        avail = width - 32
        # Presets too wide beside Original/Mix (a narrow window): they go on a line of their own.
        wide = self.ab_frame.sizeHint().width() + 8 + self.presets_frame.sizeHint().width()
        d = QHBoxLayout.Direction
        self.top.setDirection(d.LeftToRight if avail >= wide else d.TopToBottom)
        cols = n if avail >= ROW_WIDTH * n else (2 if avail >= ROW_WIDTH * 2 else 1)
        for r in self.stem_rows:
            self.rows.removeWidget(r)
        for c in range(4):
            self.rows.setColumnStretch(c, 0)
        for i, r in enumerate(self.stem_rows):
            self.rows.addWidget(r, i // cols, i % cols)
        for c in range(cols):
            self.rows.setColumnStretch(c, 1)
        # A new number of lines changes the panel's height: the window lays out again after this.
        self.rows_box.updateGeometry()
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow(event.size().width())

    def show_page(self, page: QWidget) -> None:
        """Only the page shown counts for the panel's height."""
        for i in range(self.pages.count()):
            w = self.pages.widget(i)
            w.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred if w is page else QSizePolicy.Policy.Ignored,
            )
        self.pages.setCurrentWidget(page)
        self.pages.updateGeometry()
        self.updateGeometry()

    def show_work(self, step: str, progress: float | None, note: str = "", cancel=True) -> None:
        self.step.setText(step)
        if progress is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(progress * 1000))
        self.work_note.setText(note)
        self.work_note.setVisible(bool(note))
        self.cancel.setVisible(cancel)
        self.show_page(self.work)


class StoreDialog(QDialog):
    """What the separation keeps on the disk, and deleting it."""

    def __init__(self, controller: MixerController):
        super().__init__(controller.w)
        self.c = controller
        self.setWindowTitle(translate("Mixer", "Pistes séparées et modèle"))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.model = QLabel()
        self.model.setWordWrap(True)
        self.model.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.delete_model = QPushButton(translate("Mixer", "Supprimer le modèle…"))
        self.store = QLabel()
        self.store.setWordWrap(True)
        self.store.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.delete_all = QPushButton(translate("Mixer", "Supprimer toutes les pistes séparées…"))
        self.busy = QLabel()
        self.busy.setObjectName("caption")
        close = QPushButton(translate("Mixer", "Fermer"))
        close.clicked.connect(self.accept)
        for w, b in ((self.model, self.delete_model), (self.store, self.delete_all)):
            layout.addWidget(w)
            row = QHBoxLayout()
            row.addWidget(b)
            row.addStretch(1)
            layout.addLayout(row)
        layout.addWidget(self.busy)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.delete_model.clicked.connect(self._delete_model)
        self.delete_all.clicked.connect(self._delete_all)
        self.refresh()

    def refresh(self) -> None:
        m = stems.MODEL
        where = stems.model_path()
        if stems.model_installed():
            self.model.setText(
                translate(
                    "Mixer",
                    "<b>Modèle de séparation</b> : {label}, {size_text}, installé dans "
                    "{parent}.<br>SHA-256 : <code>{sha256}</code>",
                ).format(
                    label=translate("Stems", m["label"]),
                    size_text=stems.size_text(m["size"]),
                    parent=where.parent,
                    sha256=m["sha256"],
                )
            )
        else:
            self.model.setText(
                translate(
                    "Mixer",
                    "<b>Modèle de séparation</b> : {label}, non installé. Il sera téléchargé "
                    "({size_text}, vérifié par SHA-256) à la première séparation.",
                ).format(label=translate("Stems", m["label"]), size_text=stems.size_text(m["size"]))
            )
        folders = [p for p in stems.cache_root().glob("*") if p.is_dir()]
        songs = {p.name.split("-")[0] for p in folders}
        size = stems.size_of(folders)
        if size:
            head = translate(
                "Mixer",
                "<b>Pistes séparées</b> : {size} pour %n morceau(x), dans {folder}.",
                None,
                len(songs),
            ).format(size=stems.size_text(size), folder=stems.cache_root())
        else:
            head = translate("Mixer", "<b>Pistes séparées</b> : aucune, dans {folder}.").format(
                folder=stems.cache_root()
            )
        self.store.setText(
            head
            + "<br>"
            + translate(
                "Mixer",
                "Les morceaux, leurs accords, paroles, favoris, collections et corrections ne "
                "sont jamais supprimés ici.",
            )
        )
        busy = self.c.busy()
        self.busy.setText(
            translate("Mixer", "Une séparation est en cours : attendez qu'elle finisse.")
            if busy
            else ""
        )
        self.delete_model.setEnabled(not busy and stems.model_path().exists())
        self.delete_all.setEnabled(not busy and size > 0)

    def _delete_model(self) -> None:
        if _confirm(
            self,
            translate("Mixer", "Supprimer le modèle"),
            translate(
                "Mixer",
                "Supprimer le modèle de séparation ({size_text}) ?\n\nLes pistes déjà "
                "séparées restent utilisables. Il faudra le télécharger de nouveau pour "
                "séparer un autre morceau.",
            ).format(size_text=stems.size_text(stems.MODEL["size"])),
            translate("Mixer", "Supprimer le modèle"),
        ):
            stems.delete_model()
        self.refresh()

    def _delete_all(self) -> None:
        size = stems.total_size()
        if _confirm(
            self,
            translate("Mixer", "Supprimer toutes les pistes"),
            translate(
                "Mixer",
                "Supprimer toutes les pistes séparées ({size_text}) ?\n\nLes morceaux, "
                "accords, paroles et réglages ne sont pas touchés ; il faudra séparer de "
                "nouveau un morceau pour le mixer. Cette suppression est définitive.",
            ).format(size_text=stems.size_text(size)),
            translate("Mixer", "Tout supprimer"),
        ):
            self.c.forget_stems()
            stems.delete_all()
            self.c.refresh()
        self.refresh()


class MixerController(QObject):
    """Everything about separating and mixing, kept out of the main window: song_opened() when a
    song is shown, audio_loaded() once its recording is decoded, close() on quitting."""

    stemsLoaded = Signal(object, object, object)  # token, stems, error text

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        s = window.song
        self.panel = MixerPanel()
        self.panel.hide()
        layout = s.layout()
        layout.insertWidget(layout.indexOf(s.bottom), self.panel)
        self.button = s.mixer_button
        self.button.toggled.connect(self._button_toggled)
        p = self.panel
        p.close_button.clicked.connect(lambda: self.button.setChecked(False))
        p.separate.clicked.connect(lambda: self.separate(self._chosen_mode()))
        p.mode_group.buttonClicked.connect(lambda _b: self._show_facts())
        p.cancel.clicked.connect(self.cancel)
        p.original.clicked.connect(lambda: self._set(on=False))
        p.mixed.clicked.connect(lambda: self._set(on=True))
        p.rowChanged.connect(self._row_changed)
        p.preset_group.buttonClicked.connect(self._preset_clicked)
        p.more.menu().aboutToShow.connect(self._fill_menu)
        self.stemsLoaded.connect(self._stems_loaded)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)

        self.fp = ""
        self.settings: dict | None = None  # the mixer as set, once the song has stems
        self.folder: Path | None = None  # the stems in use
        self.load_token = None
        self.job: worker.Job | None = None
        self.job_for: dict | None = None  # fingerprint, mode, path, title of the job's song
        self.download: transcribe.Task | None = None
        self.export_task: transcribe.Task | None = None
        self.export_dialog: QProgressDialog | None = None
        self.error = ""
        self.button.setChecked(bool(window.settings.get("mixer_open")))

    # The song -------------------------------------------------------------------------------------
    def song_opened(self) -> None:
        project = self.w.project
        self.fp = project.audio.get("fingerprint") or ""
        self.load_token = None
        self.error = ""
        saved = stems.checked(project.view.get("mixer"))
        first = saved["mode"] if saved else self.w.settings.get("mixer_mode", stems.DEFAULT_MODE)
        if first not in stems.MODES:
            first = stems.DEFAULT_MODE
        self.folder, self.settings = None, None
        for mode in (first, _other(first)):
            folder = stems.cached(self.fp, mode) if self.fp else None
            if folder:
                self.folder = folder
                self.settings = self._saved(mode)
                break
        self.panel.mode_buttons[first].setChecked(True)
        self.refresh()

    def _saved(self, mode: str) -> dict:
        """This song's settings for `mode`: each mode keeps its own ("mixer" is the one in use)."""
        view = self.w.project.view
        for key in ("mixer", "mixer_other"):
            saved = stems.checked(view.get(key))
            if saved and saved["mode"] == mode:
                return saved
        return stems.new_settings(mode)

    def audio_loaded(self) -> None:
        if self.folder is not None:
            self._load_stems()
        else:
            self.refresh()  # separating needs the recording

    def _load_stems(self) -> None:
        token = object()
        self.load_token = token
        folder, mode, sr = self.folder, self.settings["mode"], self.w.player.sr
        frames = len(self.w.player.mix.original if self.w.player.mix else self.w.player.y)

        def run():
            try:
                y = stems.load(folder, mode, sr, frames, lambda: self.load_token is not token)
                self.stemsLoaded.emit(token, y, None)
            except MemoryError:
                self.stemsLoaded.emit(
                    token, None, translate("Mixer", "Mémoire insuffisante pour lire les pistes.")
                )
            except Exception as exc:  # noqa: BLE001 - a damaged cache is shown, not raised
                if self.load_token is token:
                    self.stemsLoaded.emit(
                        token,
                        None,
                        translate("Mixer", "Impossible de lire les pistes : {exc}").format(exc=exc),
                    )

        threading.Thread(target=run, daemon=True).start()
        self.refresh()

    def _stems_loaded(self, token, layers, error, faded=False) -> None:
        if token is not self.load_token:
            return
        self.load_token = None
        player = self.w.player
        if error:
            self.error = translate(
                "Mixer", "{error} Elles peuvent être séparées de nouveau."
            ).format(error=error)
            self.folder = None
            player.use_mix(None)  # another mode's stems may still be playing
        else:
            old = player.mix
            if old is not None and player.playing and not faded and old.gains[0] != 1.0:
                # Other stems are being heard: back to the recording first, which both mixes
                # start from, then the swap, so that changing mixes never clicks.
                old.set_gains(1.0, [0.0] * len(old.stems))
                self.load_token = token
                QTimer.singleShot(
                    int(Mix.RAMP * 1000) + 30,
                    lambda: self._stems_loaded(token, layers, None, faded=True),
                )
                return
            original = old.original if old else player.y
            player.use_mix(Mix(original, layers, player.sr))
            self._apply(save=False)
        self.refresh()

    def forget_stems(self) -> None:
        """Back to the recording alone, before the stems are deleted."""
        self.load_token = None
        self.w.player.use_mix(None)
        self.folder = None

    # What the panel shows -------------------------------------------------------------------------
    def busy(self) -> bool:
        return self.job is not None or self.download is not None

    def _ours(self) -> bool:
        return bool(self.job_for) and self.job_for["fingerprint"] == self.fp

    def _chosen_mode(self) -> str:
        return next(m for m, b in self.panel.mode_buttons.items() if b.isChecked())

    def refresh(self) -> None:
        p = self.panel
        if self.busy() and self._ours():
            return  # the job's own messages keep the work page current
        if self.folder is not None and self.w.player.mix is not None:
            p.state.setText(translate("Mixer", SHORT_MODE[self.settings["mode"]]))
            self._show_settings()
            p.show_page(p.console)
        elif self.folder is not None:
            p.state.setText("")
            step = (
                translate("Mixer", "Chargement des pistes séparées…")
                if self.w.audio_ready
                else (
                    translate("Mixer", "Les pistes séparées seront prêtes avec l'enregistrement.")
                )
            )
            p.show_work(step, None, cancel=False)
        else:
            p.state.setText("")
            self._show_facts()
            p.show_page(p.intro)
        self._show_button()

    def _show_facts(self) -> None:
        p = self.panel
        project = self.w.project
        if project is None:
            return
        mode = self._chosen_mode()
        duration = project.duration
        lines = []
        m = stems.MODEL
        size = stems.size_text(m["size"])
        if stems.model_installed():
            lines.append(
                translate("Mixer", "Modèle : {label}, déjà installé.").format(
                    label=translate("Stems", m["label"])
                )
            )
        else:
            lines.append(
                translate("Mixer", "Modèle : {label}, {size} à télécharger une seule fois.").format(
                    label=translate("Stems", m["label"]), size=size
                )
            )
        lines.append(
            translate("Mixer", "Place nécessaire : environ {needed_mb} Mo pour ce morceau.").format(
                needed_mb=stems.needed_mb(duration, mode)
            )
        )
        speed = self.w.settings.get("separation_speed")
        if isinstance(speed, (int, float)) and speed > 0:
            seconds = max(5, round(duration * speed / 5) * 5)
            lines.append(
                translate(
                    "Mixer", "Durée estimée : environ {duration} (mesurée sur cet ordinateur)."
                ).format(duration=_duration(seconds))
            )
        lines.append(translate("Mixer", HONEST))
        p.facts.setText("\n".join(lines))
        warn = [self.error] if self.error else []
        problem = stems.space_problem(duration, mode)
        if problem:
            warn.append(problem)
        elif stems.removable(stems.cache_root()):
            warn.append(
                translate(
                    "Mixer",
                    "Les données sont sur une clé USB ou une carte mémoire : l'écriture des "
                    "pistes sera plus lente et use le support.",
                )
            )
        if self.busy() and not self._ours():
            warn.append(
                translate(
                    "Mixer",
                    "Une séparation est en cours pour « {title} » : attendez qu'elle finisse "
                    "pour en lancer une autre.",
                ).format(title=self.job_for["title"])
            )
        p.warn.setText("\n".join(warn))
        p.warn.setVisible(bool(warn))
        audio = self.w.audio_ready
        p.separate.setEnabled(audio and not problem and not self.busy() and bool(self.fp))
        p.separate.setText(
            translate("Mixer", "Réessayer")
            if self.error
            else translate("Mixer", "Séparer les instruments")
        )

    def _show_settings(self) -> None:
        p, s = self.panel, self.settings
        p.build_console(s["mode"])
        p.original.setChecked(not s["on"])
        p.mixed.setChecked(s["on"])
        current = stems.current_preset(s)
        p.preset_group.setExclusive(False)
        for key, b in p.preset_buttons.items():
            b.setChecked(s["on"] and key == current)
        p.preset_group.setExclusive(True)
        p.preset_buttons["custom"].setEnabled(bool(s.get("custom")) or current == "custom")
        for row in p.stem_rows:
            row.show_settings(s)

    def _show_button(self) -> None:
        active = self.w.player.mix is not None and self.settings and self.settings["on"]
        self.button.setToolTip(
            translate(
                "Mixer",
                "Mixage : séparer les instruments et régler leur volume (M) ; un mix "
                "personnalisé est en cours d'écoute",
            )
            if active
            else translate("Mixer", "Mixage : séparer les instruments et régler leur volume (M)")
        )

    # The panel, opened and closed -----------------------------------------------------------------
    def toggle_panel(self) -> None:
        self.button.toggle()

    def _button_toggled(self, on: bool) -> None:
        self.panel.setVisible(on)
        self.w._remember("mixer_open", on)
        if on:
            self.refresh()

    # Setting the mix ------------------------------------------------------------------------------
    def _row_changed(self, name: str, what: str, value) -> None:
        s = self.settings
        if s is None:
            return
        if what == "level":
            s["levels"][name] = int(value)
        else:
            names = [n for n in s[what] if n != name]
            s[what] = [*names, name] if value else names
        s["on"] = True  # touching a stem means wanting to hear the stems
        s["custom"] = {
            "levels": dict(s["levels"]),
            "mute": list(s["mute"]),
            "solo": list(s["solo"]),
        }
        self._apply()

    def _set(self, **values) -> None:
        if self.settings is not None:
            self.settings = {**self.settings, **values}
            self._apply()

    def toggle_original(self) -> None:
        if self.settings is not None and self.w.player.mix is not None:
            self._set(on=not self.settings["on"])

    def _preset_clicked(self, button) -> None:
        key = next(k for k, b in self.panel.preset_buttons.items() if b is button)
        if self.settings is None:
            return
        if key == "custom":
            self.settings = stems.restore_custom({**self.settings, "on": True})
        else:
            self.settings = stems.apply_preset(self.settings, key)
        self._apply()

    def _apply(self, save: bool = True) -> None:
        mix = self.w.player.mix
        s = self.settings
        n = len(stems.MODES[s["mode"]]["stems"]) if s is not None else 0
        # The other mode's stems may still be playing while these load: they keep their gains.
        if mix is not None and s is not None and len(mix.stems) == n:
            mix.set_gains(0.0 if s["on"] else 1.0, stems.gains(s) if s["on"] else [0.0] * n)
        if s is not None:
            self._show_settings()
            self._show_button()
        if save and self.w.project is not None and s is not None:
            view = self.w.project.view
            before = stems.checked(view.get("mixer"))
            if before and before["mode"] != s["mode"]:
                view["mixer_other"] = before  # the other mode's mix, kept for coming back to it
            self.w.project.set_view(mixer=s)
            self.w.save_timer.start()

    # Separating -----------------------------------------------------------------------------------
    def separate(self, mode: str) -> None:
        project = self.w.project
        if project is None or self.busy() or not self.fp:
            return
        path = library.audio_file(project.audio)
        if not path.is_file():
            self.error = translate("Mixer", "Le fichier audio est introuvable : {path}.").format(
                path=path
            )
            self.refresh()
            return
        problem = stems.space_problem(project.duration, mode)
        if problem:
            self.error = problem
            self.refresh()
            return
        self.error = ""
        self.w._remember("mixer_mode", mode)
        self.job_for = {
            "fingerprint": self.fp,
            "mode": mode,
            "path": path,
            "title": project.audio.get("title") or path.stem,
        }
        if stems.model_installed():
            self._start_job()
        else:
            self.download = transcribe.run(stems.download_model)
            self.panel.show_work(
                translate("Mixer", "Téléchargement du modèle de séparation…"),
                0.0,
                translate(
                    "Mixer",
                    "{label} : {size_text}, une seule fois, vérifié par SHA-256. La lecture "
                    "reste possible pendant ce temps.",
                ).format(
                    label=translate("Stems", stems.MODEL["label"]),
                    size_text=stems.size_text(stems.MODEL["size"]),
                ),
            )
        self.timer.start()

    def _start_job(self) -> None:
        j = self.job_for
        self.job = worker.start_separation(j["path"], j["mode"], j["fingerprint"])
        if self._ours():
            self.panel.show_work(
                translate("Mixer", "Séparation des instruments…"),
                0.0,
                translate(
                    "Mixer",
                    "Sur cet ordinateur, en arrière-plan : la lecture, les accords et le "
                    "reste du programme restent utilisables.",
                ),
            )

    def cancel(self) -> None:
        if self.download is not None:
            self.download.cancel()
            self.download = None
        if self.job is not None:
            self.job.cancel()
            self.job = None
        self.job_for = None
        if self.export_task is None:
            self.timer.stop()
        self.refresh()

    def _poll(self) -> None:
        if self.download is not None:
            task = self.download
            if self._ours():
                self.panel.show_work(
                    translate("Mixer", "Téléchargement du modèle de séparation… {status}").format(
                        status=task.status
                    ),
                    task.progress,
                    self.panel.work_note.text(),
                )
            if task.done:
                self.download = None
                if task.error:
                    self._failed(task.error)
                else:
                    self._start_job()
        if self.job is not None:
            for message in self.job.poll():
                kind = message[0]
                if kind == "progress" and self._ours():
                    self.panel.show_work(message[2], message[1], self.panel.work_note.text())
                elif kind == "done":
                    self._separated(Path(message[1]), message[2], message[3])
                elif kind == "error":
                    self._failed(message[1])
                    if message[2]:
                        from .main_window import _log

                        _log(message[2])
        if self.export_task is not None:
            self._poll_export()
        if self.job is None and self.download is None and self.export_task is None:
            self.timer.stop()

    def _failed(self, text: str) -> None:
        ours = self._ours()
        if self.job is not None:
            self.job.cancel()
        self.job, self.job_for = None, None
        if ours:
            self.error = text
        self.refresh()

    def _separated(self, folder: Path, seconds: float, duration: float) -> None:
        mode = self.job_for["mode"]
        ours = self._ours()
        self.job.cancel()  # already ended: closes the pipe
        self.job, self.job_for = None, None
        if duration > 0:
            self.w._remember("separation_speed", round(seconds / duration, 3))
        if not ours:
            self.refresh()
            return
        if self.settings is None or self.settings["mode"] != mode:
            self.settings = self._saved(mode)
        self.folder = folder
        if self.w.audio_ready:  # what is playing now goes on until the new stems are read
            self._load_stems()
        else:
            self.refresh()
        self._apply()

    # The menu -------------------------------------------------------------------------------------
    def _fill_menu(self) -> None:
        menu = self.panel.more.menu()
        menu.clear()
        ready = self.w.player.mix is not None and self.settings is not None
        export = menu.addAction(translate("Mixer", "Exporter le mix (FLAC ou WAV)…"), self.export)
        export.setEnabled(ready and self.export_task is None)
        if self.settings is not None:
            other = _other(self.settings["mode"])
            name = translate("Mixer", SHORT_MODE[other]).split(" ·")[0]
            if stems.cached(self.fp, other):
                menu.addAction(
                    translate("Mixer", "Utiliser les pistes du mode {name}").format(name=name),
                    lambda: self.use_mode(other),
                )
            else:
                action = menu.addAction(
                    translate("Mixer", "Séparer aussi en mode {name}…").format(name=name),
                    lambda: self.separate(other),
                )
                action.setEnabled(not self.busy() and self.w.audio_ready)
        menu.addSeparator()
        size = stems.size_of(stems.song_folders(self.fp))
        delete = menu.addAction(
            translate("Mixer", "Supprimer les pistes de ce morceau ({size_text})…").format(
                size_text=stems.size_text(size)
            )
            if size
            else translate("Mixer", "Supprimer les pistes de ce morceau"),
            self.delete_song,
        )
        delete.setEnabled(bool(size) and not (self.busy() and self._ours()))
        menu.addAction(translate("Mixer", "Pistes séparées et modèle…"), self.show_store)

    def use_mode(self, mode: str) -> None:
        folder = stems.cached(self.fp, mode)
        if not folder:
            return
        self.settings = self._saved(mode)
        self.folder = folder
        self.w._remember("mixer_mode", mode)
        self._load_stems()
        self._apply()

    def delete_song(self) -> None:
        size = stems.size_of(stems.song_folders(self.fp))
        if not size or not _confirm(
            self.w,
            translate("Mixer", "Supprimer les pistes séparées"),
            translate(
                "Mixer",
                "Supprimer les pistes séparées de ce morceau ({size_text}) ?\n\nLe "
                "morceau, ses accords, ses paroles et vos réglages ne sont pas touchés ; "
                "il faudra le séparer de nouveau pour le mixer.",
            ).format(size_text=stems.size_text(size)),
            translate("Mixer", "Supprimer les pistes"),
        ):
            return
        self.forget_stems()
        stems.delete_song(self.fp)
        self.refresh()

    def show_store(self) -> None:
        StoreDialog(self).exec()

    # Exporting ------------------------------------------------------------------------------------
    def export(self) -> None:
        project = self.w.project
        if project is None or self.folder is None or self.settings is None:
            return
        title = project.audio.get("title") or "morceau"
        safe = "".join(c for c in title if c not in '<>:"/\\|?*').strip() or "morceau"
        name, chosen = QFileDialog.getSaveFileName(
            self.w,
            translate("Mixer", "Exporter le mix"),
            str(Path.home() / f"{safe} (mix).flac"),
            translate("Mixer", "FLAC, sans perte (*.flac);;WAV (*.wav)"),
        )
        if not name:
            return
        target = Path(name)
        if target.suffix.lower() not in (".flac", ".wav"):
            # Added, not replaced: "Live 1.5" is a name, not a file type.
            target = target.with_name(target.name + (".wav" if "WAV" in chosen else ".flac"))
            if target.exists() and not _confirm(
                self.w,
                translate("Mixer", "Exporter le mix"),
                translate("Mixer", "« {name} » existe déjà. Le remplacer ?").format(
                    name=target.name
                ),
                translate("Mixer", "Remplacer"),
            ):
                return
        recording = library.audio_file(project.audio)
        folder, settings = self.folder, dict(self.settings)
        self.export_task = transcribe.run(
            lambda t: stems.export_mix(target, recording, folder, settings, t)
        )
        dialog = QProgressDialog(
            translate("Mixer", "Export du mix…"), translate("Mixer", "Annuler"), 0, 1000, self.w
        )
        dialog.setWindowTitle(translate("Mixer", "Exporter le mix"))
        dialog.setMinimumDuration(300)
        dialog.canceled.connect(self.export_task.cancel)
        self.export_dialog = dialog
        self.timer.start()

    def _poll_export(self) -> None:
        task, dialog = self.export_task, self.export_dialog
        dialog.setLabelText(task.status or translate("Mixer", "Export du mix…"))
        dialog.setValue(int(task.progress * 1000))
        if not task.done:
            return
        self.export_task, self.export_dialog = None, None
        dialog.reset()
        dialog.deleteLater()
        if task.error and not task.cancelled:
            self.w._alert(
                translate("Mixer", "L'export du mix a échoué : {error}").format(error=task.error)
            )
        elif not task.error:
            self.panel.note.setText(
                translate("Mixer", "Mix exporté : {result}. {honest}").format(
                    result=task.result, honest=translate("Mixer", HONEST)
                )
            )

    # Quitting -------------------------------------------------------------------------------------
    def close(self) -> None:
        self.load_token = None
        if self.export_task is not None:
            self.export_task.cancel()
        if self.download is not None:
            self.download.cancel()
        if self.job is not None:
            self.job.cancel()
        self.job = self.download = None
        self.timer.stop()


def _duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    m, s = divmod(seconds, 60)
    return f"{m} min {s:02d} s" if s else f"{m} min"
