"""The window: a home screen to bring a song in, a song screen to read and play it."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, audio, engines, export, i18n, identify, library, voicings, worker
from .. import catalog as C
from .. import lyrics as L
from ..chords import key_name, parse, spell_tonic, symbol
from ..i18n import translate
from ..player import Player, device_sample_rate
from ..project import EXTENSION, Project, ProjectError, decode_waveform
from . import theme
from .diagrams import ChordPanel, Positions
from .dialogs import ChordEditor, RhythmDialog, SheetDialog, ShortcutsDialog
from .grid import ChordGrid
from .library_view import LibraryPage
from .lyrics_view import LyricsController
from .mixer import MixerController
from .pdf import write_chord_sheet, write_pdf
from .songchords import UPCOMING, Item, SongChords, chord_key
from .update_banner import UpdateController
from .waveform import Waveform
from .widgets import ElidedLabel, Stepper, fmt_time, language_menu

AUDIO_FILTER = "Audio (" + " ".join(f"*{e}" for e in audio.AUDIO_EXTENSIONS) + ")"
SIDE_PANEL_WIDTH = 1280
MIN_WIDTH = 800  # every bar collapses to fit this; a tiling window manager may go narrower
SPEEDS = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.1, 1.25, 1.5]


class AudioLoader(QObject):
    """Decode for playback off the interface's thread."""

    finished = Signal(object, object, object)  # token, samples, error text

    def load(self, path: Path, rate: int) -> object:
        token = object()
        self.current = token

        def run():
            try:
                y = audio.decode(path, rate, should_cancel=lambda: self.current is not token)
                self.finished.emit(token, y, None)
            except audio.Cancelled:
                pass
            except audio.AudioError as exc:
                self.finished.emit(token, None, str(exc))
            except MemoryError:
                self.finished.emit(
                    token,
                    None,
                    translate("MainWindow", "Mémoire insuffisante pour charger ce morceau."),
                )

        threading.Thread(target=run, daemon=True).start()
        return token


