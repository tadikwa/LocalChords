"""The home screen as a library (v1.4): every analyzed song, searched, sorted, starred, gathered in
collections; and what goes with it: kept copies of the audio, finding moved files, backups.
docs/TECHNIQUE.md#la-bibliothèque-v14."""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QAbstractTableModel,
    QEventLoop,
    QFile,
    QMimeData,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import audio, backup, i18n, library
from .. import catalog as C
from .. import lyrics as L
from ..chords import key_name
from ..i18n import translate
from ..project import Project, ProjectError
from . import theme
from .widgets import fmt_time, language_menu, segmented

MONTHS = (
    QT_TRANSLATE_NOOP("Library", "janv."),
    QT_TRANSLATE_NOOP("Library", "févr."),
    QT_TRANSLATE_NOOP("Library", "mars"),
    QT_TRANSLATE_NOOP("Library", "avr."),
    QT_TRANSLATE_NOOP("Library", "mai"),
    QT_TRANSLATE_NOOP("Library", "juin"),
    QT_TRANSLATE_NOOP("Library", "juil."),
    QT_TRANSLATE_NOOP("Library", "août"),
    QT_TRANSLATE_NOOP("Library", "sept."),
    QT_TRANSLATE_NOOP("Library", "oct."),
    QT_TRANSLATE_NOOP("Library", "nov."),
    QT_TRANSLATE_NOOP("Library", "déc."),
)
ESTIMATED = QT_TRANSLATE_NOOP(
    "Library",
    "Date estimée d'après le fichier du projet : il a été créé avant la v1.4, qui retient "
    "ces dates.",
)
AUDIO_TEXT = {
    "kept": (
        QT_TRANSLATE_NOOP("Library", "Conservé"),
        QT_TRANSLATE_NOOP("Library", "Une copie est gardée dans le dossier de LocalChords."),
    ),
    "ok": (
        QT_TRANSLATE_NOOP("Library", "Disponible"),
        QT_TRANSLATE_NOOP("Library", "Le fichier audio d'origine est à sa place."),
    ),
    "offline": (
        QT_TRANSLATE_NOOP("Library", "Disque absent"),
        QT_TRANSLATE_NOOP(
            "Library",
            "Le disque ou le partage réseau de ce fichier n'est pas "
            "connecté. Rien n'est supprimé : le morceau se rejoue quand il revient.",
        ),
    ),
    "missing": (
        QT_TRANSLATE_NOOP("Library", "Introuvable"),
        QT_TRANSLATE_NOOP(
            "Library",
            "Le fichier audio a été déplacé, renommé ou supprimé. La "
            "grille, les corrections et les paroles restent consultables.",
        ),
    ),
    "unknown": ("…", QT_TRANSLATE_NOOP("Library", "Pas encore vérifié.")),
}
# (key, header, sort it gives when clicked)
COLUMNS = [
    ("favorite", "", None),
    ("title", QT_TRANSLATE_NOOP("Library", "Titre"), "title"),
    ("artist", QT_TRANSLATE_NOOP("Library", "Artiste"), "artist"),
    ("genre", QT_TRANSLATE_NOOP("Library", "Genre"), "genre"),
    ("year", QT_TRANSLATE_NOOP("Library", "Année"), "year"),
    ("duration", QT_TRANSLATE_NOOP("Library", "Durée"), "duration"),
    ("key", QT_TRANSLATE_NOOP("Library", "Tonalité"), "key"),
    ("bpm", QT_TRANSLATE_NOOP("Library", "Tempo"), "bpm"),
    ("chords", QT_TRANSLATE_NOOP("Library", "Accords"), None),
    ("lyrics", QT_TRANSLATE_NOOP("Library", "Paroles"), None),
    ("audio", QT_TRANSLATE_NOOP("Library", "Audio"), None),
    ("added", QT_TRANSLATE_NOOP("Library", "Ajouté"), "added"),
    ("opened", QT_TRANSLATE_NOOP("Library", "Ouvert"), "opened"),
]
NARROW_HIDDEN = ("year", "chords", "added")  # the columns that go first on a narrow window
TIGHT_HIDDEN = ("genre", "bpm", "lyrics", "audio", "opened")  # then these, so nothing is cut
VIEW_ICONS = {
    "all": "music", "fav": "star", "recent": "clock", "latest": "plus", "hidden": "hidden",
    "col": "collection",
}  # fmt: skip
COUNT_ROLE = Qt.ItemDataRole.UserRole + 1
VIEWS = {
    "all": QT_TRANSLATE_NOOP("Library", "Tous les morceaux"),
    "fav": QT_TRANSLATE_NOOP("Library", "Favoris"),
    "recent": QT_TRANSLATE_NOOP("Library", "Récemment ouverts"),
    "latest": QT_TRANSLATE_NOOP("Library", "Derniers ajouts"),
    "hidden": QT_TRANSLATE_NOOP("Library", "Retirés de la bibliothèque"),
}


def day(ts: float | None, estimated: bool = False) -> str:
    if not ts:
        return "—"
    t = time.localtime(ts)
    month = translate("Library", MONTHS[t.tm_mon - 1])
    text = translate("Library", "{day} {month} {year}").format(
        day=t.tm_mday, month=month, year=t.tm_year
    )
    return f"≈ {text}" if estimated else text


def megabytes(n: int) -> str:
    return i18n.size(n)


def trash(path: Path) -> bool:
    """To the Recycle Bin, never straight away."""
    result = QFile.moveToTrash(str(path))
    return bool(result[0] if isinstance(result, tuple) else result)


