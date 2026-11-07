"""The window: a home screen to bring a song in, a song screen to read and play it."""

from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PySide6.QtCore import (
    QLibraryInfo,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    QTranslator,
    Signal,
)
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDialog,
    QFileDialog,
    QFrame,
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

from .. import __version__, audio, engines, export, library, voicings, worker
from ..chords import key_name, parse, spell_tonic, symbol
from ..player import Player, device_sample_rate
from ..project import EXTENSION, Project, ProjectError, decode_waveform
from . import theme
from .diagrams import ChordPanel, Positions
from .dialogs import ChordEditor, RhythmDialog, SheetDialog, ShortcutsDialog
from .grid import ChordGrid
from .pdf import write_chord_sheet, write_pdf
from .songchords import UPCOMING, Item, SongChords, chord_key
from .waveform import Waveform
from .widgets import ElidedLabel, Stepper, fmt_time

AUDIO_FILTER = "Audio (" + " ".join(f"*{e}" for e in audio.AUDIO_EXTENSIONS) + ")"
SIDE_PANEL_WIDTH = 1280
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
                self.finished.emit(token, None, "Mémoire insuffisante pour charger ce morceau.")

        threading.Thread(target=run, daemon=True).start()
        return token


class GridScroll(QScrollArea):
    """Tells the grid how much room it has, for it to choose its layout."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.widget().set_view_height(self.viewport().height())


class HomePage(QWidget):
    openRequested = Signal()
    linkRequested = Signal()
    projectRequested = Signal(Path)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(720)
        column.setMinimumWidth(320)
        layout = QVBoxLayout(column)
        layout.setSpacing(16)
        title = QLabel("LocalChords")
        title.setObjectName("h1")
        lead = QLabel(
            "Glissez un morceau dans cette fenêtre : ses accords apparaissent en grille et "
            "défilent avec la lecture."
        )
        lead.setObjectName("muted")
        lead.setWordWrap(True)
        self.open_button = QPushButton("Ouvrir un morceau…")
        self.open_button.setObjectName("primary")
        self.open_button.setToolTip("Ctrl + O")
        self.open_button.clicked.connect(self.openRequested)
        place = "Tout reste sur votre ordinateur."
        if library.portable_dir() == library.data_dir():
            place = "Mode portable : tout reste dans le dossier Data, à côté du programme."
        formats = QLabel(f"MP3, WAV, FLAC, M4A, OGG, OPUS… {place}")
        formats.setObjectName("caption")
        self.link_button = QPushButton("Importer un lien…")
        self.link_button.setToolTip(
            "YouTube et autres sites, pour les contenus que vous avez le droit de télécharger"
        )
        self.link_button.clicked.connect(self.linkRequested)
        row = QHBoxLayout()
        row.addWidget(self.open_button)
        row.addWidget(self.link_button)
        row.addStretch()
        layout.addWidget(title)
        layout.addWidget(lead)
        layout.addLayout(row)
        layout.addWidget(formats)
        self.batch_box = QWidget()
        batch_row = QHBoxLayout(self.batch_box)
        batch_row.setContentsMargins(0, 0, 0, 0)
        self.batch_text = QLabel()
        self.batch_text.setObjectName("muted")
        self.batch_cancel = QPushButton("Arrêter")
        batch_row.addWidget(self.batch_text, 1)
        batch_row.addWidget(self.batch_cancel)
        self.batch_box.hide()
        layout.addWidget(self.batch_box)
        self.recent_title = QLabel("Morceaux récents")
        self.recent_title.setObjectName("h2")
        layout.addSpacing(16)
        layout.addWidget(self.recent_title)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(6)
        holder = QWidget()
        holder.setLayout(self.recent_box)
        self.scroll = QScrollArea()
        self.scroll.setWidget(holder)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMaximumHeight(420)
        layout.addWidget(self.scroll)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(column, 3)
        wrap.addStretch(1)
        outer.addLayout(wrap)
        outer.addStretch(2)
        self.refresh()

    def refresh(self) -> None:
        while self.recent_box.count():
            item = self.recent_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = library.recent()
        self.recent_title.setVisible(bool(items))
        self.scroll.setVisible(bool(items))
        for path, info in items:
            title = info.get("title") or Path(info.get("path", "")).stem
            artist = info.get("artist")
            duration = fmt_time(float(info.get("duration") or 0))
            text = f"{title}    —    {artist}" if artist else title
            source = info.get("path", "")
            tail = f"    {duration}"
            if not Path(source).exists():
                tail += "    · audio introuvable"
            b = QPushButton()
            b.setObjectName("recent")
            # A long title is shortened rather than widening the window; the tooltip has it whole.
            b.setText(b.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 520) + tail)
            b.setToolTip(f"{text}\n{source}")
            b.setMinimumWidth(1)
            b.clicked.connect(lambda _=False, p=path: self.projectRequested.emit(p))
            self.recent_box.addWidget(b)
        self.recent_box.addStretch()


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
        row = QHBoxLayout(top)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        self.home = QToolButton()
        self.home.setIcon(theme.icon("home"))
        self.home.setToolTip("Retour à l'accueil")
        self.home.setAccessibleName("Accueil")
        row.addWidget(self.home)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = ElidedLabel()
        self.title.setObjectName("title")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle = ElidedLabel()
        self.subtitle.setObjectName("caption")
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 3)
        # Now and next: what to play without reading the grid.
        self.now = QLabel("—")
        self.now.setStyleSheet(f"font-size: 30px; font-weight: 700; color: {theme.ACCENT};")
        self.now.setAccessibleName("Accord en cours")
        self.now.setMinimumWidth(96)
        self.now.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.next = QLabel("")
        self.next.setStyleSheet(f"font-size: 18px; color: {theme.TEXT_2};")
        self.next.setAccessibleName("Accord suivant")
        self.next.setMinimumWidth(80)
        row.addWidget(self.now)
        row.addWidget(self.next)
        row.addStretch(2)
        self.key_button = QToolButton()
        self.key_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.key_button.setAccessibleName("Tonalité")
        self.rhythm_button = QPushButton()
        self.rhythm_button.setAccessibleName("Tempo et mesure")
        self.rhythm_button.setToolTip("Corriger le tempo, la mesure ou le décalage de la grille")
        self.undo = QToolButton()
        self.undo.setIcon(theme.icon("undo"))
        self.undo.setToolTip("Annuler la dernière correction (Ctrl + Z)")
        self.undo.setAccessibleName("Annuler")
        self.redo = QToolButton()
        self.redo.setIcon(theme.icon("redo"))
        self.redo.setToolTip("Rétablir (Ctrl + Y)")
        self.redo.setAccessibleName("Rétablir")
        self.export = QToolButton()
        self.export.setText("Exporter")
        self.export.setIcon(theme.icon("export"))
        self.export.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.diagrams_button = QToolButton()
        self.diagrams_button.setIcon(theme.icon("diagram"))
        self.diagrams_button.setCheckable(True)
        self.diagrams_button.setToolTip("Diagrammes de guitare et de piano (D)")
        self.diagrams_button.setAccessibleName("Diagrammes d'accords")
        self.chords_button = QToolButton()
        self.chords_button.setIcon(theme.icon("cards"))
        self.chords_button.setCheckable(True)
        self.chords_button.setToolTip("Accords du morceau : tous, ou ceux à venir (T)")
        self.chords_button.setAccessibleName("Accords du morceau")
        self.menu = QToolButton()
        self.menu.setIcon(theme.icon("menu"))
        self.menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu.setToolTip("Plus d'options")
        self.menu.setAccessibleName("Plus d'options")
        for w in (
            self.key_button,
            self.rhythm_button,
            self.undo,
            self.redo,
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
        self.banner_close.setAccessibleName("Fermer le message")
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
        self.back.setToolTip("Revenir au début (Début)")
        self.back.setAccessibleName("Revenir au début")
        self.play = QToolButton()
        self.play.setObjectName("play")
        self.play.setIcon(theme.icon("play", theme.ON_ACCENT, 22))
        self.play.setIconSize(self.play.iconSize() * 1.3)
        self.play.setToolTip("Lecture / pause (Espace)")
        self.play.setAccessibleName("Lecture")
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

        self.loop_button = QPushButton(" Boucle")
        self.loop_button.setIcon(theme.icon("loop", size=16))
        self.loop_button.setCheckable(True)
        self.loop_button.setToolTip("Boucler la sélection, ou arrêter la boucle (L)")
        self.loop_a = QPushButton("A")
        self.loop_a.setToolTip("Début de boucle à la position actuelle (A)")
        self.loop_a.setAccessibleName("Début de boucle")
        self.loop_b = QPushButton("B")
        self.loop_b.setToolTip("Fin de boucle à la position actuelle (B)")
        self.loop_b.setAccessibleName("Fin de boucle")
        for w in (self.loop_a, self.loop_b, self.loop_button):
            controls.addWidget(w)

        self.speed = Stepper(
            "Vitesse",
            0,
            len(SPEEDS) - 1,
            SPEEDS.index(1.0),
            lambda i: f"{round(SPEEDS[i] * 100)} %",
            "Ralentir sans changer la hauteur (- / +)",
        )
        controls.addWidget(self.speed)
        self.transpose = Stepper(
            "Transposer",
            -12,
            12,
            0,
            lambda v: f"{v:+d}" if v else "0",
            "Transposer la grille, en demi-tons (Ctrl + ↑ / ↓).",
        )
        controls.addWidget(self.transpose)
        # Right next to the transposition, so whether the sound follows is never a guess.
        self.audio_button = QPushButton()
        self.audio_button.setIcon(theme.icon("volume", size=16))
        self.audio_button.setCheckable(True)
        self.audio_button.setAccessibleName("Transposer également l'audio")
        self.audio_button.toggled.connect(self._show_audio_state)
        # Its label must not set the window's minimum width: it gives way first (adapt_to_width).
        self.audio_button.setMinimumWidth(36)
        self._show_audio_state(False)
        controls.addWidget(self.audio_button)
        self.capo = Stepper(
            "Capo", 0, 11, 0, str, "Case du capodastre : la grille montre les formes à jouer."
        )
        controls.addWidget(self.capo)

        # How the chords are written: asked for rarely, kept one click away.
        self.display = QToolButton()
        self.display.setText("Affichage")
        self.display.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.display.setToolTip("Niveau de détail, altérations et accords courts")
        self.display.setMenu(QMenu(self.display))
        self.detail_actions = self._choices(
            "Accords",
            (
                ("Complets", "full"),
                ("Simplifiés (accords de base)", "simple"),
                ("Complets, avec analyse des degrés", "analysis"),
            ),
        )
        self.accidental_actions = self._choices(
            "Altérations",
            (("Selon la tonalité", "auto"), ("Dièses (♯)", "sharps"), ("Bémols (♭)", "flats")),
        )
        self.smooth_actions = self._choices(
            "Accords très courts",
            (
                ("Tous les afficher", 1),
                ("Ignorer sous 2 temps", 2),
                ("Ignorer sous 3 temps", 3),
                ("Ignorer sous 4 temps", 4),
            ),
        )
        controls.addWidget(self.display)

        self.volume_icon = QLabel()
        self.volume_icon.setPixmap(theme.pixmap("volume", theme.TEXT_2, 16))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(64)
        self.volume.setAccessibleName("Volume")
        self.volume.setToolTip("Volume")
        controls.addWidget(self.volume_icon)
        controls.addWidget(self.volume)
        layout.addWidget(bottom)
        self.adapt_to_width(1360)

    def _show_audio_state(self, on: bool) -> None:
        self._audio_text = " Son transposé" if on else " Son d'origine"
        self.audio_button.setText(self._audio_text if self._audio_wide else "")
        self.audio_button.setToolTip(
            "Transposer également l'audio : activé. Cliquer pour n'entendre que l'original."
            if on
            else "Transposer également l'audio : désactivé, seule la grille change. "
            "Cliquer pour que le son suive la transposition, à la même vitesse."
        )

    _audio_wide = True

    def adapt_to_width(self, width: int) -> None:
        """A tiling window manager can make the window narrower than its minimum, so what is
        rarely needed gives way first; all of it stays on the keyboard."""
        self._audio_wide = width >= 1240  # narrower, the icon and its highlight say it
        self.audio_button.setText(self._audio_text if self._audio_wide else "")
        for widget in (self.volume, self.volume_icon):
            widget.setVisible(width >= 1120)
        for widget in (self.loop_a, self.loop_b):
            widget.setVisible(width >= 960)
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
        self.home = HomePage()
        self.song = SongPage()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.song)
        self.setCentralWidget(self.stack)
        self.drop_hint = QLabel("Déposez le morceau ici", self.stack)
        self.drop_hint.setObjectName("drop")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.hide()

        self._wire()
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
        export_menu.addAction("Texte (.txt)…", lambda: self.export_as("txt"))
        export_menu.addAction("ChordPro (.cho)…", lambda: self.export_as("cho"))
        export_menu.addAction("PDF (.pdf)…", lambda: self.export_as("pdf"))
        export_menu.addSeparator()
        export_menu.addAction("Fiche des accords (PDF)…", self.export_sheet)
        s.export.setMenu(export_menu)

        menu = QMenu(self)
        menu.addAction("Ouvrir un morceau…", self.choose_file, QKeySequence.StandardKey.Open)
        menu.addAction("Importer un lien…", self.ask_link)
        menu.addAction(
            "Enregistrer une copie du projet…", self.save_as, QKeySequence.StandardKey.Save
        )
        menu.addSeparator()
        analyze = menu.addMenu("Réanalyser avec")
        for engine in engines.ENGINES.values():
            action = analyze.addAction(engine.label, lambda e=engine.name: self.reanalyze(e))
            action.setToolTip(engine.description)
        analyze.setToolTipsVisible(True)
        compare = menu.addMenu("Comparer avec")
        for engine in engines.ENGINES.values():
            compare.addAction(engine.label, lambda e=engine.name: self.compare_with(e))
        menu.addAction("Progressions répétées…", self.show_progressions)
        self.reset_action = menu.addAction("Effacer toutes les corrections", self.reset_edits)
        menu.addSeparator()
        self.latin_action = QAction("Notes en Do, Ré, Mi", self, checkable=True)
        self.latin_action.setChecked(bool(self.settings.get("latin")))
        self.latin_action.toggled.connect(self._latin_changed)
        menu.addAction(self.latin_action)
        self.bass_action = QAction("Afficher les basses (C/E)", self, checkable=True)
        self.bass_action.setChecked(bool(self.settings.get("show_bass", True)))
        self.bass_action.toggled.connect(self._bass_changed)
        menu.addAction(self.bass_action)
        menu.addSeparator()
        menu.addAction("Raccourcis clavier", self.show_shortcuts)
        menu.addAction("À propos de LocalChords", self.show_about)
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
        shortcut("Return", self.edit_selected)
        shortcut("Enter", self.edit_selected)
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

    # Opening -----------------------------------------------------------------------------------
    def choose_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Ouvrir un morceau",
            "",
            f"{AUDIO_FILTER};;Projets LocalChords (*{EXTENSION});;Tous les fichiers (*)",
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
            "Importer un lien",
            "Adresse de la vidéo ou du morceau.\n"
            "N'importez que des contenus que vous avez le droit de télécharger.",
        )
        if ok and url.strip():
            self.import_link(url.strip())

    def import_link(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            self._alert("Ce n'est pas une adresse web valide (http:// ou https://).")
            return
        folder = library.data_dir() / "downloads"
        folder.mkdir(exist_ok=True)
        self.download_job = worker.start_download(url, folder)
        dialog = QProgressDialog("Connexion au site…", "Annuler", 0, 1000, self)
        dialog.setWindowTitle("Importer un lien")
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
                f"Analyse par lots : {self.batch_done + 1} sur {self.batch_total}, « {path.name} »"
            )
            return
        self.batch_job = None
        self.batch_timer.stop()
        text = f"Analyse par lots terminée : {self.batch_total} morceaux."
        if self.batch_errors:
            text += " Problèmes : " + " ; ".join(self.batch_errors)
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
                    except OSError as exc:
                        self.batch_errors.append(str(exc))
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
        fingerprint = audio.fingerprint(path)
        saved = library.project_path(fingerprint)
        if saved.exists():
            try:
                project = Project.load(saved)
                project.audio["path"] = str(path)
                return project, saved, True
            except ProjectError:
                pass  # a damaged save doesn't stop a new analysis, which replaces it
        info = audio.metadata(path)
        project = Project(
            {
                "path": str(path),
                "title": info["title"],
                "artist": info["artist"],
                "duration": float(info["duration"] or 0.0),
                "fingerprint": fingerprint,
                "waveform": None,
                "source_url": source_url,
            },
            {"beats": [], "segments": []},
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
            self._alert(f"Impossible d'ouvrir « {path.name} » : {exc.strerror or exc}")
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
        self.setWindowTitle(f"{project.audio.get('title') or ''} : LocalChords")
        self._content_changed(save=False)
        self._load_audio(Path(project.audio.get("path", "")))

    def _load_audio(self, path: Path) -> None:
        self._set_transport_enabled(False)
        if not path.is_file():
            self._banner(
                f"Le fichier audio est introuvable : {path}. La grille reste consultable.",
                "Localiser le fichier…",
                self.locate_audio,
            )
            return
        self.audio_token = self.loader.load(path, self.player.sr)

    def _audio_loaded(self, token, y, error) -> None:
        if token is not self.audio_token or self.project is None:
            return
        if error:
            self._banner(error, "Localiser le fichier…", self.locate_audio)
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

    def locate_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Localiser le fichier audio", "", AUDIO_FILTER)
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
                "Autre fichier ?",
                "Ce fichier n'est pas celui qui a été analysé : la grille risque de ne pas lui "
                "correspondre. L'utiliser quand même ?",
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
            s.status_text.setText("Analyse en cours…")
            s.status_detail.setText("Préparation…")
            s.status_button.setText("Annuler")
            s.status_button.show()
            self._retarget(s.status_button, self.cancel_analysis)
        else:
            self._banner("Nouvelle analyse en cours…", "Annuler", self.cancel_analysis)

    def _retarget(self, button: QPushButton, fn) -> None:
        self._button_actions[button] = fn

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
                "Analyse annulée",
                "Le morceau reste écoutable.",
                "Relancer l'analyse",
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
                "Analyse impossible",
                text,
                "Réessayer",
                lambda: self.start_analysis(self.job_path, self.job_engine),
            )
        else:
            self._alert(text)

    def compare_with(self, engine: str) -> None:
        """Run another engine beside the current grid, then let the user choose."""
        if not self.project or not self.project.analysis["segments"]:
            return
        path = Path(self.project.audio.get("path", ""))
        if not path.is_file():
            self._alert("Le fichier audio est introuvable : localisez-le d'abord.")
            return
        self.start_analysis(path, engine)
        self.compare_engine = engine

    def _keep_compared(self, engine: str, analysis: dict) -> bool:
        """Show how the two grids differ; True to adopt the new one."""
        a = self.project.agreement_with(analysis)
        label = engines.ENGINES[engine].label
        spots = [fmt_time(t) for t in _spaced(a["differences"])][:12]
        text = (
            f"Le moteur « {label} » est d'accord avec la grille actuelle sur "
            f"{a['exact']:.0%} des temps, et sur {a['triads']:.0%} si l'on ne regarde "
            "que les accords de base."
        )
        if spots:
            text += "\n\nPassages à écouter : " + ", ".join(spots) + "."
        text += "\n\nVos corrections sont conservées dans les deux cas."
        box = QMessageBox(self)
        box.setWindowTitle("Comparer deux moteurs")
        box.setText(text)
        keep = box.addButton("Garder la grille actuelle", QMessageBox.ButtonRole.RejectRole)
        box.addButton(f"Utiliser « {label} »", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        return box.clickedButton() is not keep

    def show_progressions(self) -> None:
        if not self.project:
            return
        ProgressionsDialog(self.project, self.seek, self).exec()

    def reanalyze(self, engine: str) -> None:
        if not self.project:
            return
        path = Path(self.project.audio.get("path", ""))
        if not path.is_file():
            self._alert("Le fichier audio est introuvable : localisez-le d'abord.")
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
            s.middle.setCurrentWidget(s.scroll)
        elif not has_grid and self.job is None:
            path = Path(project.audio.get("path", ""))
            self.job_path, self.job_engine = (
                path,
                self.settings.get("engine", engines.DEFAULT_ENGINE),
            )
            self._show_status(
                "Ce morceau n'est pas encore analysé",
                "",
                "Lancer l'analyse",
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
        return f"mesure {place[0]}" if place and place[0] else "introduction"

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
            place = "en cours" if i == index else self._bar_text(segments[i].start_beat)
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
        s.key_button.setText(
            f"Tonalité : {key_name(key['label'] if key else None, shift, latin=latin)}"
        )
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
            all_keys = menu.addMenu("Autre tonalité")
            for mode in ("maj", "min"):
                for pc in range(12):
                    label = f"{spell_tonic(pc, mode)}:{mode}"
                    all_keys.addAction(
                        key_name(label, shift, latin=latin), lambda c=label: self._set_key(c)
                    )
            if project.edits.get("key"):
                menu.addAction("Revenir à l'estimation", lambda: self._set_key(None))
        s.key_button.setMenu(menu)
        tempo = project.tempo()
        meter = project.meter()
        bpm = f"{tempo['bpm']:.0f} BPM" if tempo["bpm"] else "— BPM"
        unsure = []
        fit = project.analysis.get("grid_fit")
        if not project.edits["grid"] and fit is not None and fit < 0.7:
            unsure.append("le tempo semble varier : la grille est approximative")
        if not meter.get("edited") and float(meter.get("confidence", 1.0)) < 0.25:
            unsure.append("mesure incertaine")
        mark = "  ?" if unsure else ""
        s.rhythm_button.setText(f"{bpm} · {meter['beats_per_bar']} temps{mark}")
        tip = "Corriger le tempo, la mesure ou le décalage de la grille"
        s.rhythm_button.setToolTip(f"{tip}\nÀ vérifier : {', '.join(unsure)}." if unsure else tip)

    def _key_tooltip(self, key: dict) -> str:
        project = self.project
        latin = bool(project.view.get("latin"))
        shift = project.sounding_shift()
        others = [key_name(c, shift, latin=latin) for c in key["candidates"] if c != key["label"]]
        origin = "choisie par vous" if key["source"] == "given" else "estimée d'après les accords"
        text = f"Tonalité {origin}."
        if others:
            text += f"\nAutres lectures possibles : {', '.join(others)}."
        regions = project.key_regions()
        if len(regions) > 1:
            grid = project.grid()
            parts = [
                f"{key_name(r['label'], shift, latin=latin)} ({fmt_time(grid[r['start_beat']])})"
                for r in regions
            ]
            text += "\nChangements de tonalité : " + " → ".join(parts) + "."
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
        s.play.setAccessibleName("Pause" if playing else "Lecture")

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
        if s.play.accessibleName() == "Pause" and not self.player.playing:
            self._update_play_icon()
        s.time.setText(f"{fmt_time(position)} / {fmt_time(self.project.duration)}")
        beat = self.project.beat_at(position)
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
                place = f"mesure {position[0]} · temps {position[1]}"
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
        status = "Suit la lecture"
        if pinned:
            place = project.bar_position(beat)
            status = f"Épinglé : mesure {place[0]}" if place and place[0] else "Épinglé"
        elif segment is None and beat < 0 and segments:
            segment, status = segments[0], "Premier accord du morceau"
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
        menu.addAction("Corriger l'accord…", lambda: self.edit_chord(*selection))
        segment = project.segment_at_beat(beat)
        if segment and segment.candidates:
            alternatives = menu.addMenu("Remplacer par")
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
            "Boucler la sélection", self.toggle_loop_key if not self.player.loop else self._reloop
        )
        menu.addAction("La première mesure commence ici", lambda: self._downbeat_here(beat))
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
            "Effacer les corrections",
            "Revenir à l'analyse d'origine ? Vous pourrez encore annuler avec Ctrl + Z.",
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
            self._alert(f"La sauvegarde a échoué : {exc.strerror or exc}")

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
            self, "Enregistrer une copie du projet", suggested, f"Projet LocalChords (*{EXTENSION})"
        )
        if path:
            try:
                self.project.save(Path(path))
            except OSError as exc:
                self._alert(f"Enregistrement impossible : {exc.strerror or exc}")

    def export_as(self, kind: str) -> None:
        if not self.project or not self.project.analysis["segments"]:
            self._alert("Il n'y a pas encore de grille à exporter.")
            return
        titles = {"txt": "Texte", "cho": "ChordPro", "pdf": "PDF"}
        suggested = f"{self.project.audio.get('title') or 'accords'}.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Exporter en {titles[kind]}", suggested, f"{titles[kind]} (*.{kind})"
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
            self._alert(f"Export impossible : {exc.strerror or exc}")

    def export_sheet(self) -> None:
        """Every chord of the song with its diagrams, on paper."""
        if not self.project or not self.project.analysis["segments"]:
            self._alert("Il n'y a pas encore de grille à exporter.")
            return
        chords = self.song.chords
        dialog = SheetDialog(chords.mode, bool(self.settings.get("sheet_grid", False)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, grid = dialog.mode, dialog.grid.isChecked()
        self._remember("sheet_grid", grid)
        suggested = f"{self.project.audio.get('title') or 'morceau'} - accords.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la fiche des accords", suggested, "PDF (*.pdf)"
        )
        if path:
            self.export_sheet_to(Path(path), mode, grid)

    def export_sheet_to(self, path: Path, mode: str, grid: bool) -> None:
        try:
            write_chord_sheet(
                self.project, path, self.song.chords.all_items, mode, grid, self.song.positions
            )
        except OSError as exc:
            self._alert(f"Export impossible : {exc.strerror or exc}")

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
            "À propos de LocalChords",
            f"<b>LocalChords {__version__}</b><br>Grille d'accords locale et synchronisée.<br><br>"
            "Reconnaissance : chordotomy, lv-chordia, Beat This!, librosa.<br>"
            "Interface : Qt (PySide6). Audio : PyAV (FFmpeg), PortAudio.<br>"
            "Le détail des licences est dans LICENCES-TIERS.md, dans le dossier _internal.<br><br>"
            "L'audio n'est jamais envoyé nulle part. Les accords sont extraits automatiquement : "
            "vérifiez-les à l'oreille.",
        )

    def closeEvent(self, event):
        self.flush()
        self._stop_job()
        self._cancel_download()
        self.cancel_batch()
        self.player.pause()
        self.player.close_device()
        library.save_settings(self.settings)
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
        self.setWindowTitle("Progressions répétées")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        found = project.progressions()
        if not found:
            layout.addWidget(QLabel("Aucune suite d'accords ne se répète dans ce morceau."))
        grid = project.grid()
        for item in found:
            chords = "  ".join(export.chord_text(project, s) for s in item["symbols"])
            b = QPushButton(f"{chords}     × {item['count']}")
            b.setObjectName("recent")
            b.setToolTip("Aller à sa première apparition")
            at = grid[item["start_beats"][0]]
            b.clicked.connect(lambda _=False, t=at: (seek(t), self.accept()))
            layout.addWidget(b)
        note = QLabel("Repérées d'après les accords affichés : à vérifier à l'oreille.")
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
    # Qt's own buttons (Yes/No, Cancel) in French, like the rest of the program.
    if not hasattr(app, "_french"):
        app._french = QTranslator(app)
        folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if app._french.load("qtbase_fr", folder):
            app.installTranslator(app._french)
    return app