class GridScroll(QScrollArea):
    """Tells the grid how much room it has, for it to choose its layout."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.widget().set_view_height(self.viewport().height())


class SongPage(QWidget):
    """Everything about the open song, top to bottom: facts, overview, grid, transport."""

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Facts and file actions.
        top = QWidget()
        top.setObjectName("bar")
        top.setProperty("quiet", True)
        row = QHBoxLayout(top)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        self.home = QToolButton()
        self.home.setIcon(theme.icon("home"))
        self.home.setToolTip(translate("MainWindow", "Retour à l'accueil"))
        self.home.setAccessibleName(translate("MainWindow", "Accueil"))
        row.addWidget(self.home)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = ElidedLabel()
        self.title.setObjectName("songTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle = ElidedLabel()
        self.subtitle.setObjectName("caption")
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 3)
        # Now and next: what to play without reading the grid.
        self.now = QLabel("—")
        self.now.setObjectName("chordNow")
        self.now.setAccessibleName(translate("MainWindow", "Accord en cours"))
        self.now.setMinimumWidth(96)
        self.now.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.next = QLabel("")
        self.next.setObjectName("chordNext")
        self.next.setAccessibleName(translate("MainWindow", "Accord suivant"))
        self.next.setMinimumWidth(80)
        row.addWidget(self.now)
        row.addWidget(self.next)
        row.addStretch(2)
        self.key_button = QToolButton()
        self.key_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.key_button.setAccessibleName(translate("MainWindow", "Tonalité"))
        self.rhythm_button = QToolButton()
        self.rhythm_button.setAccessibleName(translate("MainWindow", "Tempo et mesure"))
        self.rhythm_button.setToolTip(
            translate("MainWindow", "Corriger le tempo, la mesure ou le décalage de la grille")
        )
        self.undo = QToolButton()
        self.undo.setIcon(theme.icon("undo"))
        self.undo.setToolTip(translate("MainWindow", "Annuler la dernière correction (Ctrl + Z)"))
        self.undo.setAccessibleName(translate("MainWindow", "Annuler"))
        self.redo = QToolButton()
        self.redo.setIcon(theme.icon("redo"))
        self.redo.setToolTip(translate("MainWindow", "Rétablir (Ctrl + Y)"))
        self.redo.setAccessibleName(translate("MainWindow", "Rétablir"))
        self.export = QToolButton()
        self.export.setText(translate("MainWindow", "Exporter"))
        self.export.setIcon(theme.icon("export"))
        self.export.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export.setToolTip(translate("MainWindow", "Exporter (Ctrl + E)"))
        self.diagrams_button = QToolButton()
        self.diagrams_button.setIcon(theme.icon("diagram"))
        self.diagrams_button.setCheckable(True)
        self.diagrams_button.setToolTip(
            translate("MainWindow", "Diagrammes de guitare et de piano (D)")
        )
        self.diagrams_button.setAccessibleName(translate("MainWindow", "Diagrammes d'accords"))
        self.chords_button = QToolButton()
        self.chords_button.setIcon(theme.icon("cards"))
        self.chords_button.setCheckable(True)
        self.chords_button.setToolTip(
            translate("MainWindow", "Accords du morceau : tous, ou ceux à venir (T)")
        )
        self.chords_button.setAccessibleName(translate("MainWindow", "Accords du morceau"))
        self.star = QToolButton()
        self.star.setCheckable(True)
        self.star.setObjectName("star")
        self.star.setIcon(theme.icon("star_line", theme.TEXT_2))
        self.star.setToolTip(translate("MainWindow", "Ajouter aux favoris"))
        self.star.setAccessibleName(translate("MainWindow", "Favori"))
        self.menu = QToolButton()
        self.menu.setIcon(theme.icon("menu"))
        self.menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu.setToolTip(translate("MainWindow", "Plus d'options"))
        self.menu.setAccessibleName(translate("MainWindow", "Plus d'options"))
        # Undo and redo step aside on a narrow window (Ctrl + Z and Ctrl + Y stay).
        self.history = QWidget()
        history = QHBoxLayout(self.history)
        history.setContentsMargins(0, 0, 0, 0)
        history.setSpacing(8)
        history.addWidget(self.undo)
        history.addWidget(self.redo)
        # What gives way on a narrow window: labels first (the icon, the tooltip and the
        # accessible name stay), then the long forms of the key and the tempo.
        self.collapsible = [self.export]
        self._facts = {}
        for w in (
            self.star,
            self.key_button,
            self.rhythm_button,
            self.history,
            self.export,
            self.chords_button,
            self.diagrams_button,
            self.menu,
        ):
            row.addWidget(w)
        layout.addWidget(top)

        self.banner = QWidget()
        self.banner.setObjectName("bar")
        banner_row = QHBoxLayout(self.banner)
        banner_row.setContentsMargins(16, 8, 16, 8)
        self.banner_text = QLabel()
        self.banner_text.setWordWrap(True)
        self.banner_action = QPushButton()
        self.banner_action.setObjectName("primary")
        self.banner_close = QToolButton()
        self.banner_close.setIcon(theme.icon("close", size=14))
        self.banner_close.setAccessibleName(translate("MainWindow", "Fermer le message"))
        banner_row.addWidget(self.banner_text, 1)
        banner_row.addWidget(self.banner_action)
        banner_row.addWidget(self.banner_close)
        self.banner_close.clicked.connect(self.banner.hide)
        self.banner.hide()
        layout.addWidget(self.banner)

        self.waveform = Waveform()
        layout.addWidget(self.waveform)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # The grid, or what stands in for it while there is none.
        self.middle = QStackedWidget()
        self.grid = ChordGrid()
        self.scroll = GridScroll()
        self.scroll.setAccessibleName(translate("MainWindow", "Grille d'accords"))
        self.scroll.setWidget(self.grid)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.middle.addWidget(self.scroll)
        self.status_page = QWidget()
        self.status_page.setObjectName("page")
        status = QVBoxLayout(self.status_page)
        status.addStretch()
        self.status_text = QLabel()
        self.status_text.setObjectName("title")
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setWordWrap(True)
        self.status_detail = QLabel()
        self.status_detail.setObjectName("muted")
        self.status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail.setWordWrap(True)
        self.status_button = QPushButton()
        self.status_button.setObjectName("primary")
        status.addWidget(self.status_text)
        status.addWidget(self.status_detail)
        center = QHBoxLayout()
        center.addStretch()
        center.addWidget(self.status_button)
        center.addStretch()
        status.addLayout(center)
        status.addStretch()
        self.middle.addWidget(self.status_page)
        # One choice of position per chord, whichever diagram shows it.
        self.positions = Positions()
        self.panel = ChordPanel(self.positions)
        self.split = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.split.setSpacing(0)
        self.split.addWidget(self.middle, 1)
        self.split.addWidget(self.panel)
        layout.addLayout(self.split, 1)
        self.chords = SongChords(self.positions)
        layout.addWidget(self.chords)
        self.chords.stateChanged.connect(
            lambda state: layout.setStretchFactor(self.chords, 1 if state == "expanded" else 0)
        )

        # Transport and practice tools, in the order they get used.
        bottom = QWidget()
        bottom.setObjectName("bar")
        controls = QHBoxLayout(bottom)
        controls.setContentsMargins(16, 10, 16, 10)
        controls.setSpacing(8)
        self.back = QToolButton()
        self.back.setIcon(theme.icon("prev"))
        self.back.setToolTip(translate("MainWindow", "Revenir au début (Début)"))
        self.back.setAccessibleName(translate("MainWindow", "Revenir au début"))
        self.play = QToolButton()
        self.play.setObjectName("play")
        self.play.setIcon(theme.icon("play", theme.ON_ACCENT, 22))
        self.play.setIconSize(self.play.iconSize() * 1.3)
        self.play.setToolTip(translate("MainWindow", "Lecture / pause (Espace)"))
        self.play.setAccessibleName(translate("MainWindow", "Lecture"))
        self.time = QLabel("0:00 / 0:00")
        self.time.setObjectName("time")
        self.place = QLabel(" ")
        self.place.setObjectName("caption")
        clock = QVBoxLayout()
        clock.setSpacing(0)
        clock.setContentsMargins(0, 0, 0, 0)
        clock.addWidget(self.time)
        clock.addWidget(self.place)
        clock_box = QWidget()
        clock_box.setLayout(clock)
        clock_box.setFixedWidth(136)
        controls.addWidget(self.back)
        controls.addWidget(self.play)
        controls.addWidget(clock_box)
        controls.addStretch(1)

        self.loop_button = QPushButton(translate("MainWindow", " Boucle"))
        self.loop_button.setIcon(theme.icon("loop", size=16))
        self.loop_button.setCheckable(True)
        self.loop_button.setAccessibleName(translate("MainWindow", "Boucle"))
        self.loop_button.setToolTip(
            translate("MainWindow", "Boucler la sélection, ou arrêter la boucle (L)")
        )
        self.loop_a = QPushButton("A")
        self.loop_a.setToolTip(
            translate("MainWindow", "Début de boucle à la position actuelle (A)")
        )
        self.loop_a.setAccessibleName(translate("MainWindow", "Début de boucle"))
        self.loop_b = QPushButton("B")
        self.loop_b.setToolTip(translate("MainWindow", "Fin de boucle à la position actuelle (B)"))
        self.loop_b.setAccessibleName(translate("MainWindow", "Fin de boucle"))
        for w in (self.loop_a, self.loop_b, self.loop_button):
            controls.addWidget(w)

        self.speed = Stepper(
            translate("MainWindow", "Vitesse"),
            0,
            len(SPEEDS) - 1,
            SPEEDS.index(1.0),
            lambda i: translate("MainWindow", "{percent} %").format(percent=round(SPEEDS[i] * 100)),
            translate("MainWindow", "Ralentir sans changer la hauteur (- / +)"),
        )
        controls.addWidget(self.speed)
        self.transpose = Stepper(
            translate("MainWindow", "Transposer"),
            -12,
            12,
            0,
            lambda v: f"{v:+d}" if v else "0",
            translate("MainWindow", "Transposer la grille, en demi-tons (Ctrl + ↑ / ↓)."),
        )
        controls.addWidget(self.transpose)
        # Right next to the transposition, so whether the sound follows is never a guess.
        self.audio_button = QPushButton()
        self.audio_button.setIcon(theme.icon("volume", size=16))
        self.audio_button.setCheckable(True)
        self.audio_button.setAccessibleName(translate("MainWindow", "Transposer également l'audio"))
        self.audio_button.toggled.connect(self._show_audio_state)
        # Its label must not set the window's minimum width: it gives way first (adapt_to_width).
        self.audio_button.setMinimumWidth(36)
        self._show_audio_state(False)
        controls.addWidget(self.audio_button)
        self.capo = Stepper(
            translate("MainWindow", "Capo"),
            0,
            11,
            0,
            str,
            translate("MainWindow", "Case du capodastre : la grille montre les formes à jouer."),
        )
        controls.addWidget(self.capo)
        self.mixer_button = QPushButton()
        self.mixer_button.setIcon(theme.icon("mixer", size=16))
        self.mixer_button.setCheckable(True)
        self.mixer_button.setAccessibleName(translate("MainWindow", "Mixage"))
        self.mixer_button.setToolTip(
            translate("MainWindow", "Mixage : séparer les instruments et régler leur volume (M)")
        )
        self.mixer_button.setMinimumWidth(36)
        controls.addWidget(self.mixer_button)

        # How the chords are written: asked for rarely, kept one click away.
        self.display = QToolButton()
        self.display.setText(translate("MainWindow", "Affichage"))
        self.display.setIcon(theme.icon("sliders", size=16))
        self.display.setAccessibleName(translate("MainWindow", "Affichage des accords"))
        self.display.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.display.setToolTip(
            translate("MainWindow", "Niveau de détail, altérations et accords courts")
        )
        self.display.setMenu(QMenu(self.display))
        self.detail_actions = self._choices(
            translate("MainWindow", "Accords"),
            (
                (translate("MainWindow", "Complets"), "full"),
                (translate("MainWindow", "Simplifiés (accords de base)"), "simple"),
                (translate("MainWindow", "Complets, avec analyse des degrés"), "analysis"),
            ),
        )
        self.accidental_actions = self._choices(
            translate("MainWindow", "Altérations"),
            (
                (translate("MainWindow", "Selon la tonalité"), "auto"),
                (translate("MainWindow", "Dièses (♯)"), "sharps"),
                (translate("MainWindow", "Bémols (♭)"), "flats"),
            ),
        )
        self.smooth_actions = self._choices(
            translate("MainWindow", "Accords très courts"),
            (
                (translate("MainWindow", "Tous les afficher"), 1),
                (translate("MainWindow", "Ignorer sous 2 temps"), 2),
                (translate("MainWindow", "Ignorer sous 3 temps"), 3),
                (translate("MainWindow", "Ignorer sous 4 temps"), 4),
            ),
        )
        controls.addWidget(self.display)

        self.volume_icon = QLabel()
        self.volume_icon.setPixmap(theme.pixmap("volume", theme.TEXT_2, 16))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(64)
        self.volume.setAccessibleName(translate("MainWindow", "Volume"))
        self.volume.setToolTip(translate("MainWindow", "Volume"))
        controls.addWidget(self.volume_icon)
        controls.addWidget(self.volume)
        layout.addWidget(bottom)
        self.bottom = bottom  # the mixer's panel goes just above it
        self.adapt_to_width(1360)

    def _show_audio_state(self, on: bool) -> None:
        self._audio_text = (
            translate("MainWindow", " Son transposé")
            if on
            else translate("MainWindow", " Son d'origine")
        )
        self.audio_button.setText(self._audio_text if self._audio_wide else "")
        self.audio_button.setToolTip(
            translate(
                "MainWindow",
                "Transposer également l'audio : activé. Cliquer pour n'entendre que l'original.",
            )
            if on
            else translate(
                "MainWindow",
                "Transposer également l'audio : désactivé, seule la grille change. "
                "Cliquer pour que le son suive la transposition, à la même vitesse.",
            )
        )

    _audio_wide = True

    def adapt_to_width(self, width: int) -> None:
        """A tiling window manager can make the window narrower than its minimum, so what is
        rarely needed gives way first; all of it stays on the keyboard."""
        self._top_wide = width >= 1240
        for button in self.collapsible:
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if self._top_wide
                else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
        for button, (full, short) in self._facts.items():
            button.setText(full if self._top_wide else short)
        self.history.setVisible(width >= 900)
        self.display.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
            if width >= 960
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        theme.restyle(self.display)  # the style sheet frames it only with its text
        self._audio_wide = width >= 1240  # narrower, the icon and its highlight say it
        self.audio_button.setText(self._audio_text if self._audio_wide else "")
        self.mixer_button.setText(translate("MainWindow", " Mixage") if self._audio_wide else "")
        for widget in (self.volume, self.volume_icon):
            widget.setVisible(width >= 1160)
        for widget in (self.loop_a, self.loop_b):
            widget.setVisible(width >= 1040)  # room for the Mixage button
        self.capo.setVisible(width >= 860)
        # Beside the grid when the grid keeps room for its bars, under it otherwise.
        side = width >= SIDE_PANEL_WIDTH
        self.split.setDirection(
            QBoxLayout.Direction.LeftToRight if side else QBoxLayout.Direction.TopToBottom
        )
        self.panel.set_orientation(side, wide=width >= 2400)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adapt_to_width(event.size().width())

    def set_fact(self, button: QToolButton, full: str, short: str) -> None:
        """A fact in the top bar, said in full when there is room."""
        self._facts[button] = (full, short)
        button.setText(full if self._top_wide else short)

    def sync_panel(self, has_grid: bool) -> None:
        """No diagrams before there is a grid to follow."""
        shown = self.panel.state != "hidden"
        self.diagrams_button.setVisible(has_grid)
        self.diagrams_button.blockSignals(True)
        self.diagrams_button.setChecked(shown)
        self.diagrams_button.blockSignals(False)
        self.panel.setVisible(has_grid and shown)
        listed = self.chords.state != "hidden"
        self.chords_button.setVisible(has_grid)
        self.chords_button.blockSignals(True)
        self.chords_button.setChecked(listed)
        self.chords_button.blockSignals(False)
        self.chords.setVisible(has_grid and listed)

    def _choices(self, title: str, options) -> QActionGroup:
        """A titled group of exclusive choices in the display menu."""
        menu = self.display.menu()
        menu.addSection(title)
        group = QActionGroup(self)
        for text, value in options:
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setData(value)
            group.addAction(action)
        return group


class MainWindow(QMainWindow):
    def __init__(self, *, muted: bool = False):
        super().__init__()
        self.setWindowTitle("LocalChords")
        self.setWindowIcon(QIcon(QPixmap.fromImage(theme.app_image())))
        self.setAcceptDrops(True)
        self.resize(1360, 820)
        # Set, so the bars' widest content does not decide it: they collapse to fit instead.
        self.setMinimumWidth(MIN_WIDTH)
        self.settings = library.load_settings()
        self.player = Player(device_sample_rate())
        self.player.volume = 0.0 if muted else float(self.settings.get("volume", 1.0))
        self.muted = muted
        self.project: Project | None = None
        self.project_file: Path | None = None
        self.job: worker.Job | None = None
        self.job_path: Path | None = None
        self.job_engine: str | None = None
        self.audio_ready = False
        self.audio_token = None
        self.loader = AudioLoader()
        self.loader.finished.connect(self._audio_loaded)
        self.loop_marks: list[float | None] = [None, None]
        self.pending_source_url: str | None = None
        self.pending_info: dict | None = None  # what yt-dlp read on the site, for the next file
        self.download_job: worker.Job | None = None
        self.batch_job: worker.Job | None = None
        self.batch_queue: list[Path] = []
        self.compare_engine: str | None = None
        # The diagrams stay on the chord at this time (not a beat: a grid edit renumbers beats).
        self.pinned_at: float | None = None
        self._panel_restore = "full"
        self._shown_list: list = []  # each segment as the diagrams show it, None for no chord
        self._upcoming_at: int | None = None
        self._positions_of = None  # the project the position choices were loaded from

        self.stack = QStackedWidget()
        self.catalog, catalog_note = C.open_catalog(library.data_dir())
        self._index_on_save = False  # opened before its first save: indexed then, as opened
        self.home = LibraryPage(self.catalog, self.settings, self._remember)
        self.song = SongPage()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.song)
        self.updates = UpdateController(self)
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.updates.banner)  # above both pages: seen wherever the user is
        column.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.drop_hint = QLabel(translate("MainWindow", "Déposez le morceau ici"), self.stack)
        self.drop_hint.setObjectName("drop")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.hide()

        self._wire()
        self.updates.add_to(self.song.menu.menu())
        self.updates.add_to(self.home.menu_button.menu())
        self.lyrics = LyricsController(self)
        self.mixer = MixerController(self)
        self.song.panel.set_mode(self.settings.get("diagram_mode", "guitar"))
        self.song.panel.set_state(self.settings.get("diagram_panel", "full"), emit=False)
        if self.song.panel.state != "hidden":
            self._panel_restore = self.song.panel.state
        chords = self.song.chords
        chords.set_view(self.settings.get("song_chords_view", "all"))
        chords.set_mode(self.settings.get("song_chords_mode", "guitar"))
        chords.set_state(self.settings.get("song_chords_state", "compact"))
        self.song.sync_panel(False)
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(16)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start()
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(60)
        self.job_timer.timeout.connect(self._poll_job)
        self.download_timer = QTimer(self)
        self.download_timer.setInterval(100)
        self.download_timer.timeout.connect(self._poll_download)
        self.batch_timer = QTimer(self)
        self.batch_timer.setInterval(200)
        self.batch_timer.timeout.connect(self._poll_batch)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save)
        self._last_beat = None
        self._scroll_anim = QPropertyAnimation(self.song.scroll.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(180)
        self.home.start_scan()
        if catalog_note:
            _log(catalog_note)
            QTimer.singleShot(0, lambda: self._alert(catalog_note))

    # Wiring ------------------------------------------------------------------------------------
    def _wire(self) -> None:
        s = self.song
        self._button_actions: dict = {}
        for button in (s.status_button, s.banner_action):
            button.clicked.connect(lambda _=False, b=button: self._button_actions[b]())
        self.home.openRequested.connect(self.choose_file)
        self.home.linkRequested.connect(self.ask_link)
        self.home.batch_cancel.clicked.connect(self.cancel_batch)
        self.home.projectRequested.connect(self.open_project_file)
        self.home.audioChanged.connect(self._library_audio_changed)
        self.home.projectsReplaced.connect(self._projects_replaced)
        self.home.settingsRestored.connect(self._settings_restored)
        self.home.shortcutsRequested.connect(self.show_shortcuts)
        self.home.aboutRequested.connect(self.show_about)
        s.star.toggled.connect(self._star_toggled)
        s.home.clicked.connect(self.go_home)
        s.play.clicked.connect(self.toggle_play)
        s.back.clicked.connect(lambda: self.seek(0))
        s.waveform.seekRequested.connect(self.seek)
        s.grid.beatClicked.connect(self._beat_clicked)
        s.grid.editRequested.connect(self.edit_chord)
        s.grid.contextRequested.connect(self._grid_menu)
        s.undo.clicked.connect(self.undo)
        s.redo.clicked.connect(self.redo)
        s.rhythm_button.clicked.connect(self.open_rhythm)
        s.loop_a.clicked.connect(lambda: self.set_loop_mark(0))
        s.loop_b.clicked.connect(lambda: self.set_loop_mark(1))
        s.loop_button.clicked.connect(self.toggle_loop)
        s.speed.changed.connect(lambda i: self.player.set_rate(SPEEDS[i]))
        s.transpose.changed.connect(self._transpose_changed)
        s.audio_button.toggled.connect(self._audio_transpose_changed)
        s.capo.changed.connect(lambda v: self._view(capo=v))
        s.accidental_actions.triggered.connect(lambda a: self._view(accidentals=a.data()))
        s.detail_actions.triggered.connect(self._detail_changed)
        s.smooth_actions.triggered.connect(lambda a: self._view(min_beats=a.data()))
        s.volume.setValue(int(self.settings.get("volume", 1.0) * 100))
        s.volume.valueChanged.connect(self._volume_changed)
        s.panel.modeChanged.connect(self._diagram_mode_changed)
        s.panel.stateChanged.connect(self._diagram_state_changed)
        s.panel.followRequested.connect(self.follow_playback)
        s.diagrams_button.clicked.connect(self.toggle_diagrams)
        s.chords_button.clicked.connect(self.toggle_chords)
        s.chords.viewChanged.connect(lambda v: self._remember("song_chords_view", v))
        s.chords.modeChanged.connect(lambda m: self._remember("song_chords_mode", m))
        s.chords.stateChanged.connect(self._chords_state_changed)
        s.chords.chordChosen.connect(self._choose_chord)
        s.positions.changed.connect(self._positions_changed)

        export_menu = QMenu(self)
        export_menu.addAction(
            translate("MainWindow", "Texte (.txt)…"), lambda: self.export_as("txt")
        )
        export_menu.addAction(
            translate("MainWindow", "ChordPro (.cho)…"), lambda: self.export_as("cho")
        )
        export_menu.addAction(translate("MainWindow", "PDF (.pdf)…"), lambda: self.export_as("pdf"))
        export_menu.addSeparator()
        export_menu.addAction(
            translate("MainWindow", "Fiche des accords (PDF)…"), self.export_sheet
        )
        s.export.setMenu(export_menu)

        menu = QMenu(self)
        menu.addAction(
            translate("MainWindow", "Ouvrir un morceau…"),
            self.choose_file,
            QKeySequence.StandardKey.Open,
        )
        menu.addAction(translate("MainWindow", "Importer un lien…"), self.ask_link)
        menu.addAction(
            translate("MainWindow", "Enregistrer une copie du projet…"),
            self.save_as,
            QKeySequence.StandardKey.Save,
        )
        menu.addSeparator()
        analyze = menu.addMenu(translate("MainWindow", "Réanalyser avec"))
        for engine in engines.ENGINES.values():
            action = analyze.addAction(
                translate("Engines", engine.label), lambda e=engine.name: self.reanalyze(e)
            )
            action.setToolTip(translate("Engines", engine.description))
        analyze.setToolTipsVisible(True)
        compare = menu.addMenu(translate("MainWindow", "Comparer avec"))
        for engine in engines.ENGINES.values():
            compare.addAction(
                translate("Engines", engine.label), lambda e=engine.name: self.compare_with(e)
            )
        menu.addAction(translate("MainWindow", "Progressions répétées…"), self.show_progressions)
        menu.addAction(
            translate("MainWindow", "Pistes séparées et modèle de séparation…"),
            lambda: self.mixer.show_store(),
        )
        self.reset_action = menu.addAction(
            translate("MainWindow", "Effacer toutes les corrections"), self.reset_edits
        )
        menu.addSeparator()
        self.latin_action = QAction(
            translate("MainWindow", "Notes en Do, Ré, Mi"), self, checkable=True
        )
        self.latin_action.setChecked(bool(self.settings.get("latin")))
        self.latin_action.toggled.connect(self._latin_changed)
        menu.addAction(self.latin_action)
        self.bass_action = QAction(
            translate("MainWindow", "Afficher les basses (C/E)"), self, checkable=True
        )
        self.bass_action.setChecked(bool(self.settings.get("show_bass", True)))
        self.bass_action.toggled.connect(self._bass_changed)
        menu.addAction(self.bass_action)
        self.auto_lyrics_action = QAction(
            translate("MainWindow", "Rechercher automatiquement les paroles des morceaux"),
            self,
            checkable=True,
        )
        self.auto_lyrics_action.setChecked(self.settings.get("lyrics_auto") is True)
        self.auto_lyrics_action.setToolTip(
            translate(
                "MainWindow",
                "Pour un morceau sans paroles dont le titre et l'artiste sont connus : "
                "seuls le titre, l'artiste, l'album et la durée sont envoyés à LRCLIB "
                "(lrclib.net), jamais l'audio.",
            )
        )
        self.auto_lyrics_action.toggled.connect(lambda on: self.lyrics.allow_auto(on))
        menu.addAction(self.auto_lyrics_action)
        menu.setToolTipsVisible(True)
        menu.addSeparator()
        language_menu(menu, self.settings)
        menu.addAction(
            translate("MainWindow", "Raccourcis clavier"), self.show_shortcuts
        ).setObjectName("shortcuts")  # the updater puts its entries just above
        menu.addAction(translate("MainWindow", "À propos de LocalChords"), self.show_about)
        s.menu.setMenu(menu)

        def shortcut(keys, fn):
            QShortcut(
                QKeySequence(keys), self, activated=fn, context=Qt.ShortcutContext.WindowShortcut
            )

        shortcut("Space", self.toggle_play)
        shortcut("Left", lambda: self.step_beat(-1))
        shortcut("Right", lambda: self.step_beat(1))
        shortcut("Ctrl+Left", lambda: self.step_bar(-1))
        shortcut("Ctrl+Right", lambda: self.step_bar(1))
        shortcut("Home", lambda: self.seek(0))
        shortcut("End", lambda: self.seek(self.player.duration))
        shortcut("Return", self._enter)
        shortcut("Enter", self._enter)
        shortcut("E", self.edit_selected)
        shortcut("A", lambda: self.set_loop_mark(0))
        shortcut("B", lambda: self.set_loop_mark(1))
        shortcut("L", self.toggle_loop_key)
        shortcut("-", lambda: s.speed.step(-1))
        shortcut("+", lambda: s.speed.step(1))
        shortcut("=", lambda: s.speed.step(1))
        shortcut("Ctrl+Up", lambda: s.transpose.step(1))
        shortcut("Ctrl+Down", lambda: s.transpose.step(-1))
        shortcut("Ctrl+Z", self.undo)
        shortcut("Ctrl+Y", self.redo)
        shortcut("Ctrl+Shift+Z", self.redo)
        shortcut("Ctrl+O", self.choose_file)
        shortcut("Ctrl+S", self.save_as)
        shortcut("Ctrl+E", lambda: s.export.showMenu())
        shortcut("F1", self.show_shortcuts)
        shortcut("D", self.toggle_diagrams)
        shortcut("T", self.toggle_chords)
        shortcut("G", lambda: s.panel.step("guitar", 1))
        shortcut("Shift+G", lambda: s.panel.step("guitar", -1))
        shortcut("P", lambda: s.panel.step("piano", 1))
        shortcut("Shift+P", lambda: s.panel.step("piano", -1))
        shortcut("Escape", self.follow_playback)
        shortcut("Shift+D", self.toggle_pin)
        shortcut("K", lambda: self.lyrics.toggle_mode())
        shortcut("M", lambda: self.mixer.toggle_panel())
        shortcut("Shift+M", lambda: self.mixer.toggle_original())

    # Opening -----------------------------------------------------------------------------------
    def choose_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            translate("MainWindow", "Ouvrir un morceau"),
            "",
            translate(
                "MainWindow",
                "{audio_filter};;Projets LocalChords (*{extension});;Tous les fichiers (*)",
            ).format(audio_filter=AUDIO_FILTER, extension=EXTENSION),
        )
        self.open_paths([Path(p) for p in paths])

    def open_paths(self, paths: list[Path]) -> None:
        """One file opens; several go through analysis in the background, for later."""
        if len(paths) == 1:
            self.open_path(paths[0])
        elif paths:
            self.start_batch(paths)

    def open_path(self, path: Path) -> None:
        """A recording or a project, whichever it is."""
        if path.suffix.lower() == EXTENSION:
            self.open_project_file(path)
        else:
            self.open_audio(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_hint.setGeometry(self.stack.rect().adjusted(16, 16, -16, -16))
            self.drop_hint.raise_()
            self.drop_hint.show()

    def dragLeaveEvent(self, event):
        self.drop_hint.hide()

    def dropEvent(self, event):
        self.drop_hint.hide()
        self.open_paths([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])

    def ask_link(self) -> None:
        url, ok = QInputDialog.getText(
            self,
            translate("MainWindow", "Importer un lien"),
            translate(
                "MainWindow",
                "Adresse de la vidéo ou du morceau.\nN'importez que des contenus que vous "
                "avez le droit de télécharger.",
            ),
        )
        if ok and url.strip():
            self.import_link(url.strip())

    def import_link(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            self._alert(
                translate(
                    "MainWindow", "Ce n'est pas une adresse web valide (http:// ou https://)."
                )
            )
            return
        try:
            known = self.catalog.find_url(url)
        except Exception:  # noqa: BLE001 - an index that fails to read: download as before
            known = None
        if known:
            file = library.data_dir() / "projects" / known["file"]
            if file.exists():
                self.open_project_file(file)
                return
        folder = library.data_dir() / "downloads"
        folder.mkdir(exist_ok=True)
        self.download_job = worker.start_download(url, folder)
        dialog = QProgressDialog(
            translate("MainWindow", "Connexion au site…"),
            translate("MainWindow", "Annuler"),
            0,
            1000,
            self,
        )
        dialog.setWindowTitle(translate("MainWindow", "Importer un lien"))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        self.download_dialog = dialog
        dialog.canceled.connect(self._cancel_download)
        self.download_timer.start()

    def _cancel_download(self) -> None:
        self.download_timer.stop()
        if self.download_job:
            self.download_job.cancel()
            self.download_job = None

    def _poll_download(self) -> None:
        if not self.download_job:
            self.download_timer.stop()
            return
        for message in self.download_job.poll():
            if message[0] == "progress":
                self.download_dialog.setValue(int(message[1] * 1000))
                self.download_dialog.setLabelText(message[2])
            elif message[0] in ("downloaded", "error"):
                self.download_timer.stop()
                self.download_job.cancel()
                self.download_job = None
                self.download_dialog.close()
                if message[0] == "error":
                    self._alert(message[1])
                else:
                    self.pending_source_url = message[2]
                    self.pending_info = message[3] if len(message) > 3 else None
                    self.open_audio(Path(message[1]))
                return

    # Batch -------------------------------------------------------------------------------------
    def start_batch(self, paths: list[Path]) -> None:
        if self.batch_job:  # already running: these join the queue
            self.batch_queue.extend(paths)
            self.batch_total += len(paths)
            return
        self.batch_queue = list(paths)
        self.batch_total = len(paths)
        self.batch_done = 0
        self.batch_errors: list[str] = []
        self.home.batch_box.show()
        self.home.batch_cancel.show()
        self.batch_timer.start()
        self._next_batch()

    def _next_batch(self) -> None:
        engine = self.settings.get("engine", engines.DEFAULT_ENGINE)
        while self.batch_queue:
            path = self.batch_queue.pop(0)
            try:
                project, saved, known = self._project_for(path)
            except (audio.AudioError, OSError, ProjectError) as exc:
                self.batch_errors.append(f"{path.name} : {exc}")
                self.batch_done += 1
                continue
            if known:
                self.batch_done += 1
                continue
            self.batch_current = (project, saved)
            self.batch_job = worker.start(path, engine)
            self.home.batch_text.setText(
                translate(
                    "MainWindow", "Analyse par lots : {number} sur {batch_total}, « {name} »"
                ).format(number=self.batch_done + 1, batch_total=self.batch_total, name=path.name)
            )
            return
        self.batch_job = None
        self.batch_timer.stop()
        text = translate(
            "MainWindow", "Analyse par lots terminée : %n morceau(x).", None, self.batch_total
        )
        if self.batch_errors:
            text = translate("MainWindow", "{done} Problèmes : {problems}").format(
                done=text, problems=" ; ".join(self.batch_errors)
            )
        self.home.batch_text.setText(text)
        self.home.batch_cancel.hide()
        self.home.refresh()

    def _poll_batch(self) -> None:
        if not self.batch_job:
            return
        for message in self.batch_job.poll():
            if message[0] == "waveform":
                self.batch_current[0].audio["waveform"] = message[1]
                self.batch_current[0].audio["duration"] = message[2]
            elif message[0] in ("done", "error"):
                project, saved = self.batch_current
                # A file there now means the song was opened meanwhile: that one has the say.
                if message[0] == "done" and not saved.exists():
                    project.replace_analysis(message[1])
                    try:
                        project.save(saved)
                        self.catalog.store(saved, project)
                    except OSError as exc:
                        self.batch_errors.append(str(exc))
                    except C.CatalogError as exc:
                        _log(str(exc))
                elif message[0] == "error":
                    self.batch_errors.append(f"{project.audio['title']} : {message[1]}")
                self.batch_job.cancel()
                self.batch_done += 1
                self.home.refresh()
                self._next_batch()
                return

    def cancel_batch(self) -> None:
        self.batch_queue = []
        self.batch_timer.stop()
        if self.batch_job:
            self.batch_job.cancel()
            self.batch_job = None
        self.home.batch_box.hide()
        self.home.refresh()

    def _project_for(self, path: Path) -> tuple[Project, Path, bool]:
        """(project, its file, whether it was already analyzed) for a recording."""
        source_url, self.pending_source_url = self.pending_source_url, None
        site, self.pending_info = self.pending_info, None
        fingerprint = audio.fingerprint(path)
        saved = library.project_path(fingerprint)
        if saved.exists():
            try:
                project = Project.load(saved)
                project.audio["path"] = str(path)
                return project, saved, True
            except ProjectError as exc:
                # A new analysis replaces it, but the file is kept aside: it may hold corrections
                # and lyrics, or come from a newer version.
                aside = saved.with_name(f"{saved.stem}-{int(time.time())}.illisible")
                try:
                    saved.replace(aside)
                    _log(f"{exc} Gardé sous {aside.name}.")
                except OSError:
                    _log(f"{exc} Impossible de le mettre de côté.")
        info = audio.metadata(path)
        site_year = (site or {}).get("release_year")
        # Lyrics found beside the recording or in its tags: on this computer, so used at once.
        found = L.find_local(path, info.get("lyrics") or "")
        # Who and what it is: the site's music fields, else the tags, else the name. Stored once:
        # a project already known keeps what it has, corrections included.
        who = identify.from_info(site) if site else identify.from_file(info, path.stem)
        project = Project(
            {
                "path": str(path),
                "title": who["title"] or path.stem,
                "artist": who["artist"],
                "album": who["album"],
                "duration": float(info["duration"] or (site or {}).get("duration") or 0.0),
                "fingerprint": fingerprint,
                "waveform": None,
                "source_url": source_url,
                "size": path.stat().st_size,
                "genre": info.get("genre") or (site or {}).get("genre") or "",
                "year": C.year_of(info.get("date")) or C.year_of(site_year),
                "identity": {
                    k: who[k] for k in ("how", "sure", "video_title", "channel") if k in who
                },
            },
            {"beats": [], "segments": []},
            lyrics=L.new(*found) if found else None,
        )
        return project, saved, False

    def open_audio(self, path: Path) -> None:
        """A song already analyzed comes back as it was left; a new one gets analyzed."""
        self.flush()
        try:
            project, saved, known = self._project_for(path)
        except audio.AudioError as exc:
            self._alert(str(exc))
            return
        except OSError as exc:
            self._alert(
                translate("MainWindow", "Impossible d'ouvrir « {name} » : {reason}").format(
                    name=path.name, reason=exc.strerror or exc
                )
            )
            return
        self._show_project(project, saved)
        if known:
            self.save()
        else:
            self.start_analysis(path, self.settings.get("engine", engines.DEFAULT_ENGINE))

    def open_project_file(self, path: Path) -> None:
        self.flush()
        try:
            project = Project.load(path)
        except ProjectError as exc:
            self._alert(str(exc))
            return
        self._show_project(project, path)

    def _show_project(self, project: Project, file: Path) -> None:
        self._stop_job()
        self.player.pause()
        self.player.load(np.zeros((0, 2), dtype=np.float32))
        self.audio_ready = False
        self.project = project
        self.project_file = file
        self.pinned_at = None
        self._index_on_save = False
        if file.exists():
            self._index(file, project, opened=True)
        else:
            self._index_on_save = True
        s0 = self.song.star
        s0.blockSignals(True)
        s0.setChecked(self._favorite(file))
        s0.blockSignals(False)
        self._show_star()
        project.view["latin"] = bool(self.settings.get("latin"))
        project.view["show_bass"] = bool(self.settings.get("show_bass", True))
        s = self.song
        s.title.set_full_text(project.audio.get("title") or "")
        s.subtitle.set_full_text(project.audio.get("artist") or "")
        s.subtitle.setVisible(bool(project.audio.get("artist")))
        s.waveform.set_peaks(decode_waveform(project.audio.get("waveform")), project.duration)
        s.banner.hide()
        self._set_loop(None)
        self.loop_marks = [None, None]
        # The view comes back as it was left.
        s.transpose.set_value(int(project.view["transpose"]))
        s.capo.set_value(int(project.view["capo"]))
        view = project.view
        detail = "analysis" if view["show_numerals"] else ("simple" if view["simplify"] else "full")
        for group, value in (
            (s.detail_actions, detail),
            (s.accidental_actions, view["accidentals"]),
            (s.smooth_actions, view["min_beats"]),
        ):
            for action in group.actions():
                action.setChecked(action.data() == value)
        s.speed.set_value(SPEEDS.index(1.0))
        self.player.set_rate(1.0)
        s.audio_button.blockSignals(True)
        s.audio_button.setChecked(bool(project.view.get("transpose_audio")))
        s.audio_button.blockSignals(False)
        s._show_audio_state(s.audio_button.isChecked())
        self._apply_pitch()
        s.scroll.verticalScrollBar().setValue(0)
        self.stack.setCurrentWidget(s)
        self.setWindowTitle(
            translate("MainWindow", "{title} : LocalChords").format(
                title=project.audio.get("title") or ""
            )
        )
        self._content_changed(save=False)
        self.mixer.song_opened()
        self._load_audio(library.audio_file(project.audio))

    def _load_audio(self, path: Path) -> None:
        self._set_transport_enabled(False)
        if not path.is_file():
            self._banner(
                translate(
                    "MainWindow",
                    "Le fichier audio est introuvable : {path}. La grille reste consultable.",
                ).format(path=path),
                translate("MainWindow", "Localiser le fichier…"),
                self.locate_audio,
            )
            return
        self.audio_token = self.loader.load(path, self.player.sr)

    def _audio_loaded(self, token, y, error) -> None:
        if token is not self.audio_token or self.project is None:
            return
        if error:
            self._banner(error, translate("MainWindow", "Localiser le fichier…"), self.locate_audio)
            return
        self.player.load(y)
        self.audio_ready = True
        duration = len(y) / self.player.sr
        # The file's own header can be wrong or absent; what decoded is the truth.
        if abs(self.project.duration - duration) > 0.5 or not self.project.duration:
            self.project.audio["duration"] = round(duration, 3)
            self.project._touch()
            self._content_changed(save=False)
        if not len(self.project.audio.get("waveform") or ""):
            self.song.waveform.set_peaks(audio.peaks(y), duration)
        self._set_transport_enabled(True)
        self.mixer.audio_loaded()

    def locate_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, translate("MainWindow", "Localiser le fichier audio"), "", AUDIO_FILTER
        )
        if not path or self.project is None:
            return
        chosen = Path(path)
        known = self.project.audio.get("fingerprint")
        try:
            same = audio.fingerprint(chosen) == known
        except OSError:
            same = False
        if known and not same:
            answer = QMessageBox.question(
                self,
                translate("MainWindow", "Autre fichier ?"),
                translate(
                    "MainWindow",
                    "Ce fichier n'est pas celui qui a été analysé : la grille risque de ne "
                    "pas lui correspondre. L'utiliser quand même ?",
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.project.audio["path"] = str(chosen)
        self.song.banner.hide()
        self._load_audio(chosen)
        self.save()

    def _set_transport_enabled(self, on: bool) -> None:
        s = self.song
        for w in (s.play, s.back, s.loop_a, s.loop_b, s.loop_button, s.speed):
            w.setEnabled(on)

    def go_home(self) -> None:
        self.flush()
        self.player.pause()
        self.stack.setCurrentWidget(self.home)
        self.home.refresh()
        self.setWindowTitle("LocalChords")

    # Analysis ----------------------------------------------------------------------------------
    def start_analysis(self, path: Path, engine: str) -> None:
        self._stop_job()
        self.job = worker.start(path, engine)
        self.job_stage = 0
        self.job_path, self.job_engine = path, engine
        self.job_timer.start()
        s = self.song
        s.progress_bar.setValue(0)
        s.progress_bar.show()
        if not self.project or not self.project.analysis["segments"]:
            s.middle.setCurrentWidget(s.status_page)
            s.status_text.setText(translate("MainWindow", "Analyse en cours…"))
            s.status_detail.setText(translate("MainWindow", "Préparation…"))
            s.status_button.setText(translate("MainWindow", "Annuler"))
            s.status_button.show()
            self._retarget(s.status_button, self.cancel_analysis)
        else:
            self._banner(
                translate("MainWindow", "Nouvelle analyse en cours…"),
                translate("MainWindow", "Annuler"),
                self.cancel_analysis,
            )

    def _retarget(self, button: QPushButton, fn) -> None:
        self._button_actions[button] = fn
        # Cancelling is not the screen's main action: amber stays for what moves you forward.
        button.setObjectName("" if fn == self.cancel_analysis else "primary")
        theme.restyle(button)

    def _stop_job(self) -> None:
        self.job_timer.stop() if hasattr(self, "job_timer") else None
        if self.job:
            self.job.cancel()
            self.job = None
        self.compare_engine = None
        self.song.progress_bar.hide()

    def cancel_analysis(self) -> None:
        self._stop_job()
        self.song.banner.hide()
        if self.project and not self.project.analysis["segments"]:
            self._show_status(
                translate("MainWindow", "Analyse annulée"),
                translate("MainWindow", "Le morceau reste écoutable."),
                translate("MainWindow", "Relancer l'analyse"),
                lambda: self.start_analysis(self.job_path, self.job_engine),
            )

    def _show_status(self, title: str, detail: str, button: str, fn) -> None:
        s = self.song
        s.middle.setCurrentWidget(s.status_page)
        s.status_text.setText(title)
        s.status_detail.setText(detail)
        s.status_button.setText(button)
        s.status_button.show()
        self._retarget(s.status_button, fn)

    def _poll_job(self) -> None:
        if not self.job:
            self.job_timer.stop()
            return
        messages = self.job.poll()
        if not messages:
            # A stage gives no news until it ends: creep on, so a long one doesn't look stuck.
            bar = self.song.progress_bar
            ceiling = min(self.job_stage + 200, 970)
            bar.setValue(bar.value() + max((ceiling - bar.value()) // 90, 0))
        for message in messages:
            kind = message[0]
            if kind == "progress":
                self.job_stage = int(message[1] * 1000)
                self.song.progress_bar.setValue(max(self.job_stage, self.song.progress_bar.value()))
                self.song.status_detail.setText(message[2])
            elif kind == "waveform" and self.project and self.project.analysis["segments"]:
                pass  # a further analysis of a song already drawn
            elif kind == "waveform" and self.project:
                self.project.audio["waveform"] = message[1]
                self.project.audio["duration"] = message[2]
                self.project._touch()
                self.song.waveform.set_peaks(decode_waveform(message[1]), message[2])
            elif kind == "done":
                self._analysis_done(message[1])
                return
            elif kind == "error":
                self._analysis_failed(message[1], message[2])
                return

    def _analysis_done(self, analysis: dict) -> None:
        engine, comparing = self.job_engine, self.compare_engine
        self._stop_job()
        self.song.banner.hide()
        if self.project is None:
            return
        analysis["engine"]["requested"] = engine
        if comparing and not self._keep_compared(engine, analysis):
            return
        self.project.replace_analysis(analysis)
        self.song.middle.setCurrentWidget(self.song.scroll)
        self._content_changed()
        self.flush()

    def _analysis_failed(self, text: str, details: str) -> None:
        self._stop_job()
        self.song.banner.hide()
        if details:
            _log(details)
        if self.project and not self.project.analysis["segments"]:
            self._show_status(
                translate("MainWindow", "Analyse impossible"),
                text,
                translate("MainWindow", "Réessayer"),
                lambda: self.start_analysis(self.job_path, self.job_engine),
            )
        else:
            self._alert(text)

    def compare_with(self, engine: str) -> None:
        """Run another engine beside the current grid, then let the user choose."""
        if not self.project or not self.project.analysis["segments"]:
            return
        path = library.audio_file(self.project.audio)
        if not path.is_file():
            self._alert(
                translate("MainWindow", "Le fichier audio est introuvable : localisez-le d'abord.")
            )
            return
        self.start_analysis(path, engine)
        self.compare_engine = engine

    def _keep_compared(self, engine: str, analysis: dict) -> bool:
        """Show how the two grids differ; True to adopt the new one."""
        a = self.project.agreement_with(analysis)
        label = translate("Engines", engines.ENGINES[engine].label)
        spots = [fmt_time(t) for t in _spaced(a["differences"])][:12]
        text = translate(
            "MainWindow",
            "Le moteur « {label} » est d'accord avec la grille actuelle sur "
            "{exact:.0%} des temps, et sur {triads:.0%} si l'on ne regarde que les "
            "accords de base.",
        ).format(label=label, exact=a["exact"], triads=a["triads"])
        if spots:
            text += "\n\n" + translate("MainWindow", "Passages à écouter : {spots}.").format(
                spots=", ".join(spots)
            )
        text += "\n\n" + translate(
            "MainWindow", "Vos corrections sont conservées dans les deux cas."
        )
        box = QMessageBox(self)
        box.setWindowTitle(translate("MainWindow", "Comparer deux moteurs"))
        box.setText(text)
        keep = box.addButton(
            translate("MainWindow", "Garder la grille actuelle"), QMessageBox.ButtonRole.RejectRole
        )
        box.addButton(
            translate("MainWindow", "Utiliser « {label} »").format(label=label),
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.exec()
        return box.clickedButton() is not keep

    def show_progressions(self) -> None:
        if not self.project:
            return
        ProgressionsDialog(self.project, self.seek, self).exec()

    def reanalyze(self, engine: str) -> None:
        if not self.project:
            return
        path = library.audio_file(self.project.audio)
        if not path.is_file():
            self._alert(
                translate("MainWindow", "Le fichier audio est introuvable : localisez-le d'abord.")
            )
            return
        self.settings["engine"] = engine
        library.save_settings(self.settings)
        self.start_analysis(path, engine)

    # What the song page shows ------------------------------------------------------------------
    def _content_changed(self, *, save: bool = True) -> None:
        """Everything derived from the project, recomputed after any change to it."""
        project = self.project
        if project is None:
            return
        s = self.song
        has_grid = bool(project.analysis["segments"])
        s.grid.set_project(project) if s.grid.project is not project else s.grid.refresh()
        s.waveform.set_project(project if has_grid else None)
        s.waveform.invalidate()
        if has_grid and self.job is None:
            s.middle.setCurrentWidget(self.lyrics.middle_page())
        elif not has_grid and self.job is None:
            path = library.audio_file(project.audio)
            self.job_path, self.job_engine = (
                path,
                self.settings.get("engine", engines.DEFAULT_ENGINE),
            )
            self._show_status(
                translate("MainWindow", "Ce morceau n'est pas encore analysé"),
                "",
                translate("MainWindow", "Lancer l'analyse"),
                lambda: self.start_analysis(self.job_path, self.job_engine),
            )
        # Nothing to say about the song's key or tempo before there is an analysis.
        for widget in (s.key_button, s.rhythm_button, s.undo, s.redo, s.export):
            widget.setVisible(has_grid)
        s.sync_panel(has_grid and self.job is None)
        if self._positions_of is not project:
            s.positions.load(project.view.get("positions"))  # before: loading is not an edit
            self._positions_of = project
        self._update_song_chords()
        self._update_facts()
        self._update_loop_display()
        self.lyrics.refresh(has_grid)
        s.undo.setEnabled(project.can_undo)
        s.redo.setEnabled(project.can_redo)
        self._last_beat = None
        self._tick()
        if save and has_grid:
            self.save_timer.start()

    def _shown(self, segment) -> voicings.Shown | None:
        """A segment as the diagrams show it: exactly as the grid writes it."""
        project = self.project
        view = project.view
        key = project.key()
        return voicings.describe(
            segment.chord,
            segment.bass,
            key=key["label"] if key else None,
            transpose=int(view["transpose"]),
            capo=int(view["capo"]),
            accidentals=view["accidentals"],
            simplify=bool(view["simplify"]),
            show_bass=bool(view["show_bass"]),
            latin=bool(view.get("latin")),
        )

    def _bar_text(self, beat: int) -> str:
        place = self.project.bar_position(beat)
        return (
            translate("MainWindow", "mesure {bar}").format(bar=place[0])
            if place and place[0]
            else "introduction"
        )

    def _update_song_chords(self) -> None:
        """Every chord once, in the order it first comes: worked out here, not during playback."""
        project = self.project
        segments = project.segments()
        grid = project.grid()
        self._shown_list = [self._shown(x) for x in segments]
        seen, items = set(), []
        for segment, shown in zip(segments, self._shown_list, strict=True):
            if shown is None or chord_key(shown) in seen:
                continue
            seen.add(chord_key(shown))
            start = max(0, segment.start_beat)
            items.append(Item(shown, grid[start], self._bar_text(segment.start_beat)))
        self.song.chords.set_all(items)
        self._upcoming_at = None
        self._sync_selection()

    def _update_upcoming(self, index: int | None, beat: int) -> None:
        """The chord playing and the next ones; new cards only when the chord changes."""
        s = self.song
        project = self.project
        segments = project.segments()
        if len(self._shown_list) != len(segments):
            return
        here = self._shown_list[index] if index is not None else None
        key = chord_key(here) if here is not None else None
        if key != s.chords.current:
            s.chords.set_current(key)
        start = index if index is not None else (0 if beat < 0 else len(segments))
        if start == self._upcoming_at:
            return
        self._upcoming_at = start
        grid = project.grid()
        items = []
        for i in range(start, len(segments)):
            shown = self._shown_list[i]
            if shown is None:
                continue
            first = max(0, segments[i].start_beat)
            place = (
                translate("MainWindow", "en cours")
                if i == index
                else self._bar_text(segments[i].start_beat)
            )
            items.append(Item(shown, grid[first], place, current=i == index))
            if len(items) == UPCOMING:
                break
        s.chords.set_upcoming(items)

    def _sync_selection(self) -> None:
        """The card of the chord the panel is pinned to, outlined."""
        key = None
        if self.project is not None and self.pinned_at is not None:
            beat = self.project.beat_at(self.pinned_at)
            segments = self.project.segments()
            i = next((i for i, x in enumerate(segments) if x.start_beat <= beat < x.end_beat), None)
            if i is not None and i < len(self._shown_list) and self._shown_list[i] is not None:
                key = chord_key(self._shown_list[i])
        if key != self.song.chords.selected:
            self.song.chords.set_selected(key)

    def _choose_chord(self, time: float) -> None:
        """A card was clicked: the panel shows that chord, playback stays where it is."""
        self.pinned_at = time
        self._update_panel()

    def _positions_changed(self) -> None:
        if self.project is not None and self._positions_of is self.project:
            self.project.view["positions"] = dict(self.song.positions.chosen)
            if self.project.analysis["segments"]:
                self.save_timer.start()

    def toggle_chords(self) -> None:
        s = self.song
        if s.chords_button.isVisible():
            s.chords.toggle()

    def _chords_state_changed(self, state: str) -> None:
        self._remember("song_chords_state", state)
        has_grid = bool(self.project and self.project.analysis["segments"])
        self.song.sync_panel(has_grid and self.job is None)

    def _remember(self, name: str, value) -> None:
        self.settings[name] = value
        library.save_settings(self.settings)

    def _update_facts(self) -> None:
        project = self.project
        s = self.song
        key = project.key()
        latin = bool(project.view.get("latin"))
        shift = project.sounding_shift()
        # What sounds; with a capo, the shapes the hands play are named apart.
        label = key["label"] if key else None
        short = key_name(label, int(project.view["transpose"]), latin=latin)
        text = translate("MainWindow", "Tonalité : {short}").format(short=short)
        if key and project.view["capo"]:
            text += " · " + translate("MainWindow", "formes {key}").format(
                key=key_name(label, shift, latin=latin)
            )
        s.set_fact(s.key_button, text, short)
        menu = QMenu(self)
        if key:
            s.key_button.setToolTip(self._key_tooltip(key))
            for candidate in key["candidates"]:
                action = menu.addAction(
                    key_name(candidate, shift, latin=latin),
                    lambda c=candidate: self._set_key(c),
                )
                action.setCheckable(True)
                action.setChecked(candidate == key["label"])
            menu.addSeparator()
            all_keys = menu.addMenu(translate("MainWindow", "Autre tonalité"))
            for mode in ("maj", "min"):
                for pc in range(12):
                    label = f"{spell_tonic(pc, mode)}:{mode}"
                    all_keys.addAction(
                        key_name(label, shift, latin=latin), lambda c=label: self._set_key(c)
                    )
            if project.edits.get("key"):
                menu.addAction(
                    translate("MainWindow", "Revenir à l'estimation"), lambda: self._set_key(None)
                )
        s.key_button.setMenu(menu)
        tempo = project.tempo()
        meter = project.meter()
        bpm = f"{tempo['bpm']:.0f} BPM" if tempo["bpm"] else "— BPM"
        unsure = []
        fit = project.analysis.get("grid_fit")
        if not project.edits["grid"] and fit is not None and fit < 0.7:
            unsure.append(
                translate("MainWindow", "le tempo semble varier : la grille est approximative")
            )
        if not meter.get("edited") and float(meter.get("confidence", 1.0)) < 0.25:
            unsure.append(translate("MainWindow", "mesure incertaine"))
        mark = "  ?" if unsure else ""
        s.set_fact(
            s.rhythm_button,
            translate("MainWindow", "{bpm} · {beats_per_bar} temps{mark}").format(
                bpm=bpm, beats_per_bar=meter["beats_per_bar"], mark=mark
            ),
            bpm + mark,
        )
        tip = translate("MainWindow", "Corriger le tempo, la mesure ou le décalage de la grille")
        s.rhythm_button.setToolTip(
            translate("MainWindow", "{tip}\nÀ vérifier : {unsure}.").format(
                tip=tip, unsure=", ".join(unsure)
            )
            if unsure
            else tip
        )

    def _key_tooltip(self, key: dict) -> str:
        project = self.project
        latin = bool(project.view.get("latin"))
        shift = project.sounding_shift()
        others = [key_name(c, shift, latin=latin) for c in key["candidates"] if c != key["label"]]
        origin = (
            translate("MainWindow", "choisie par vous")
            if key["source"] == "given"
            else translate("MainWindow", "estimée d'après les accords")
        )
        text = translate("MainWindow", "Tonalité {origin}.").format(origin=origin)
        if others:
            text += translate("MainWindow", "\nAutres lectures possibles : {others}.").format(
                others=", ".join(others)
            )
        regions = project.key_regions()
        if len(regions) > 1:
            grid = project.grid()
            parts = [
                f"{key_name(r['label'], shift, latin=latin)} ({fmt_time(grid[r['start_beat']])})"
                for r in regions
            ]
            text += "\n" + translate("MainWindow", "Changements de tonalité : {changes}.").format(
                changes=" → ".join(parts)
            )
        return text

    def _view(self, **values) -> None:
        if self.project:
            self.project.set_view(**values)
            self._content_changed()

    def _detail_changed(self, action) -> None:
        value = action.data()
        self._view(simplify=value == "simple", show_numerals=value == "analysis")

    def _transpose_changed(self, value: int) -> None:
        self._view(transpose=value)
        self._apply_pitch()

    def _audio_transpose_changed(self, on: bool) -> None:
        self._view(transpose_audio=on)
        self._apply_pitch()

    def _apply_pitch(self) -> None:
        view = self.project.view if self.project else {}
        self.player.set_pitch(int(view.get("transpose", 0)) if view.get("transpose_audio") else 0)

    def _latin_changed(self, on: bool) -> None:
        self.settings["latin"] = on
        library.save_settings(self.settings)
        self._view(latin=on)

    def _bass_changed(self, on: bool) -> None:
        self.settings["show_bass"] = on
        library.save_settings(self.settings)
        self._view(show_bass=on)

    def _set_key(self, key: str | None) -> None:
        self.project.set_key(key)
        self._content_changed()

    def _volume_changed(self, value: int) -> None:
        self.settings["volume"] = value / 100
        if not self.muted:
            self.player.volume = value / 100
        library.save_settings(self.settings)

    # Playback ----------------------------------------------------------------------------------
    def toggle_play(self) -> None:
        if not self.audio_ready or self.stack.currentWidget() is not self.song:
            return
        self.player.toggle()
        if self.player.last_error:
            self._alert(self.player.last_error)
            self.player.playing = False
        self._update_play_icon()
        if self.player.playing and self.pinned_at is not None:
            self.follow_playback()

    def _update_play_icon(self) -> None:
        s = self.song
        playing = self.player.playing
        s.play.setIcon(theme.icon("pause" if playing else "play", theme.ON_ACCENT, 22))
        s.play.setAccessibleName(
            translate("MainWindow", "Pause") if playing else translate("MainWindow", "Lecture")
        )

    def seek(self, seconds: float) -> None:
        self.player.seek(seconds)
        self._last_beat = None
        self._tick()

    def _beat_clicked(self, beat: int) -> None:
        self.pinned_at = self.project.grid()[beat]
        self.seek(self.pinned_at)
        self._update_panel()

    def toggle_pin(self) -> None:
        """The keyboard's click: pin the chord under the playhead, or follow playback again."""
        if self.pinned_at is not None:
            self.follow_playback()
        elif self.project and self.project.grid():
            self._beat_clicked(max(0, self.project.beat_at(self.player.position)))

    def step_beat(self, delta: int) -> None:
        if not self.project or not self.project.grid():
            return
        grid = self.project.grid()
        here = self.project.beat_at(self.player.position)
        target = max(0, min(len(grid) - 1, here + delta))
        if self.pinned_at is not None:
            self.pinned_at = grid[target]
        self.seek(grid[target])
        self.song.grid.anchor = target
        self.song.grid.set_selection(target, target)

    def step_bar(self, delta: int) -> None:
        if not self.project or not self.project.grid():
            return
        here = self.project.beat_at(self.player.position)
        starts = [b.beats for b in self.project.bars()]
        firsts = [next((c for c in cells if c is not None), None) for cells in starts]
        firsts = [f for f in firsts if f is not None]
        now = max((i for i, f in enumerate(firsts) if f <= here), default=0)
        target = firsts[max(0, min(len(firsts) - 1, now + delta))] if firsts else 0
        if self.pinned_at is not None:
            self.pinned_at = self.project.grid()[target]
        self.seek(self.project.grid()[target])
        self.song.grid.anchor = target
        self.song.grid.set_selection(target, target)

    def _tick(self) -> None:
        if self.stack.currentWidget() is not self.song or not self.project:
            return
        position = self.player.position
        s = self.song
        s.grid.set_playhead(position)
        s.waveform.set_position(position)
        if s.play.accessibleName() == translate("MainWindow", "Pause") and not self.player.playing:
            self._update_play_icon()
        s.time.setText(f"{fmt_time(position)} / {fmt_time(self.project.duration)}")
        beat = self.project.beat_at(position)
        self.lyrics.tick(position, beat)
        if beat == self._last_beat:
            return
        self._last_beat = beat
        self._update_now(beat)
        if self.player.playing:
            self._follow(beat)

    def _update_now(self, beat: int) -> None:
        project = self.project
        s = self.song
        place = ""
        if beat >= 0 and project.analysis["segments"]:
            position = project.bar_position(beat)
            if position and position[0]:
                place = translate("MainWindow", "mesure {bar} · temps {beat}").format(
                    bar=position[0], beat=position[1]
                )
            elif position:
                place = "introduction"
        s.place.setText(place)
        now = next_ = ""
        segments = project.segments()
        if segments:
            index = next(
                (i for i, x in enumerate(segments) if x.start_beat <= beat < x.end_beat), None
            )
            if index is None and beat < 0:
                next_ = export.chord_text(project, segments[0])
            elif index is not None:
                now = export.chord_text(project, segments[index])
                if index + 1 < len(segments):
                    next_ = export.chord_text(project, segments[index + 1])
        s.now.setText(now or "—")
        s.next.setText(f"→ {next_}" if next_ else "")
        if segments:
            self._update_upcoming(index, beat)
        self._update_panel(beat)

    # Diagrams ----------------------------------------------------------------------------------
    def _update_panel(self, beat: int | None = None) -> None:
        """The diagrams show the chord playing, or the pinned one, exactly as the grid writes it."""
        project = self.project
        s = self.song
        self._sync_selection()
        if project is None or s.panel.state == "hidden" or not project.analysis["segments"]:
            return
        segments = project.segments()
        pinned = self.pinned_at is not None
        if pinned:
            beat = project.beat_at(self.pinned_at)
        elif beat is None:
            beat = project.beat_at(self.player.position)
        segment = next((x for x in segments if x.start_beat <= beat < x.end_beat), None)
        if pinned and segment is None:  # the grid changed under it
            self.pinned_at, pinned = None, False
            self._sync_selection()
            beat = project.beat_at(self.player.position)
            segment = next((x for x in segments if x.start_beat <= beat < x.end_beat), None)
        status = translate("MainWindow", "Suit la lecture")
        if pinned:
            place = project.bar_position(beat)
            status = (
                translate("MainWindow", "Épinglé : mesure {bar}").format(bar=place[0])
                if place and place[0]
                else translate("MainWindow", "Épinglé")
            )
        elif segment is None and beat < 0 and segments:
            segment, status = segments[0], translate("MainWindow", "Premier accord du morceau")
        shown = self._shown(segment) if segment is not None else None
        empty = "N.C." if segment is not None else "—"
        s.panel.show_chord(shown, status, pinned, empty)

    def follow_playback(self) -> None:
        if self.pinned_at is None:
            return
        self.pinned_at = None
        self._update_panel()

    def toggle_diagrams(self) -> None:
        s = self.song
        if not s.diagrams_button.isVisible():
            return
        s.panel.set_state(self._panel_restore if s.panel.state == "hidden" else "hidden")

    def _diagram_state_changed(self, state: str) -> None:
        if state != "hidden":
            self._panel_restore = state
        self.settings["diagram_panel"] = state
        library.save_settings(self.settings)
        has_grid = bool(self.project and self.project.analysis["segments"])
        self.song.sync_panel(has_grid and self.job is None)
        self._update_panel()

    def _diagram_mode_changed(self, mode: str) -> None:
        self.settings["diagram_mode"] = mode
        library.save_settings(self.settings)

    def _follow(self, beat: int) -> None:
        """Keep the current line, and the one after it, in view."""
        s = self.song
        rect = s.grid.rect_of(beat)
        if rect is None:
            return
        bar = s.scroll.verticalScrollBar()
        view = s.scroll.viewport().height()
        row = s.grid.row_h + 10
        top, bottom = rect.top() - 16, rect.bottom() + row + 16
        target = bar.value()
        if bottom > bar.value() + view or top < bar.value():
            target = (
                min(top, max(bottom - view, 0))
                if bottom - top > view
                else top - max(0, (view - (bottom - top)) // 3)
            )
        if target != bar.value():
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(bar.value())
            self._scroll_anim.setEndValue(max(0, target))
            self._scroll_anim.start()

    # Loop --------------------------------------------------------------------------------------
    def set_loop_mark(self, which: int) -> None:
        if not self.audio_ready or not self.project or not self.project.grid():
            return
        grid = self.project.grid()
        beat = max(self.project.beat_at(self.player.position), 0)
        # Snapped to the beat: a loop that starts on a beat stays in time with itself.
        time = (
            grid[beat]
            if which == 0
            else (grid[beat + 1] if beat + 1 < len(grid) else self.project.duration)
        )
        self.loop_marks[which] = time
        a, b = self.loop_marks
        if a is not None and b is not None and b > a:
            self._set_loop((a, b))
        self._update_loop_display()

    def toggle_loop(self) -> None:
        self.toggle_loop_key()

    def toggle_loop_key(self) -> None:
        if not self.audio_ready or not self.project or not self.project.grid():
            self.song.loop_button.setChecked(False)
            return
        if self.player.loop:
            self._set_loop(None)
            return
        selection = self.song.grid.selection
        grid = self.project.grid()
        if selection:
            start = grid[selection[0]]
            end = grid[selection[1] + 1] if selection[1] + 1 < len(grid) else self.project.duration
            self._set_loop((start, end))
        elif (
            all(m is not None for m in self.loop_marks) and self.loop_marks[1] > self.loop_marks[0]
        ):
            self._set_loop(tuple(self.loop_marks))
        else:
            # Nothing chosen: the bar being played is the natural thing to loop.
            beat = max(self.project.beat_at(self.player.position), 0)
            for bar in self.project.bars():
                cells = [c for c in bar.beats if c is not None]
                if cells and cells[0] <= beat <= cells[-1]:
                    end = (
                        grid[cells[-1] + 1] if cells[-1] + 1 < len(grid) else self.project.duration
                    )
                    self._set_loop((grid[cells[0]], end))
                    break

    def _set_loop(self, loop: tuple[float, float] | None) -> None:
        self.player.set_loop(*(loop or (None, None)))
        if loop:
            self.loop_marks = [loop[0], loop[1]]
            position = self.player.position
            if not loop[0] <= position < loop[1]:
                self.seek(loop[0])
        else:
            self.loop_marks = [None, None]
        self._update_loop_display()

    def _update_loop_display(self) -> None:
        s = self.song
        loop = self.player.loop
        seconds = (loop[0] / self.player.sr, loop[1] / self.player.sr) if loop else None
        s.loop_button.setChecked(bool(loop))
        s.waveform.set_loop(seconds)
        a, b = self.loop_marks
        s.loop_a.setText(f"A {fmt_time(a)}" if a is not None else "A")
        s.loop_b.setText(f"B {fmt_time(b)}" if b is not None else "B")
        beats = None
        if seconds and self.project and self.project.grid():
            first = max(self.project.beat_at(seconds[0] + 1e-3), 0)
            last = max(self.project.beat_at(seconds[1] - 0.01), first)
            beats = (first, last)
        s.grid.set_loop(beats)

    # Corrections -------------------------------------------------------------------------------
    def edit_selected(self) -> None:
        if self.lyrics.tap():  # Enter times the chosen line while the lyrics are being synced
            return
        if not self.project or not self.project.grid():
            return
        selection = self.song.grid.selection
        if selection is None:
            beat = max(self.project.beat_at(self.player.position), 0)
            selection = (beat, beat)
        self.edit_chord(*selection)

    def edit_chord(self, first: int, last: int) -> None:
        editor = ChordEditor(self.project, first, last, self)
        if not editor.exec() or editor.result_label is None:
            return
        self.apply_chord(*editor.result_span, editor.result_label, editor.result_bass)

    def apply_chord(self, first: int, last: int, label: str, bass: str | None) -> None:
        grid = self.project.grid()
        end = grid[last + 1] if last + 1 < len(grid) else self.project.duration
        self.project.set_chord(grid[first], end, label, bass)
        self._content_changed()

    def _grid_menu(self, beat: int, where) -> None:
        project = self.project
        menu = QMenu(self)
        selection = self.song.grid.selection or (beat, beat)
        menu.addAction(
            translate("MainWindow", "Corriger l'accord…"), lambda: self.edit_chord(*selection)
        )
        segment = project.segment_at_beat(beat)
        if segment and segment.candidates:
            alternatives = menu.addMenu(translate("MainWindow", "Remplacer par"))
            key = project.key()
            for label in segment.candidates[:6]:
                if label == segment.chord or parse(label) is None:
                    continue
                text = symbol(
                    label,
                    key=key["label"] if key else None,
                    semitones=project.sounding_shift(),
                    accidentals=project.view["accidentals"],
                    latin=bool(project.view.get("latin")),
                )
                alternatives.addAction(
                    text,
                    lambda c=label: self.apply_chord(
                        segment.start_beat, segment.end_beat - 1, c, None
                    ),
                )
        menu.addSeparator()
        menu.addAction(
            translate("MainWindow", "Boucler la sélection"),
            self.toggle_loop_key if not self.player.loop else self._reloop,
        )
        menu.addAction(
            translate("MainWindow", "La première mesure commence ici"),
            lambda: self._downbeat_here(beat),
        )
        menu.exec(where)

    def _reloop(self) -> None:
        self._set_loop(None)
        self.toggle_loop_key()

    def _downbeat_here(self, beat: int) -> None:
        per_bar = int(self.project.meter()["beats_per_bar"])
        self.project.set_meter(per_bar, beat % per_bar)
        self._content_changed()

    def undo(self) -> None:
        if self.project and self.project.can_undo:
            self.project.undo()
            self._content_changed()

    def redo(self) -> None:
        if self.project and self.project.can_redo:
            self.project.redo()
            self._content_changed()

    def reset_edits(self) -> None:
        if not self.project:
            return
        answer = QMessageBox.question(
            self,
            translate("MainWindow", "Effacer les corrections"),
            translate(
                "MainWindow",
                "Revenir à l'analyse d'origine ? Vous pourrez encore annuler avec Ctrl + Z.",
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.project.reset_edits()
            self._content_changed()

    def open_rhythm(self) -> None:
        if not self.project:
            return
        dialog = RhythmDialog(self.project, self)
        dialog.changed.connect(self._content_changed)
        dialog.exec()

    # Saving and exporting ----------------------------------------------------------------------
    def save(self) -> None:
        if not self.project or not self.project_file or not self.project.analysis["segments"]:
            return
        try:
            self.project.save(self.project_file)
        except OSError as exc:
            self._alert(
                translate("MainWindow", "La sauvegarde a échoué : {reason}").format(
                    reason=exc.strerror or exc
                )
            )
            return
        self._index(self.project_file, self.project, opened=self._index_on_save)
        self._index_on_save = False

    # The library -------------------------------------------------------------------------------
    def _index(self, file: Path, project: Project, *, opened: bool = False) -> None:
        """The library learns of a save; its own failure never stands in the song's way."""
        try:
            self.catalog.store(file, project, opened=opened)
        except (C.CatalogError, OSError) as exc:
            _log(str(exc))

    def _favorite(self, file: Path) -> bool:
        try:
            song = self.catalog.song(file.stem)
        except Exception:  # noqa: BLE001
            song = None
        return bool(song and song["favorite"])

    def _show_star(self) -> None:
        star = self.song.star
        on = star.isChecked()
        star.setIcon(
            theme.icon("star", theme.ACCENT) if on else theme.icon("star_line", theme.TEXT_2)
        )
        star.setToolTip(
            translate("MainWindow", "Retirer des favoris")
            if on
            else translate("MainWindow", "Ajouter aux favoris")
        )

    def _star_toggled(self, on: bool) -> None:
        file = self.project_file
        if file is None:
            return
        if not file.exists():  # not saved yet: the first save indexes it
            self.save()
        try:
            if self.catalog.song(file.stem) is None:
                self.catalog.store(file, self.project, opened=True)
            self.catalog.set_favorite([file.stem], on)
        except (C.CatalogError, OSError) as exc:
            self.song.star.blockSignals(True)
            self.song.star.setChecked(not on)
            self.song.star.blockSignals(False)
            self._alert(
                translate("MainWindow", "Le favori n'a pas pu être enregistré : {exc}").format(
                    exc=exc
                )
            )
        self._show_star()

    def _enter(self) -> None:
        if self.stack.currentWidget() is self.home:
            self.home.open_current()
        else:
            self.edit_selected()

    def _library_audio_changed(self, file: Path, info: dict) -> None:
        """A kept copy made or dropped, a file found again, from the library: the song in memory
        follows, so that its next save does not undo it."""
        if self.project is not None and self.project_file == file:
            self.project.audio["path"] = info.get("path", self.project.audio.get("path"))
            if info.get("kept"):
                self.project.audio["kept"] = info["kept"]
            else:
                self.project.audio.pop("kept", None)

    def _projects_replaced(self, files: list) -> None:
        """Project files deleted or restored over: the song in memory is not saved over them."""
        if self.project_file is not None and self.project_file in files:
            self.project_file = None

    def _settings_restored(self) -> None:
        self.settings.clear()
        self.settings.update(library.load_settings())
        for action, key, default in (
            (self.latin_action, "latin", False),
            (self.bass_action, "show_bass", True),
        ):
            action.setChecked(bool(self.settings.get(key, default)))
        self.auto_lyrics_action.setChecked(self.settings.get("lyrics_auto") is True)
        self.updates.sync()
        self.home.refresh()

    def flush(self) -> None:
        """Save now whatever the timer was about to."""
        if self.save_timer.isActive():
            self.save_timer.stop()
        self.save()

    def save_as(self) -> None:
        if not self.project or not self.project.analysis["segments"]:
            return
        suggested = (self.project.audio.get("title") or "projet") + EXTENSION
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("MainWindow", "Enregistrer une copie du projet"),
            suggested,
            translate("MainWindow", "Projet LocalChords (*{extension})").format(
                extension=EXTENSION
            ),
        )
        if path:
            try:
                self.project.save(Path(path), shared=True)  # leaves the program: no catalog lyrics
            except OSError as exc:
                self._alert(
                    translate("MainWindow", "Enregistrement impossible : {reason}").format(
                        reason=exc.strerror or exc
                    )
                )

    def export_as(self, kind: str) -> None:
        if not self.project or not self.project.analysis["segments"]:
            self._alert(translate("MainWindow", "Il n'y a pas encore de grille à exporter."))
            return
        titles = {"txt": translate("MainWindow", "Texte"), "cho": "ChordPro", "pdf": "PDF"}
        suggested = (
            f"{self.project.audio.get('title') or translate('MainWindow', 'accords')}.{kind}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("MainWindow", "Exporter en {format}").format(format=titles[kind]),
            suggested,
            f"{titles[kind]} (*.{kind})",
        )
        if path:
            self.export_to(Path(path), kind)

    def export_to(self, path: Path, kind: str) -> None:
        try:
            if kind == "pdf":
                write_pdf(self.project, path)
            else:
                text = (
                    export.to_text(self.project)
                    if kind == "txt"
                    else export.to_chordpro(self.project)
                )
                path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self._alert(
                translate("MainWindow", "Export impossible : {reason}").format(
                    reason=exc.strerror or exc
                )
            )

    def export_sheet(self) -> None:
        """Every chord of the song with its diagrams, on paper."""
        if not self.project or not self.project.analysis["segments"]:
            self._alert(translate("MainWindow", "Il n'y a pas encore de grille à exporter."))
            return
        chords = self.song.chords
        dialog = SheetDialog(chords.mode, bool(self.settings.get("sheet_grid", False)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, grid = dialog.mode, dialog.grid.isChecked()
        self._remember("sheet_grid", grid)
        suggested = translate("MainWindow", "{title} - accords.pdf").format(
            title=self.project.audio.get("title") or "morceau"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, translate("MainWindow", "Exporter la fiche des accords"), suggested, "PDF (*.pdf)"
        )
        if path:
            self.export_sheet_to(Path(path), mode, grid)

    def export_sheet_to(self, path: Path, mode: str, grid: bool) -> None:
        try:
            write_chord_sheet(
                self.project, path, self.song.chords.all_items, mode, grid, self.song.positions
            )
        except OSError as exc:
            self._alert(
                translate("MainWindow", "Export impossible : {reason}").format(
                    reason=exc.strerror or exc
                )
            )

    # Messages ----------------------------------------------------------------------------------
    def _alert(self, text: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("LocalChords")
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.exec()

    def _banner(self, text: str, action: str, fn) -> None:
        s = self.song
        s.banner_text.setText(text)
        s.banner_action.setText(action)
        self._retarget(s.banner_action, fn)
        s.banner.show()

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            translate("MainWindow", "À propos de LocalChords"),
            translate(
                "MainWindow",
                "<b>LocalChords {version}</b><br>Grille d'accords locale et "
                "synchronisée.<br><br>Reconnaissance : chordotomy, lv-chordia, Beat "
                "This!, librosa.<br>Interface : Qt (PySide6). Audio : PyAV (FFmpeg), "
                "PortAudio.<br>Le détail des licences est dans LICENCES-TIERS.md, dans "
                "le dossier _internal.<br><br>L'audio n'est jamais envoyé nulle part. "
                "Les accords sont extraits automatiquement : vérifiez-les à l'oreille.",
            ).format(version=__version__),
        )

    def closeEvent(self, event):
        self.flush()
        self._stop_job()
        self._cancel_download()
        self.cancel_batch()
        self.lyrics.cancel()
        self.mixer.close()
        self.updates.stop()
        self.player.pause()
        self.player.close_device()
        library.save_settings(self.settings)
        self.catalog.close()
        super().closeEvent(event)


def _spaced(times: list[float], gap: float = 8.0) -> list[float]:
    """The start of each passage in a list of times: one mention per stretch."""
    out: list[float] = []
    for t in times:
        if not out or t - out[-1] >= gap:
            out.append(t)
    return out


class ProgressionsDialog(QDialog):
    """What comes back in the song. A click goes to its first appearance."""

    def __init__(self, project: Project, seek, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("MainWindow", "Progressions répétées"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        found = project.progressions()
        if not found:
            layout.addWidget(
                QLabel(
                    translate("MainWindow", "Aucune suite d'accords ne se répète dans ce morceau.")
                )
            )
        grid = project.grid()
        for item in found:
            chords = "  ".join(export.chord_text(project, s) for s in item["symbols"])
            b = QPushButton(f"{chords}     × {item['count']}")
            b.setObjectName("recent")
            b.setToolTip(translate("MainWindow", "Aller à sa première apparition"))
            at = grid[item["start_beats"][0]]
            b.clicked.connect(lambda _=False, t=at: (seek(t), self.accept()))
            layout.addWidget(b)
        note = QLabel(
            translate(
                "MainWindow", "Repérées d'après les accords affichés : à vérifier à l'oreille."
            )
        )
        note.setObjectName("caption")
        layout.addWidget(note)


def _log(text: str) -> None:
    try:
        with (library.data_dir() / "log.txt").open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def app_instance() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(theme.QSS)
    app.setApplicationName("LocalChords")
    app.setFont(theme.app_font(13))
    # The interface's language, with Qt's own buttons (Yes/No, Cancel) in it too.
    settings = library.load_settings()
    if i18n.migrate(settings, library.existing_user()):
        library.save_settings(settings)
    i18n.install(app, i18n.resolve(settings["language"]))
    return app