def run_task(parent: QWidget, title: str, fn, cancellable: bool = True):
    """fn(progress, stop) on another thread behind a progress dialog, the window staying alive.
    progress(text, fraction or None). Returns fn's result, or raises what it raised."""
    state = {"done": False, "result": None, "error": None, "text": "", "fraction": None}
    cancel = threading.Event()

    def progress(text: str, fraction: float | None = None) -> None:
        state["text"], state["fraction"] = text, fraction

    def work() -> None:
        try:
            state["result"] = fn(progress, cancel.is_set)
        except BaseException as exc:  # noqa: BLE001 - handed to the caller, on its thread
            state["error"] = exc
        finally:
            state["done"] = True

    dialog = QProgressDialog(title, translate("Library", "Annuler"), 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(300)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.canceled.connect(cancel.set)
    if not cancellable:
        dialog.setCancelButton(None)
    loop = QEventLoop()

    def tick() -> None:
        if state["done"]:
            loop.quit()
            return
        if state["text"]:
            dialog.setLabelText(state["text"])
        if state["fraction"] is None:
            dialog.setRange(0, 0)
        else:
            dialog.setRange(0, 1000)
            dialog.setValue(int(state["fraction"] * 1000))

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(80)
    threading.Thread(target=work, daemon=True).start()
    loop.exec()
    timer.stop()
    dialog.close()
    if state["error"] is not None:
        raise state["error"]
    return state["result"]


class Scanner(QObject):
    """Brings the index up to the projects off the interface's thread, on its own connection."""

    finished = Signal(object)  # the scan's report, or an error text

    def start(self, path) -> None:
        def run():
            try:
                catalog = C.Catalog(path)
                try:
                    report = catalog.scan(library.data_dir() / "projects")
                    catalog.backup_daily(library.data_dir() / C.BACKUPS)
                finally:
                    catalog.close()
            except Exception as exc:  # noqa: BLE001 - said in the log; the page shows what it has
                report = str(exc)
            with contextlib.suppress(RuntimeError):  # the window closed meanwhile
                self.finished.emit(report)

        threading.Thread(target=run, daemon=True).start()


# The songs, as a table and as cards -----------------------------------------------------------
SONGS_MIME = "application/x-localchords-songs"  # songs dragged onto a collection


class SongModel(QAbstractTableModel):
    def __init__(self, latin=lambda: False):
        super().__init__()
        self.rows: list[dict] = []
        self.latin = latin
        self.star = theme.icon("star", theme.ACCENT, 16)
        self.no_star = theme.icon("star_line", theme.TEXT_3, 16)

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def song(self, row: int) -> dict:
        return self.rows[row]

    def flags(self, index):
        return super().flags(index) | Qt.ItemFlag.ItemIsDragEnabled

    def mimeTypes(self):  # noqa: N802
        return [SONGS_MIME]

    def mimeData(self, indexes):  # noqa: N802
        rows = sorted({i.row() for i in indexes if i.isValid()})
        mime = QMimeData()
        mime.setData(SONGS_MIME, "\n".join(self.rows[r]["id"] for r in rows).encode())
        return mime

    def rowCount(self, parent=QModelIndex()):  # noqa: B008, N802 - Qt's
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008, N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return translate("Library", COLUMNS[section][1])
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.ToolTipRole:
            return translate("Library", "Favori") if section == 0 else None
        return None

    def text(self, s: dict, key: str) -> str:
        if key == "title":
            return s["title"] or translate("Library", "Sans titre")
        if key == "artist":
            return s["artist"] or "—"
        if key == "genre":
            return translate("Catalog", s["shown_genre"] or "") or translate(
                "Library", "Non renseigné"
            )
        if key == "year":
            return str(s["year"]) if s["year"] else "—"
        if key == "duration":
            return fmt_time(s["duration"]) if s["duration"] else "—"
        if key == "key":
            return key_name(s["key"], latin=self.latin()) if s["key"] else "—"
        if key == "bpm":
            return f"{round(s['bpm'])} BPM" if s["bpm"] else "—"
        if key == "chords":
            return str(s["chords"]) if s["chords"] else "—"
        if key == "lyrics":
            return translate("Library", "Oui") if s["lyrics"] else "—"
        if key == "audio":
            if s["project_state"] != "ok":
                return (
                    translate("Library", "Projet absent")
                    if s["project_state"] == "missing"
                    else translate("Library", "Projet illisible")
                )
            return translate("Library", AUDIO_TEXT[s["audio_state"]][0])
        if key == "added":
            return day(s["added_at"], s["added_estimated"])
        if key == "opened":
            return day(s["opened_at"], s["opened_estimated"])
        return ""

    def tip(self, s: dict, key: str) -> str | None:
        if key == "favorite":
            return (
                translate("Library", "Retirer des favoris")
                if s["favorite"]
                else translate("Library", "Ajouter aux favoris")
            )
        if key == "genre" and not s["shown_genre"]:
            return translate("Library", "Genre non renseigné : clic droit pour le choisir.")
        if key == "genre" and s["genre"] is None:
            return translate("Library", "D'après les informations du fichier audio.")
        if key == "lyrics" and s["lyrics"]:
            return translate(
                "Lyrics", L.KINDS.get(s["lyrics"], QT_TRANSLATE_NOOP("Lyrics", "Paroles"))
            )
        if key in ("key", "bpm", "chords") and not s["analyzed"]:
            return translate("Library", "Pas encore analysé.")
        if key == "audio":
            if s["project_state"] == "missing":
                return translate(
                    "Library", "Le fichier du projet n'est plus dans le dossier de LocalChords."
                )
            if s["project_state"] == "unreadable":
                return translate(
                    "Library",
                    "Le fichier du projet est endommagé ou vient d'une version plus récente.",
                )
            where = s["audio_path"] or ""
            return f"{translate('Library', AUDIO_TEXT[s['audio_state']][1])}\n{where}".strip()
        if key == "added" and s["added_estimated"] or key == "opened" and s["opened_estimated"]:
            return translate("Library", ESTIMATED)
        if key == "title":
            return " — ".join(x for x in (s["title"], s["artist"], s["album"]) if x)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        s = self.rows[index.row()]
        key = COLUMNS[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return self.text(s, key)
        if role == Qt.ItemDataRole.DecorationRole and key == "favorite":
            return self.star if s["favorite"] else self.no_star
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tip(s, key)
        if role == Qt.ItemDataRole.AccessibleTextRole and key == "favorite":
            return (
                translate("Library", "Favori")
                if s["favorite"]
                else translate("Library", "Pas favori")
            )
        if role == Qt.ItemDataRole.ForegroundRole:
            if s["project_state"] != "ok":
                return QColor(theme.TEXT_3)
            if key == "audio" and s["audio_state"] in ("missing", "offline"):
                return QColor(theme.ERROR)
            if key == "genre" and not s["shown_genre"] or self.text(s, key) == "—":
                return QColor(theme.TEXT_3)
            if key != "title":
                return QColor(theme.TEXT_2)
        if role == Qt.ItemDataRole.FontRole and key == "title":
            font = theme.app_font(13, 600)
            return font
        return None


class CardDelegate(QStyledItemDelegate):
    SIZE = QSize(248, 108)

    def __init__(self, model: SongModel, parent=None):
        super().__init__(parent)
        self.model = model

    def sizeHint(self, option, index):  # noqa: N802
        return self.SIZE

    @staticmethod
    def star_rect(rect: QRect) -> QRect:
        return QRect(rect.right() - 34, rect.top() + 6, 28, 28)

    def paint(self, p: QPainter, option, index):
        s = self.model.song(index.row())
        r = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(theme.SELECT if selected else theme.BORDER), 1.2))
        p.setBrush(QColor(theme.SURFACE_3 if selected else theme.SURFACE))
        p.drawRoundedRect(r, 8, 8)
        text = r.adjusted(12, 10, -40, -10)
        m = self.model
        title_font = theme.app_font(14, 600)
        p.setFont(title_font)
        p.setPen(QColor(theme.TEXT if s["project_state"] == "ok" else theme.TEXT_3))
        fm = p.fontMetrics()
        title = fm.elidedText(m.text(s, "title"), Qt.TextElideMode.ElideRight, text.width())
        p.drawText(text.left(), text.top() + fm.ascent(), title)
        p.setFont(theme.app_font(12))
        p.setPen(QColor(theme.TEXT_2))
        small = p.fontMetrics()
        y = text.top() + fm.height() + small.ascent() + 2
        who = s["artist"] or translate("Library", "Artiste non renseigné")
        p.drawText(
            text.left(), y, small.elidedText(who, Qt.TextElideMode.ElideRight, text.width() + 28)
        )
        facts = [m.text(s, "key"), m.text(s, "bpm"), m.text(s, "duration")]
        line = " · ".join(f for f in facts if f != "—") or translate(
            "Library", "Pas encore analysé"
        )
        y += small.height() + 4
        p.drawText(
            text.left(), y, small.elidedText(line, Qt.TextElideMode.ElideRight, text.width() + 28)
        )
        y += small.height() + 2
        state = s["audio_state"] if s["project_state"] == "ok" else None
        if state in ("missing", "offline") or s["project_state"] != "ok":
            p.setPen(QColor(theme.ERROR))
            p.drawText(text.left(), y, m.text(s, "audio"))
        else:
            p.setPen(QColor(theme.TEXT_3))
            extra = [
                translate("Catalog", s["shown_genre"] or ""),
                translate("Library", "paroles") if s["lyrics"] else "",
            ]
            line = " · ".join(x for x in extra if x)
            elide = Qt.TextElideMode.ElideRight
            p.drawText(text.left(), y, small.elidedText(line, elide, text.width() + 28))
        icon = m.star if s["favorite"] else m.no_star
        icon.paint(p, self.star_rect(option.rect).adjusted(5, 5, -5, -5))
        p.restore()


class CardView(QListView):
    starClicked = Signal(int)

    def mouseReleaseEvent(self, event):  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if (
            index.isValid()
            and event.button() == Qt.MouseButton.LeftButton
            and CardDelegate.star_rect(self.visualRect(index)).contains(event.position().toPoint())
        ):
            self.starClicked.emit(index.row())
            return
        super().mouseReleaseEvent(event)


class SongTable(QTableView):
    """The title takes the room the other columns leave, between readable and not adrift."""

    def fit_title(self) -> None:
        h = self.horizontalHeader()
        shown = [i for i in range(h.count()) if i != 1 and not h.isSectionHidden(i)]
        rest = sum(h.sectionSize(i) for i in shown)
        self.setColumnWidth(1, min(560, max(220, self.viewport().width() - rest)))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.fit_title()


class SideDelegate(QStyledItemDelegate):
    """Each view's number of songs, right-aligned in the room the style sheet keeps for it."""

    def paint(self, p: QPainter, option, index):
        super().paint(p, option, index)
        count = index.data(COUNT_ROLE)
        if count is None:
            return
        p.save()
        p.setFont(theme.app_font(theme.SIZE_CAPTION))
        p.setPen(QColor(theme.TEXT_2))
        box = option.rect.adjusted(0, 0, -10, 0)
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        p.drawText(box, int(align), str(count))
        p.restore()


class SideList(QListWidget):
    """The views and collections; songs dropped on a collection or on Favoris join it."""

    songsDropped = Signal(object, list)  # the view's key, the songs' ids

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setItemDelegate(SideDelegate(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # names elide
        self.setIconSize(QSize(16, 16))

    def _target(self, event):
        item = self.itemAt(event.position().toPoint())
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        ok = event.mimeData().hasFormat(SONGS_MIME) and key and key[0] in ("col", "fav")
        return key if ok else None

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(SONGS_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802
        if self._target(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # noqa: N802
        key = self._target(event)
        if not key:
            event.ignore()
            return
        ids = bytes(event.mimeData().data(SONGS_MIME)).decode().split()
        event.acceptProposedAction()
        if ids:
            self.songsDropped.emit(key, ids)


# The page -------------------------------------------------------------------------------------
class LibraryPage(QWidget):
    openRequested = Signal()
    linkRequested = Signal()
    projectRequested = Signal(Path)
    audioChanged = Signal(Path, dict)  # a project's file, its audio as now saved
    projectsReplaced = Signal(list)  # project files written over (deleted, restored)
    settingsRestored = Signal()
    shortcutsRequested = Signal()
    aboutRequested = Signal()

    def __init__(self, catalog: C.Catalog, settings: dict, remember):
        super().__init__()
        self.setObjectName("page")
        self.catalog = catalog
        self.settings = settings
        self.remember = remember
        self.view_key: tuple = ("all",)
        self.scanning = False
        self.scanner = Scanner()
        self.scanner.finished.connect(self._scanned)
        self.search_timer = QTimer(self, singleShot=True, interval=120)
        self.search_timer.timeout.connect(self.refresh)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._sidebar())
        main = QWidget()
        column = QVBoxLayout(main)
        column.setContentsMargins(24, 18, 24, 12)
        column.setSpacing(10)
        column.addLayout(self._top())
        column.addWidget(self._filters())
        self.batch_box = QWidget()
        batch_row = QHBoxLayout(self.batch_box)
        batch_row.setContentsMargins(0, 0, 0, 0)
        self.batch_text = QLabel()
        self.batch_text.setObjectName("muted")
        self.batch_text.setWordWrap(True)
        self.batch_cancel = QPushButton(translate("Library", "Arrêter"))
        batch_row.addWidget(self.batch_text, 1)
        batch_row.addWidget(self.batch_cancel)
        self.batch_box.hide()
        column.addWidget(self.batch_box)
        self.pages = QStackedWidget()
        self.model = SongModel(lambda: bool(self.settings.get("latin")))
        self.table = self._table()
        self.cards = self._cards()
        self.empty = self._empty()
        self.welcome = self._welcome()
        for w in (self.table, self.cards, self.empty, self.welcome):
            self.pages.addWidget(w)
        column.addWidget(self.pages, 1)
        outer.addWidget(main, 1)

        def shortcut(keys, fn):
            QShortcut(QKeySequence(keys), self, activated=fn,
                      context=Qt.ShortcutContext.WidgetWithChildrenShortcut)  # fmt: skip

        shortcut("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll()))
        shortcut("Alt+Up", lambda: self.move_selected(-1))
        shortcut("Alt+Down", lambda: self.move_selected(1))
        self.refresh()

    # Building ----------------------------------------------------------------------------------
    def _sidebar(self) -> QWidget:
        self.sidebar = side = QWidget()
        side.setObjectName("bar")
        side.setFixedWidth(232)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)
        name = QLabel(translate("Library", "Ma bibliothèque"))
        name.setObjectName("h2")
        layout.addWidget(name)
        self.side = SideList()
        self.side.setObjectName("side")
        self.side.songsDropped.connect(self.drop_songs)
        self.side.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.side.customContextMenuRequested.connect(self._side_menu)
        self.side.currentItemChanged.connect(self._side_changed)
        self.side.itemDoubleClicked.connect(lambda item: self._rename_collection(item))
        layout.addWidget(self.side, 1)
        new = QPushButton(translate("Library", "Nouvelle collection"))
        new.setObjectName("link")
        new.setIcon(theme.icon("plus", theme.SELECT, 14))
        new.setToolTip(
            translate("Library", "Créer une collection ; on peut aussi y glisser des morceaux")
        )
        new.clicked.connect(lambda: self.new_collection())
        layout.addWidget(new, 0, Qt.AlignmentFlag.AlignLeft)
        place = translate("Library", "Tout reste sur votre ordinateur.")
        if library.portable_dir() == library.data_dir():
            place = translate(
                "Library", "Mode portable : tout reste dans le dossier Data, à côté du programme."
            )
        self.place = QLabel(place)
        self.place.setObjectName("caption")
        self.place.setWordWrap(True)
        layout.addWidget(self.place)
        return side

    def _top(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.heading = QLabel()
        self.heading.setObjectName("title")
        self.count = QLabel()
        self.count.setObjectName("caption")
        titles.addWidget(self.heading)
        titles.addWidget(self.count)
        row.addLayout(titles)
        row.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            translate("Library", "Rechercher un titre, un artiste, un genre, une étiquette…")
        )
        self.search.setClearButtonEnabled(True)
        self.search.addAction(
            theme.icon("search", theme.TEXT_2, 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search.setToolTip(translate("Library", "Rechercher (Ctrl + F)"))
        self.search.setMinimumWidth(200)
        self.search.setMaximumWidth(460)
        self.search.setAccessibleName(translate("Library", "Rechercher dans la bibliothèque"))
        self.search.textChanged.connect(lambda: self.search_timer.start())
        row.addWidget(self.search, 2)
        self.add_button = QToolButton()
        self.add_button.setObjectName("primary")
        self.add_button.setText(translate("Library", "Ajouter un morceau"))
        self.add_button.setAccessibleName(translate("Library", "Ajouter un morceau"))
        self.add_button.setIcon(theme.icon("plus", theme.ON_ACCENT))
        self.add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.add_button.setToolTip(
            translate(
                "Library", "Un fichier audio (Ctrl + O), un lien, ou glissez des fichiers ici"
            )
        )
        add = QMenu(self)
        add.addAction(translate("Library", "Fichier audio ou projet…"), self.openRequested.emit)
        add.addAction(
            translate("Library", "Lien (YouTube et autres sites)…"), self.linkRequested.emit
        )
        self.add_button.setMenu(add)
        row.addWidget(self.add_button)
        self.menu_button = QToolButton()
        self.menu_button.setIcon(theme.icon("more"))
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setToolTip(
            translate("Library", "Sauvegarde, restauration et autres options")
        )
        self.menu_button.setAccessibleName(translate("Library", "Options de la bibliothèque"))
        menu = QMenu(self)
        menu.addAction(translate("Library", "Sauvegarder la bibliothèque…"), self.backup)
        menu.addAction(translate("Library", "Restaurer une sauvegarde…"), self.restore)
        menu.addSeparator()
        menu.addAction(
            translate("Library", "Retrouver les fichiers audio manquants…"),
            lambda: self.find_in_folder(None),
        )
        menu.addAction(
            translate("Library", "Ouvrir le dossier de LocalChords"),
            lambda: self._reveal(library.data_dir()),
        )
        menu.addSeparator()
        language_menu(menu, self.settings)
        menu.addAction(
            translate("Library", "Raccourcis clavier"), self.shortcutsRequested.emit
        ).setObjectName("shortcuts")  # the updater puts its entries just above
        menu.addAction(translate("Library", "À propos de LocalChords"), self.aboutRequested.emit)
        self.menu_button.setMenu(menu)
        row.addWidget(self.menu_button)
        return row

    def _filters(self) -> QWidget:
        """The filters, then the sort: side by side, or one above the other when narrow."""
        box = QWidget()
        self.filter_rows = QBoxLayout(QBoxLayout.Direction.LeftToRight, box)
        self.filter_rows.setContentsMargins(0, 0, 0, 0)
        self.filter_rows.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.filter_rows.addLayout(row)
        self.genre_box = QComboBox()
        self.genre_box.setAccessibleName(translate("Library", "Genre"))
        self.tag_box = QComboBox()
        self.tag_box.setAccessibleName(translate("Library", "Étiquette"))
        self.state_box = QComboBox()
        self.state_box.setAccessibleName(translate("Library", "État"))
        for text, value in (
            (translate("Library", "Tous les états"), None),
            (translate("Library", "Avec paroles"), "lyrics"),
            (translate("Library", "Sans paroles"), "nolyrics"),
            (translate("Library", "Audio introuvable"), "missing"),
            (translate("Library", "Audio conservé"), "kept"),
        ):
            self.state_box.addItem(text, value)
        for combo in (self.genre_box, self.tag_box, self.state_box):
            combo.currentIndexChanged.connect(self.refresh)
            row.addWidget(combo)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.filter_rows.addLayout(row, 1)
        self.clear_filters = QPushButton(translate("Library", "Effacer les filtres"))
        self.clear_filters.setObjectName("link")
        self.clear_filters.clicked.connect(self.reset_filters)
        row.addWidget(self.clear_filters)
        row.addStretch(1)
        sort_label = QLabel(translate("Library", "Trier par"))
        sort_label.setObjectName("caption")
        row.addWidget(sort_label)
        self.sort_box = QComboBox()
        self.sort_box.setAccessibleName(translate("Library", "Trier par"))
        for value, text in C.SORTS.items():
            self.sort_box.addItem(translate("Catalog", text), value)
        self.sort_box.addItem(translate("Library", "Ordre de la collection"), "order")
        self.order_index = self.sort_box.count() - 1
        sort = self.settings.get("library_sort", "title")
        self.sort_box.setCurrentIndex(max(0, self.sort_box.findData(sort)))
        self.sort_box.currentIndexChanged.connect(self._sort_changed)
        row.addWidget(self.sort_box)
        self.desc = QToolButton()
        self.desc.setObjectName("sortDir")
        self.desc.setCheckable(True)
        self.desc.setChecked(bool(self.settings.get("library_desc", False)))
        self.desc.toggled.connect(self._desc_changed)
        row.addWidget(self.desc)
        self.view_list = QToolButton()
        self.view_list.setIcon(theme.icon("rows", on=None))
        self.view_list.setToolTip(translate("Library", "Liste"))
        self.view_list.setAccessibleName(translate("Library", "Affichage en liste"))
        self.view_cards = QToolButton()
        self.view_cards.setIcon(theme.icon("tiles", on=None))
        self.view_cards.setToolTip(translate("Library", "Cartes"))
        self.view_cards.setAccessibleName(translate("Library", "Affichage en cartes"))
        for b, mode in ((self.view_list, "list"), (self.view_cards, "cards")):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
        row.addWidget(segmented((self.view_list, self.view_cards)))
        self._show_direction()
        return box

    def _table(self) -> QTableView:
        t = SongTable()
        t.setModel(self.model)
        t.setObjectName("songs")
        t.setAccessibleName(translate("Library", "Morceaux"))
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.setShowGrid(False)
        t.setWordWrap(False)
        t.setAlternatingRowColors(False)
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(36)
        t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setDragEnabled(True)
        t.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        t.setTextElideMode(Qt.TextElideMode.ElideRight)
        h = t.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionsClickable(True)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        widths = {"favorite": 36, "title": 260, "artist": 170, "genre": 130, "year": 64,
                  "duration": 64, "key": 96, "bpm": 84, "chords": 72, "lyrics": 70,
                  "audio": 100, "added": 104, "opened": 104}  # fmt: skip
        for i, (key, _, _) in enumerate(COLUMNS):
            t.setColumnWidth(i, widths[key])
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.sectionClicked.connect(self._header_clicked)
        t.clicked.connect(
            lambda i: self.toggle_favorite([self.model.song(i.row())]) if i.column() == 0 else None
        )
        t.doubleClicked.connect(
            lambda i: self.open_song(self.model.song(i.row())) if i.column() else None
        )
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(
            lambda pos: self._song_menu(t.viewport().mapToGlobal(pos))
        )
        return t

    def _cards(self) -> CardView:
        v = CardView()
        v.setModel(self.model)
        v.setModelColumn(1)
        v.setItemDelegate(CardDelegate(self.model, v))
        v.setViewMode(QListView.ViewMode.IconMode)
        v.setResizeMode(QListView.ResizeMode.Adjust)
        v.setMovement(QListView.Movement.Static)
        v.setUniformItemSizes(True)
        v.setSpacing(2)
        v.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        v.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        v.setDragEnabled(True)
        v.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        v.setObjectName("cards")
        v.starClicked.connect(lambda row: self.toggle_favorite([self.model.song(row)]))
        v.doubleClicked.connect(lambda i: self.open_song(self.model.song(i.row())))
        v.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        v.customContextMenuRequested.connect(
            lambda pos: self._song_menu(v.viewport().mapToGlobal(pos))
        )
        return v

    def _empty(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)
        self.empty_text = QLabel()
        self.empty_text.setObjectName("muted")
        self.empty_text.setWordWrap(True)
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_action = QPushButton()
        self.empty_action.clicked.connect(lambda: self._empty_fn())
        layout.addWidget(self.empty_text)
        layout.addWidget(self.empty_action, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)
        self._empty_fn = lambda: None
        return w

    def _welcome(self) -> QWidget:
        """The first launch: nothing analyzed yet, the way in is the whole page."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(640)
        layout = QVBoxLayout(column)
        layout.setSpacing(16)
        title = QLabel("LocalChords")
        title.setObjectName("h1")
        lead = QLabel(
            translate(
                "Library",
                "Glissez un morceau dans cette fenêtre : ses accords apparaissent en "
                "grille et défilent avec la lecture. Chaque morceau analysé reste "
                "ensuite ici, avec ses corrections et ses paroles.",
            )
        )
        lead.setObjectName("muted")
        lead.setWordWrap(True)
        self.open_button = QPushButton(
            translate("Library", "Ouvrir un morceau…")
        )  # amber: « Ajouter », just above
        self.open_button.setToolTip("Ctrl + O")
        self.open_button.clicked.connect(self.openRequested)
        self.link_button = QPushButton(translate("Library", "Importer un lien…"))
        self.link_button.setToolTip(
            translate(
                "Library",
                "YouTube et autres sites, pour les contenus que vous avez le droit de télécharger",
            )
        )
        self.link_button.clicked.connect(self.linkRequested)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.link_button)
        buttons.addStretch()
        formats = QLabel(
            translate(
                "Library",
                "MP3, WAV, FLAC, M4A, OGG, OPUS… Une sauvegarde de bibliothèque se "
                "restaure depuis le menu Options, en haut à droite.",
            )
        )
        formats.setObjectName("caption")
        formats.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(lead)
        layout.addLayout(buttons)
        layout.addWidget(formats)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column, 3)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        return w

    # Showing -----------------------------------------------------------------------------------
    def start_scan(self) -> None:
        """Index what is on disk; at start, and after a restore. A catalog kept in memory (a Data
        folder that cannot be written) is scanned here: it cannot be shared with another thread."""
        if self.catalog.path == ":memory:":
            with contextlib.suppress(C.CatalogError):
                self.catalog.scan(library.data_dir() / "projects")
            self.refresh()
            return
        self.scanning = True
        self.refresh()
        self.scanner.start(self.catalog.path)

    def _scanned(self, report) -> None:
        self.scanning = False
        self.refresh()

    def refresh(self) -> None:
        """Everything from the catalog again; the selection stays."""
        try:
            songs = self.catalog.songs()
            collections = self.catalog.collections()
        except Exception:  # noqa: BLE001 - a catalog that fails to read shows as empty
            songs, collections = [], []
        self._fill_side(songs, collections)
        self._fill_filters(songs)
        selected = {s["id"] for s in self.selected()}
        kind = self.view_key[0]
        visible = [s for s in songs if bool(s["hidden"]) == (kind == "hidden")]
        if kind == "fav":
            visible = [s for s in visible if s["favorite"]]
        order = None
        if kind == "col":
            order = self.catalog.members(self.view_key[1])
            members = set(order)
            visible = [s for s in visible if s["id"] in members]
        sort, descending = self.sort_box.currentData(), self.desc.isChecked()
        if kind == "recent":
            sort, descending = "opened", True
        elif kind == "latest":
            sort, descending = "added", True
        use_order = order if (kind == "col" and sort == "order") else None
        rows = C.arrange(
            visible,
            query=self.search.text(),
            sort="title" if sort == "order" else sort,
            descending=descending,
            genre=self.genre_box.currentData(),
            tag=self.tag_box.currentData(),
            state=self.state_box.currentData(),
            order=use_order,
        )
        if kind == "recent":
            rows = [s for s in rows if s["opened_at"]][: C.LATEST]
        elif kind == "latest":
            rows = rows[: C.LATEST]
        self.model.set_rows(rows)
        self._restore_selection(selected)
        self._show_header(kind, len(rows), len(visible), songs)
        fixed = kind in ("recent", "latest")
        self.sort_box.setEnabled(not fixed)
        self.desc.setEnabled(not fixed and sort != "order")
        filtered = bool(self.search.text().strip()) or any(
            b.currentIndex() > 0 for b in (self.genre_box, self.tag_box, self.state_box)
        )
        self.clear_filters.setVisible(filtered)
        if not songs:
            self.pages.setCurrentWidget(self.welcome)
        elif not rows:
            self._show_empty(kind, filtered)
        else:
            self.set_mode(self.settings.get("library_view", "list"), remember=False)

    def _show_header(self, kind, shown, total, songs) -> None:
        if kind == "col":
            name = next(
                (c["name"] for c in self.catalog.collections() if c["cid"] == self.view_key[1]), ""
            )
            self.heading.setText(name)
        else:
            self.heading.setText(translate("Library", VIEWS[kind]))
        if shown != total and kind not in ("recent", "latest"):
            n = translate("Library", "%n morceau(x) sur {total}", None, shown).format(total=total)
        else:
            n = translate("Library", "%n morceau(x)", None, shown)
        if self.scanning:
            n = translate("Library", "{count} · lecture des projets…").format(count=n)
        self.count.setText(n)

    def _show_empty(self, kind: str, filtered: bool) -> None:
        if filtered:
            text = translate(
                "Library", "Aucun morceau ne correspond à cette recherche ou à ces filtres."
            )
            action, fn = (
                translate("Library", "Effacer la recherche et les filtres"),
                self.reset_filters,
            )
        elif kind == "fav":
            text = translate(
                "Library",
                "Aucun favori pour l'instant. Cliquez sur l'étoile d'un morceau, dans la "
                "liste ou sur sa page, pour le retrouver ici d'un clic.",
            )
            action, fn = (
                translate("Library", "Voir tous les morceaux"),
                lambda: self.select_view(("all",)),
            )
        elif kind == "col":
            text = translate(
                "Library",
                "Cette collection est vide. Faites un clic droit sur un morceau, puis « "
                "Ajouter à la collection ». Un morceau peut être dans plusieurs "
                "collections.",
            )
            action, fn = (
                translate("Library", "Voir tous les morceaux"),
                lambda: self.select_view(("all",)),
            )
        elif kind == "hidden":
            text = translate("Library", "Aucun morceau retiré de la bibliothèque.")
            action, fn = (
                translate("Library", "Voir tous les morceaux"),
                lambda: self.select_view(("all",)),
            )
        else:
            text = translate("Library", "Aucun morceau ici pour l'instant.")
            action, fn = translate("Library", "Ajouter un morceau…"), self.openRequested.emit
        self.empty_text.setText(text)
        self.empty_action.setText(action)
        self._empty_fn = fn
        self.pages.setCurrentWidget(self.empty)

    def _fill_side(self, songs: list[dict], collections: list[dict]) -> None:
        side = self.side
        side.blockSignals(True)
        side.clear()
        hidden = sum(1 for s in songs if s["hidden"])
        counts = {
            "all": len(songs) - hidden,
            "fav": sum(1 for s in songs if s["favorite"] and not s["hidden"]),
            "hidden": hidden,
        }
        entries = [("all",), ("fav",), ("recent",), ("latest",)]
        if hidden:
            entries.append(("hidden",))
        for key in entries:
            text = (
                translate("Library", VIEWS[key[0]])
                if key[0] != "hidden"
                else translate("Library", "Retirés")
            )
            item = QListWidgetItem(text)
            if key[0] in counts:
                item.setToolTip(translate("Library", "%n morceau(x)", None, counts[key[0]]))
                item.setData(COUNT_ROLE, counts[key[0]])
            color = theme.ACCENT if key[0] == "fav" else theme.TEXT_2
            item.setIcon(theme.icon(VIEW_ICONS[key[0]], color, 16, on=None))
            item.setData(Qt.ItemDataRole.UserRole, key)
            side.addItem(item)
        head = QListWidgetItem(translate("Library", "Collections"))
        head.setFlags(Qt.ItemFlag.NoItemFlags)
        head.setForeground(QColor(theme.TEXT_2))
        head.setFont(theme.app_font(theme.SIZE_CAPTION, 600))
        head.setSizeHint(QSize(0, 40))  # a little air above the collections
        side.addItem(head)
        if not collections:
            none = QListWidgetItem(translate("Library", "Aucune pour l'instant"))
            none.setFlags(Qt.ItemFlag.NoItemFlags)
            none.setForeground(QColor(theme.TEXT_3))
            side.addItem(none)
        for c in collections:
            item = QListWidgetItem(c["name"])
            item.setToolTip(translate("Library", "%n morceau(x)", None, c["count"]))
            item.setData(COUNT_ROLE, c["count"])
            item.setIcon(theme.icon("collection", theme.TEXT_2, 16, on=None))
            item.setData(Qt.ItemDataRole.UserRole, ("col", c["cid"]))
            side.addItem(item)
        found = None
        for i in range(side.count()):
            if side.item(i).data(Qt.ItemDataRole.UserRole) == self.view_key:
                found = side.item(i)
        if found is None:  # a collection deleted, the last hidden song back
            self.view_key = ("all",)
            found = side.item(0)
        side.setCurrentItem(found)
        side.blockSignals(False)

    def _fill_filters(self, songs: list[dict]) -> None:
        def fill(box: QComboBox, first: str, values: list[tuple[str, object]]):
            current = box.currentData()
            box.blockSignals(True)
            box.clear()
            box.addItem(first, None)
            for text, value in values:
                box.addItem(text, value)
            box.setCurrentIndex(max(0, box.findData(current)) if current is not None else 0)
            box.blockSignals(False)

        genres = sorted({s["shown_genre"] for s in songs if s["shown_genre"]}, key=C.folded)
        fill(
            self.genre_box,
            translate("Library", "Tous les genres"),
            [(translate("Catalog", g), g) for g in genres]
            + [(translate("Library", "Non renseigné"), "")],
        )
        tags = sorted({t for s in songs for t in s["tags"]}, key=C.folded)
        fill(
            self.tag_box,
            translate("Library", "Toutes les étiquettes"),
            [(translate("Catalog", t), t) for t in tags],
        )
        self.tag_box.setVisible(bool(tags))

    def _restore_selection(self, ids: set[str]) -> None:
        if not ids:
            return
        for view in (self.table, self.cards):
            sel = view.selectionModel()
            sel.clearSelection()
            for row, s in enumerate(self.model.rows):
                if s["id"] in ids:
                    flags = sel.SelectionFlag.Select | sel.SelectionFlag.Rows
                    sel.select(self.model.index(row, 1), flags)

    def set_mode(self, mode: str, remember: bool = True) -> None:
        if remember:
            self.remember("library_view", mode)
        self.view_list.setChecked(mode == "list")
        self.view_cards.setChecked(mode == "cards")
        if self.model.rows:
            self.pages.setCurrentWidget(self.cards if mode == "cards" else self.table)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        tight = self.width() < 1000  # what makes the library fit a narrow window
        self.sidebar.setFixedWidth(220 if tight else 232)
        self.add_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if tight
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.filter_rows.setDirection(
            QBoxLayout.Direction.TopToBottom if tight else QBoxLayout.Direction.LeftToRight
        )
        narrow = self.width() < 1240
        for i, (key, _, _) in enumerate(COLUMNS):
            self.table.setColumnHidden(
                i, key in NARROW_HIDDEN and narrow or key in TIGHT_HIDDEN and tight
            )
        self.table.fit_title()

    def select_view(self, key: tuple) -> None:
        index = None
        if key[0] == "col" and self.view_key != key:
            index = self.order_index  # a collection shows in its own order first
        elif key[0] != "col" and self.sort_box.currentData() == "order":
            index = max(0, self.sort_box.findData(self.settings.get("library_sort", "title")))
        self.view_key = key
        if index is not None and index != self.sort_box.currentIndex():
            self.sort_box.setCurrentIndex(index)  # refreshes
        else:
            self.refresh()

    def _side_changed(self, item, _previous) -> None:
        if item is not None and item.data(Qt.ItemDataRole.UserRole):
            self.select_view(item.data(Qt.ItemDataRole.UserRole))

    def _sort_changed(self) -> None:
        sort = self.sort_box.currentData()
        if sort != "order":
            self.remember("library_sort", sort)
            dated = sort in ("opened", "added")
            if self.desc.isChecked() != dated:
                self.desc.blockSignals(True)
                self.desc.setChecked(dated)
                self.desc.blockSignals(False)
                self.remember("library_desc", dated)
        self._show_direction()
        self.refresh()

    def _desc_changed(self, on: bool) -> None:
        self.remember("library_desc", on)
        self._show_direction()
        self.refresh()

    def _show_direction(self) -> None:
        down = self.desc.isChecked()
        self.desc.setIcon(theme.icon("sort_down" if down else "sort_up", on=None))
        self.desc.setToolTip(
            translate("Library", "Ordre décroissant")
            if down
            else translate("Library", "Ordre croissant")
        )
        self.desc.setAccessibleName(self.desc.toolTip())

    def _header_clicked(self, section: int) -> None:
        sort = COLUMNS[section][2]
        if sort is None or not self.sort_box.isEnabled():
            return
        if self.sort_box.currentData() == sort:
            self.desc.toggle()
        else:
            self.sort_box.setCurrentIndex(self.sort_box.findData(sort))

    def reset_filters(self) -> None:
        for box in (self.genre_box, self.tag_box, self.state_box):
            box.blockSignals(True)
            box.setCurrentIndex(0)
            box.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh()

    def current_view(self):
        return self.cards if self.pages.currentWidget() is self.cards else self.table

    def selected(self) -> list[dict]:
        view = self.current_view()
        rows = sorted({i.row() for i in view.selectionModel().selectedIndexes()})
        return [self.model.song(r) for r in rows if r < len(self.model.rows)]

    # Acting on songs ---------------------------------------------------------------------------
    def open_current(self) -> None:
        songs = self.selected()
        if len(songs) == 1:
            self.open_song(songs[0])

    def open_song(self, song: dict) -> None:
        file = self.project_file(song)
        if song["project_state"] == "missing" or not file.exists():
            self._say(
                translate(
                    "Library",
                    "Le fichier de ce projet n'est plus dans le dossier de LocalChords "
                    "({parent}). S'il revient, le morceau se rouvre tel quel.",
                ).format(parent=file.parent)
            )
            return
        self.projectRequested.emit(file)

    @staticmethod
    def project_file(song: dict) -> Path:
        return library.data_dir() / "projects" / song["file"]

    def _write(self, fn, *args) -> bool:
        try:
            fn(*args)
            return True
        except C.CatalogError as exc:
            self._say(str(exc))
            return False

    def toggle_favorite(self, songs: list[dict]) -> None:
        on = not all(s["favorite"] for s in songs)
        if self._write(self.catalog.set_favorite, [s["id"] for s in songs], on):
            self.refresh()

    def _song_menu(self, where) -> None:
        songs = self.selected()
        if not songs:
            return
        ids = [s["id"] for s in songs]
        one = songs[0] if len(songs) == 1 else None
        menu = QMenu(self)
        if one:
            menu.addAction(translate("Library", "Ouvrir"), lambda: self.open_song(one))
            menu.addSeparator()
        fav = all(s["favorite"] for s in songs)
        menu.addAction(
            theme.icon("star", theme.ACCENT, 16),
            translate("Library", "Retirer des favoris")
            if fav
            else translate("Library", "Ajouter aux favoris"),
            lambda: self.toggle_favorite(songs),
        )
        self._collections_menu(menu.addMenu(translate("Library", "Ajouter à la collection")), ids)
        if self.view_key[0] == "col":
            cid = self.view_key[1]
            menu.addAction(
                translate("Library", "Retirer de cette collection"),
                lambda: self._remove_from_collection(cid, ids),
            )
            if one:
                menu.addAction(
                    translate("Library", "Monter    Alt + ↑"), lambda: self.move_selected(-1)
                )
                menu.addAction(
                    translate("Library", "Descendre    Alt + ↓"), lambda: self.move_selected(1)
                )
        self._genre_menu(menu.addMenu(translate("Library", "Genre")), songs)
        self._tags_menu(menu.addMenu(translate("Library", "Étiquettes")), songs)
        self._audio_menu(menu.addMenu(translate("Library", "Fichier audio")), songs)
        menu.addSeparator()
        if self.view_key[0] == "hidden":
            menu.addAction(
                translate("Library", "Remettre dans la bibliothèque"),
                lambda: self._hide(ids, False),
            )
        else:
            remove = menu.addAction(
                translate("Library", "Retirer de la bibliothèque"), lambda: self._hide(ids, True)
            )
            remove.setToolTip(
                translate(
                    "Library",
                    "Le morceau n'apparaît plus ; son analyse et son audio restent. Il "
                    "revient s'il est rouvert, ou depuis « Retirés ».",
                )
            )
        menu.addAction(
            translate("Library", "Supprimer l'analyse…"), lambda: self.delete_projects(songs)
        )
        menu.setToolTipsVisible(True)
        menu.exec(where)

    def _collections_menu(self, menu: QMenu, ids: list[str]) -> None:
        for c in self.catalog.collections():
            menu.addAction(c["name"], lambda cid=c["cid"]: self._add_to_collection(cid, ids))
        if not menu.isEmpty():
            menu.addSeparator()
        menu.addAction(
            translate("Library", "Nouvelle collection…"), lambda: self.new_collection(ids)
        )

    def _add_to_collection(self, cid: int, ids: list[str]) -> None:
        if self._write(self.catalog.add_to_collection, cid, ids):
            self.refresh()

    def _remove_from_collection(self, cid: int, ids: list[str]) -> None:
        if self._write(self.catalog.remove_from_collection, cid, ids):
            self.refresh()

    def move_selected(self, delta: int) -> None:
        if self.view_key[0] != "col" or self.sort_box.currentData() != "order":
            return
        songs = self.selected()
        if len(songs) != 1:
            return
        order = self.catalog.members(self.view_key[1])
        i = order.index(songs[0]["id"])
        j = i + delta
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            if self._write(self.catalog.reorder, self.view_key[1], order):
                self.refresh()

    def _genre_menu(self, menu: QMenu, songs: list[dict]) -> None:
        ids = [s["id"] for s in songs]
        one = songs[0] if len(songs) == 1 else None
        file_genre = one["file_genre"] if one else None
        label = (
            translate("Library", "D'après le fichier ({file_genre})").format(file_genre=file_genre)
            if file_genre
            else translate("Library", "D'après le fichier")
        )
        from_file = menu.addAction(label, lambda: self._set_genre(ids, None))
        none = menu.addAction(
            translate("Library", "Non renseigné"), lambda: self._set_genre(ids, "")
        )
        menu.addSeparator()
        known = list(C.GENRES) + [g for g in self.catalog.genres() if g not in C.GENRES]
        current = one["shown_genre"] if one else None
        for g in known:
            action = menu.addAction(translate("Catalog", g), lambda g=g: self._set_genre(ids, g))
            if one and one["genre"] is not None and current == g:
                action.setCheckable(True)
                action.setChecked(True)
        menu.addSeparator()
        menu.addAction(translate("Library", "Autre…"), lambda: self._other_genre(ids))
        if one:
            for action, on in ((from_file, one["genre"] is None), (none, one["genre"] == "")):
                action.setCheckable(True)
                action.setChecked(on)

    def _set_genre(self, ids, genre) -> None:
        if self._write(self.catalog.set_genre, ids, genre):
            self.refresh()

    def _other_genre(self, ids) -> None:
        text, ok = QInputDialog.getText(
            self, translate("Library", "Genre"), translate("Library", "Genre de ces morceaux :")
        )
        if ok and text.strip():
            self._set_genre(ids, text.strip())

    def _tags_menu(self, menu: QMenu, songs: list[dict]) -> None:
        ids = [s["id"] for s in songs]
        tags = sorted(set(C.TAGS) | set(self.catalog.tags()), key=C.folded)
        for tag in tags:
            have = all(C.folded(tag) in {C.folded(t) for t in s["tags"]} for s in songs)
            action = menu.addAction(translate("Catalog", tag))
            action.setCheckable(True)
            action.setChecked(have)
            action.triggered.connect(lambda _=False, t=tag, h=have: self._tag(ids, t, not h))
        menu.addSeparator()
        menu.addAction(translate("Library", "Nouvelle étiquette…"), lambda: self._new_tag(ids))

    def _tag(self, ids, tag: str, on: bool) -> None:
        fn = self.catalog.add_tag if on else self.catalog.remove_tag
        if self._write(fn, ids, tag):
            self.refresh()

    def _new_tag(self, ids) -> None:
        text, ok = QInputDialog.getText(
            self,
            translate("Library", "Nouvelle étiquette"),
            translate("Library", "Étiquette, par exemple « Pour le concert » :"),
        )
        if ok and text.strip():
            self._tag(ids, text.strip(), True)

    def _hide(self, ids, on: bool) -> None:
        if self._write(self.catalog.hide, ids, on):
            self.refresh()

    def drop_songs(self, key: tuple, ids: list[str]) -> None:
        """Songs dragged onto a collection join it at its end; onto Favoris, they are starred."""
        known = self.catalog.ids()
        ids = [i for i in dict.fromkeys(ids) if i in known]
        if not ids:
            return
        if key[0] == "col":
            done = self._write(self.catalog.add_to_collection, key[1], ids)
        else:
            done = self._write(self.catalog.set_favorite, ids, True)
        if done:
            self.refresh()

    # Collections -------------------------------------------------------------------------------
    def new_collection(self, ids: list[str] | None = None) -> None:
        name, ok = QInputDialog.getText(
            self,
            translate("Library", "Nouvelle collection"),
            translate("Library", "Nom de la collection :"),
        )
        if not ok or not name.strip():
            return
        try:
            cid = self.catalog.create_collection(name)
            if ids:
                self.catalog.add_to_collection(cid, ids)
        except C.CatalogError as exc:
            self._say(str(exc))
            return
        if ids:
            self.refresh()
        else:
            self.select_view(("col", cid))
            self.sort_box.setCurrentIndex(self.order_index)

    def _side_menu(self, pos) -> None:
        item = self.side.itemAt(pos)
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not key or key[0] != "col":
            return
        menu = QMenu(self)
        menu.addAction(translate("Library", "Renommer…"), lambda: self._rename_collection(item))
        menu.addAction(
            translate("Library", "Supprimer la collection…"),
            lambda: self._delete_collection(key[1], item.text()),
        )
        menu.exec(self.side.viewport().mapToGlobal(pos))

    def _rename_collection(self, item) -> None:
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not key or key[0] != "col":
            return
        name, ok = QInputDialog.getText(
            self,
            translate("Library", "Renommer la collection"),
            translate("Library", "Nouveau nom :"),
            text=item.text(),
        )
        changed = ok and name.strip() and name.strip() != item.text()
        if changed and self._write(self.catalog.rename_collection, key[1], name):
            self.refresh()

    def _delete_collection(self, cid: int, name: str) -> None:
        if self._confirm(
            translate("Library", "Supprimer la collection"),
            translate(
                "Library",
                "Supprimer la collection « {name} » ?\n\nSes morceaux restent dans la "
                "bibliothèque, avec leurs analyses et leurs fichiers audio.",
            ).format(name=name),
            translate("Library", "Supprimer la collection"),
        ) and self._write(self.catalog.delete_collection, cid):
            self.refresh()

    # The audio ---------------------------------------------------------------------------------
    def _audio_menu(self, menu: QMenu, songs: list[dict]) -> None:
        one = songs[0] if len(songs) == 1 else None
        can_keep = [s for s in songs if s["audio_state"] == "ok"]
        if can_keep:
            size = sum(s["audio_size"] or 0 for s in can_keep)
            text = translate("Library", "Conserver une copie dans la bibliothèque")
            menu.addAction(text + (f" ({megabytes(size)})" if size else "") + "…",
                           lambda: self.keep_copies(can_keep))  # fmt: skip
        lost = [s for s in songs if s["audio_state"] in ("missing", "offline")]
        if one and one["project_state"] == "ok":
            menu.addAction(translate("Library", "Localiser le fichier…"), lambda: self.locate(one))
        if lost:
            menu.addAction(
                translate("Library", "Rechercher dans un dossier…"),
                lambda: self.find_in_folder(lost),
            )
        kept = [s for s in songs if s["kept"]]
        if kept:
            menu.addAction(
                translate("Library", "Supprimer la copie conservée…"),
                lambda: self.drop_copies(kept),
            )
        if one:
            path = library.audio_file({"path": one["audio_path"], "kept": one["kept"]})
            show = menu.addAction(
                translate("Library", "Afficher dans l'Explorateur"), lambda: self._reveal(path)
            )
            show.setEnabled(one["audio_state"] in ("ok", "kept"))
        if menu.isEmpty():
            menu.setEnabled(False)

    def _edit_project(self, song: dict, change) -> tuple[Path, Project] | None:
        """Load a song's project, change it, save it, index it; None (said) when it fails."""
        file = self.project_file(song)
        try:
            project = Project.load(file)
            change(project)
            project.save(file)
            self.catalog.store(file, project)
        except (ProjectError, OSError, C.CatalogError) as exc:
            self._say(
                translate("Library", "« {title} » n'a pas pu être modifié : {exc}").format(
                    title=song["title"], exc=exc
                )
            )
            return None
        self.audioChanged.emit(file, dict(project.audio))
        return file, project

    def keep_copies(self, songs: list[dict]) -> None:
        sizes = []
        for s in songs:
            try:
                sizes.append(Path(s["audio_path"]).stat().st_size)
            except OSError:
                sizes.append(0)
        total = sum(sizes)
        where = library.data_dir() / "audio"
        free = library.free_mb(library.data_dir()) * 2**20
        what = (
            translate("Library", "« {title} »").format(title=songs[0]["title"])
            if len(songs) == 1
            else translate("Library", "ces {count} morceaux").format(count=len(songs))
        )
        text = translate(
            "Library",
            "Garder une copie de l'audio de {what} dans le dossier de LocalChords "
            "?\n\nPlace nécessaire : {megabytes} (libre : {megabytes2}), dans "
            "{where}.\n\nLe fichier d'origine n'est ni déplacé ni supprimé. La copie "
            "permet de rejouer le morceau même si l'original disparaît, et suit le "
            "dossier Data en mode portable.",
        ).format(what=what, megabytes=megabytes(total), megabytes2=megabytes(free), where=where)
        if not self._confirm(
            translate("Library", "Conserver une copie"), text, translate("Library", "Copier")
        ):
            return

        def work(progress, stop):
            done, errors = [], []
            for i, s in enumerate(songs):
                if stop():
                    break
                progress(
                    translate("Library", "Copie de « {title} »… ({number} sur {count})").format(
                        title=s["title"], number=i + 1, count=len(songs)
                    ),
                    i / len(songs),
                )
                file = self.project_file(s)
                try:
                    project = Project.load(file)
                    source = Path(project.audio.get("path") or "")
                    fp = project.audio.get("fingerprint") or audio.fingerprint(source)
                    project.audio["kept"] = library.keep_copy(source, fp)
                    project.save(file)
                    done.append((file, project))
                except (library.KeepError, ProjectError, OSError) as exc:
                    errors.append(f"{s['title']} : {exc}")
            return done, errors

        done, errors = run_task(self, translate("Library", "Conserver une copie"), work)
        self._stored(done)
        if errors:
            self._say(
                translate("Library", "Certaines copies n'ont pas été faites :\n\n{errors}").format(
                    errors="\n".join(errors)
                )
            )

    def _stored(self, done: list[tuple[Path, Project]]) -> None:
        for file, project in done:
            with contextlib.suppress(OSError, C.CatalogError):
                self.catalog.store(file, project)
            self.audioChanged.emit(file, dict(project.audio))
        self.refresh()

    def drop_copies(self, songs: list[dict]) -> None:
        alone = [s for s in songs if not Path(s["audio_path"]).is_file()
                 or library.managed(Path(s["audio_path"]))]  # fmt: skip
        what = (
            translate("Library", "« {title} »").format(title=songs[0]["title"])
            if len(songs) == 1
            else translate("Library", "de {count} morceaux").format(count=len(songs))
        )
        text = translate(
            "Library",
            "Supprimer la copie audio conservée {what} ? Elle part à la "
            "Corbeille.\n\nLes fichiers d'origine ne sont pas touchés, ni l'analyse.",
        ).format(what=what)
        if alone:
            text += translate(
                "Library",
                "\n\nAttention : pour %n d'entre eux l'original est introuvable. Sans "
                "la copie, ils ne pourront plus être écoutés (la grille reste).",
                None,
                len(alone),
            )
        if not self._confirm(
            translate("Library", "Supprimer la copie conservée"),
            text,
            translate("Library", "Supprimer la copie"),
        ):
            return
        failed = []
        for s in songs:
            copy = library.data_dir() / s["kept"]
            if copy.exists() and (not library.managed(copy) or not trash(copy)):
                failed.append(s["title"])
                continue
            self._edit_project(s, lambda p: p.audio.pop("kept", None))
        self.refresh()
        if failed:
            self._say(
                translate(
                    "Library", "Ces copies n'ont pas pu être mises à la Corbeille : {files}"
                ).format(files=", ".join(failed))
            )

    def locate(self, song: dict) -> None:
        start = Path(song["audio_path"]).parent
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate("Library", "Où est « {title} » ?").format(title=song["title"]),
            str(start) if start.is_dir() else "",
            translate("Library", "Audio ({patterns})").format(
                patterns=" ".join(f"*{e}" for e in audio.AUDIO_EXTENSIONS)
            ),
        )
        if not path:
            return
        file = self.project_file(song)
        try:
            wanted = Project.load(file).audio.get("fingerprint")
            same = audio.fingerprint(Path(path)) == wanted
        except (ProjectError, OSError):
            same = False
        if not same:
            self._say(
                translate(
                    "Library",
                    "Ce fichier n'est pas l'enregistrement analysé : son contenu diffère. Il "
                    "n'est pas associé, pour que la grille ne tombe pas sur un autre "
                    "morceau.\n\nPour l'utiliser quand même, ouvrez le morceau puis « "
                    "Localiser le fichier… ».",
                )
            )
            return
        self._edit_project(song, lambda p: p.audio.__setitem__("path", str(Path(path))))
        self.refresh()

    def find_in_folder(self, songs: list[dict] | None) -> None:
        """Look for moved recordings in a folder the user picks, and nowhere else."""
        if songs is None:
            lost = ("missing", "offline")
            songs = [s for s in self.catalog.songs()
                     if s["audio_state"] in lost and s["project_state"] == "ok"]  # fmt: skip
        if not songs:
            self._say(
                translate(
                    "Library",
                    "Aucun fichier audio n'est introuvable : tous les morceaux se jouent.",
                )
            )
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            translate(
                "Library",
                "Dans quel dossier chercher (%n fichier(s) manquant(s)) ?",
                None,
                len(songs),
            ),
        )
        if not folder:
            return
        wanted = []
        for s in songs:
            try:
                fp = Project.load(self.project_file(s)).audio.get("fingerprint")
            except ProjectError:
                continue
            if fp:
                wanted.append({"id": s["id"], "fingerprint": fp, "name": Path(s["audio_path"]).name,
                               "size": s["audio_size"]})  # fmt: skip

        def work(progress, stop):
            def seen(n, root):
                progress(
                    translate("Library", "{n} fichiers examinés… {root}").format(n=n, root=root)
                )

            return library.find_moved(Path(folder), wanted, stop=stop, progress=seen)

        found = run_task(self, translate("Library", "Rechercher les fichiers audio"), work)
        by_id = {s["id"]: s for s in songs}
        for sid, path in found.items():
            self._edit_project(
                by_id[sid], lambda p, path=path: p.audio.__setitem__("path", str(path))
            )
        self.refresh()
        if found:
            self._say(
                translate(
                    "Library",
                    "%n fichier(s) retrouvé(s) sur {total} dans {folder}.",
                    None,
                    len(found),
                ).format(total=len(wanted), folder=folder),
                info=True,
            )
        else:
            self._say(
                translate(
                    "Library",
                    "Aucun des fichiers manquants n'est dans {folder} ni ses sous-dossiers. "
                    "Seul ce dossier a été examiné.",
                ).format(folder=folder),
                info=True,
            )

    def _reveal(self, path: Path) -> None:
        try:
            if path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603, S607
            elif path.is_dir():
                subprocess.Popen(["explorer", str(path)])  # noqa: S603, S607
        except OSError as exc:
            self._say(translate("Library", "L'Explorateur ne s'ouvre pas : {exc}").format(exc=exc))

    # Deleting ----------------------------------------------------------------------------------
    def _ask_delete(self, songs: list[dict], managed: list[dict]) -> bool | None:
        """None to cancel, else whether LocalChords' own copies of the audio go too."""
        what = (
            translate("Library", "de « {title} »").format(title=songs[0]["title"])
            if len(songs) == 1
            else translate("Library", "de {count} morceaux").format(count=len(songs))
        )
        box = QMessageBox(self)
        box.setWindowTitle(translate("Library", "Supprimer l'analyse"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            translate(
                "Library",
                "Supprimer l'analyse {what} ?\n\nAccords, corrections, positions et "
                "paroles partent à la Corbeille, et le morceau quitte la bibliothèque, "
                "ses collections et ses favoris. Les fichiers audio d'origine ne sont "
                "jamais supprimés.",
            ).format(what=what)
        )
        also = None
        if managed:
            size = sum(s["audio_size"] or 0 for s in managed)
            also = QCheckBox(
                translate(
                    "Library",
                    "Mettre aussi à la Corbeille l'audio gardé par LocalChords ({megabytes})",
                ).format(megabytes=megabytes(size))
            )
            box.setCheckBox(also)
        delete = box.addButton(
            translate("Library", "Supprimer l'analyse"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not delete:
            return None
        return also is not None and also.isChecked()

    def delete_projects(self, songs: list[dict]) -> None:
        managed = [s for s in songs if library.managed(library.audio_file(
            {"path": s["audio_path"], "kept": s["kept"]}))]  # fmt: skip
        answer = self._ask_delete(songs, managed)
        if answer is None:
            return
        also_audio = answer
        failed, gone = [], []
        for s in songs:
            file = self.project_file(s)
            if file.exists() and not trash(file):
                failed.append(s["title"])
                continue
            if also_audio:
                copy = library.audio_file({"path": s["audio_path"], "kept": s["kept"]})
                if library.managed(copy) and copy.is_file():
                    trash(copy)
            with contextlib.suppress(C.CatalogError):
                self.catalog.forget(s["id"])
            gone.append(file)
        self.projectsReplaced.emit(gone)
        self.refresh()
        if failed:
            self._say(
                translate(
                    "Library",
                    "Ces analyses n'ont pas pu être mises à la Corbeille, elles restent : {files}",
                ).format(files=", ".join(failed))
            )

    # Backups -----------------------------------------------------------------------------------
    def _task_catalog(self):
        """A connection for another thread; the same catalog when it lives in memory."""
        if self.catalog.path == ":memory:":
            return self.catalog, False
        return C.Catalog(self.catalog.path), True

    def backup(self) -> None:
        dialog = BackupDialog(self.catalog, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = translate("Library", "LocalChords - bibliothèque {strftime}.zip").format(
            strftime=time.strftime("%Y-%m-%d")
        )
        start = self.settings.get("backup_folder") or str(Path.home() / "Documents")
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("Library", "Enregistrer la sauvegarde"),
            str(Path(start) / name),
            translate("Library", "Sauvegarde (*.zip)"),
        )
        if not path:
            return
        target = Path(path)
        if library.data_dir() in target.resolve().parents:
            self._say(
                translate(
                    "Library",
                    "Choisissez un autre dossier que celui de LocalChords : une sauvegarde "
                    "sert justement si ce dossier est perdu.",
                )
            )
            return
        self.remember("backup_folder", str(target.parent))
        with_audio, lyrics = dialog.audio.isChecked(), dialog.lyrics.isChecked()

        def work(progress, stop):
            catalog, own = self._task_catalog()
            try:
                return backup.write(
                    target,
                    catalog,
                    with_audio=with_audio,
                    catalog_lyrics=lyrics,
                    stop=stop,
                    progress=lambda i, n, what: progress(
                        translate("Library", "{i} sur {n} : {what}").format(i=i, n=n, what=what),
                        i / max(1, n),
                    ),
                )
            finally:
                if own:
                    catalog.close()

        try:
            manifest = run_task(self, translate("Library", "Sauvegarder la bibliothèque"), work)
        except backup.BackupError as exc:
            self._say(str(exc))
            return
        size = megabytes(target.stat().st_size)
        text = translate(
            "Library",
            "Sauvegarde enregistrée : {target}\n\n{projects} analyses, {audio} "
            "fichiers audio, {size}. Gardez-la ailleurs que sur ce disque (clé USB, "
            "autre disque). C'est une copie privée : ne la partagez pas.",
        ).format(target=target, projects=manifest["projects"], audio=manifest["audio"], size=size)
        if manifest.get("left_out"):
            text += translate(
                "Library",
                "\n\n%n analyse(s) illisible(s) n'y sont pas : leurs paroles ne "
                "pouvaient pas être vérifiées. Pour les inclure, cochez « Inclure les "
                "paroles venues du catalogue en ligne ».",
                None,
                len(manifest["left_out"]),
            )
        self._say(text, info=True)

    def restore(self) -> None:
        start = self.settings.get("backup_folder") or str(Path.home() / "Documents")
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate("Library", "Restaurer une sauvegarde"),
            start,
            translate("Library", "Sauvegarde (*.zip)"),
        )
        if not path:
            return
        archive = Path(path)
        try:
            plan = backup.inspect(archive)
        except backup.BackupError as exc:
            self._say(str(exc))
            return
        dialog = RestoreDialog(plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        take_newer, settings = dialog.newer.isChecked(), dialog.settings.isChecked()

        def work(progress, stop):
            catalog, own = self._task_catalog()
            try:
                return backup.restore(
                    archive,
                    catalog,
                    take_newer=take_newer,
                    settings=settings,
                    progress=lambda i, n, what: progress(
                        translate("Library", "{i} sur {n}").format(i=i, n=n), i / max(1, n)
                    ),
                )
            finally:
                if own:
                    catalog.close()

        folder = library.data_dir() / "projects"
        replaced = plan["new"] + [s for s in plan["differ"] if take_newer and s in plan["newer"]]
        # The song open in the window is not saved over what the restore writes, even meanwhile.
        self.projectsReplaced.emit([folder / f"{s}.lchords" for s in replaced])
        try:
            report = run_task(
                self, translate("Library", "Restaurer la bibliothèque"), work, cancellable=False
            )
        except (backup.BackupError, C.CatalogError) as exc:
            self._say(str(exc))
            self.start_scan()
            return
        if settings:
            self.settingsRestored.emit()
        self.start_scan()
        text = translate(
            "Library",
            "Restauration terminée : {written} analyses écrites, {same} déjà "
            "présentes, {audio} fichiers audio.",
        ).format(written=report["written"], same=report["same"], audio=report["audio"])
        if report["set_aside"]:
            text += translate(
                "Library",
                "\n\n{set_aside} morceaux différaient : la version non retenue est gardée, "
                "rien n'est perdu :\n{aside_folder}",
            ).format(set_aside=report["set_aside"], aside_folder=report["aside_folder"])
        self._say(text, info=True)

    # Messages ----------------------------------------------------------------------------------
    def _say(self, text: str, info: bool = False) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("LocalChords")
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information if info else QMessageBox.Icon.Warning)
        box.exec()

    def _confirm(self, title: str, text: str, yes: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        ok = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is ok


class BackupDialog(QDialog):
    def __init__(self, catalog: C.Catalog, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Library", "Sauvegarder la bibliothèque"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        size = backup.estimate(catalog, with_audio=True)
        lead = QLabel(
            translate(
                "Library",
                "Un seul fichier .zip réunit vos {projects} analyses (accords, "
                "corrections, positions, paroles), vos favoris, genres, étiquettes, "
                "collections et préférences, pour les retrouver après une réinstallation "
                "ou sur un autre PC.\n\nC'est une copie privée, pour vous : ce n'est pas "
                "un moyen de partager des morceaux.",
            ).format(projects=size["projects"])
        )
        lead.setWordWrap(True)
        layout.addWidget(lead)
        self.audio = QCheckBox(
            translate(
                "Library",
                "Inclure les fichiers audio ({audio} fichiers, environ {megabytes} de plus)",
            ).format(audio=size["audio"], megabytes=megabytes(size["audio_bytes"]))
        )
        self.audio.setEnabled(size["audio"] > 0)
        layout.addWidget(self.audio)
        if size["without_audio"]:
            note = QLabel(
                translate(
                    "Library",
                    "{without_audio} morceaux n'ont pas d'audio disponible : seule leur "
                    "analyse est sauvegardée.",
                ).format(without_audio=size["without_audio"])
            )
            note.setObjectName("caption")
            note.setWordWrap(True)
            layout.addWidget(note)
        self.lyrics = QCheckBox(
            translate("Library", "Inclure les paroles venues du catalogue en ligne (LRCLIB)")
        )
        self.lyrics.setChecked(True)
        lyrics_note = QLabel(
            translate(
                "Library",
                "Elles restent réservées à votre usage : une fois restaurées, "
                "LocalChords ne les exporte toujours pas. Décochez si la sauvegarde doit "
                "quitter votre ordinateur pour quelqu'un d'autre.",
            )
        )
        lyrics_note.setObjectName("caption")
        lyrics_note.setWordWrap(True)
        has_catalog = any(s["lyrics"] == "catalog" for s in catalog.songs())
        self.lyrics.setVisible(has_catalog)
        lyrics_note.setVisible(has_catalog)
        layout.addWidget(self.lyrics)
        layout.addWidget(lyrics_note)
        self.total = QLabel()
        self.total.setObjectName("muted")
        layout.addWidget(self.total)

        def update_total():
            n = size["project_bytes"] + (size["audio_bytes"] if self.audio.isChecked() else 0)
            self.total.setText(
                translate("Library", "Taille estimée : {megabytes}").format(megabytes=megabytes(n))
            )

        self.audio.toggled.connect(update_total)
        update_total()
        buttons = QDialogButtonBox()
        buttons.addButton(
            translate("Library", "Choisir où l'enregistrer…"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class RestoreDialog(QDialog):
    def __init__(self, plan: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Library", "Restaurer une sauvegarde"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        m = plan["manifest"]
        made = (
            day(m.get("created_at"))
            if m.get("created_at")
            else translate("Library", "date inconnue")
        )
        lines = [
            translate("Library", "Sauvegarde du {made} ({program}).").format(
                made=made, program=m.get("program", "LocalChords")
            ),
            "",
            translate(
                "Library",
                "• %n analyses nouvelles sur ce PC seront ajoutées ;",
                None,
                len(plan["new"]),
            ),
            translate(
                "Library",
                "• %n sont déjà là, identiques : rien ne change ;",
                None,
                len(plan["same"]),
            ),
            translate(
                "Library", "• %n existent ici avec un autre contenu.", None, len(plan["differ"])
            ),
            "",
            translate(
                "Library",
                "Favoris, étiquettes et collections s'ajoutent à ceux d'ici, sans "
                "doublon. Rien de ce PC n'est écrasé sans être gardé.",
            ),
        ]
        text = QLabel("\n".join(lines))
        text.setWordWrap(True)
        layout.addWidget(text)
        self.newer = QCheckBox(
            translate(
                "Library",
                "Pour ceux qui diffèrent, prendre la version la plus récente (%n dans "
                "la sauvegarde)",
                None,
                len(plan["newer"]),
            )
        )
        self.newer.setVisible(bool(plan["differ"]))
        layout.addWidget(self.newer)
        note = QLabel(
            translate(
                "Library",
                "Sinon la version de ce PC reste. Dans les deux cas, l'autre version est "
                "gardée dans le dossier « restored » de LocalChords.",
            )
        )
        note.setObjectName("caption")
        note.setWordWrap(True)
        note.setVisible(bool(plan["differ"]))
        layout.addWidget(note)
        self.settings = QCheckBox(
            translate("Library", "Reprendre aussi les préférences de la sauvegarde")
        )
        layout.addWidget(self.settings)
        buttons = QDialogButtonBox()
        buttons.addButton(translate("Library", "Restaurer"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
