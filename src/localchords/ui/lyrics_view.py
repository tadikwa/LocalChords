"""The lyrics on screen: a sheet with the chords over the words, a strip over the grid, and the
page that gets them (a file, the online catalog, a transcription) and corrects them.

The layout (lay_out, paint) is the one the PDF prints: lyrics.layout cuts each line at its words
and chords, so a chord stays over its letter at any size, on screen as on paper.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import audio, export, identify, library, lyrics_online, transcribe
from .. import lyrics as L
from . import theme
from .widgets import ElidedLabel, Stepper, fmt_time

MODES = {
    "grid": "Grille seule",
    "strip": "Grille et paroles",
    "lyrics": "Paroles",
    "sheet": "Paroles et accords",
}
SIZES = (12, 48)
MANUAL_SCROLL_PAUSE = 5.0  # seconds without following after the user scrolls by hand
NOT_EXPORTABLE = (
    "Paroles d'un catalogue en ligne : consultables ici, mais pas exportables. Saisissez, "
    "importez ou transcrivez vos propres paroles pour les exporter."
)


# Layout, shared with the PDF ---------------------------------------------------------------------


class Fonts:
    def __init__(self, size: float):
        self.size = size
        self.text = theme.app_font(size)
        self.chord = theme.app_font(size * 0.92, 700)
        self.approx = QFont(self.chord)
        self.approx.setItalic(True)
        self.section = theme.app_font(size * 0.72, 700)
        self.section.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        self.tm = QFontMetricsF(self.text)
        self.cm = QFontMetricsF(self.chord)
        self.am = QFontMetricsF(self.approx)
        self.sm = QFontMetricsF(self.section)
        self.text_h = self.tm.height() * 1.15
        self.chord_h = self.cm.height() * 1.02
        self.gap = size * 0.6

    def chord_w(self, label: str) -> float:
        return max(self.cm.horizontalAdvance(label), self.am.horizontalAdvance(label))


@dataclass
class Line:
    """One visual line: a row of the sheet can wrap into several."""

    row: int
    kind: str
    runs: list  # (x, text, first char)
    chords: list  # (x, chord dict)
    h: float
    chord_h: float  # room above the words for the names
    gap: float  # space before it
    y: float = 0.0


def lay_out(rows: list[dict], width: float, f: Fonts, chords_on: bool) -> list[Line]:
    out: list[Line] = []
    for r, row in enumerate(rows):
        kind = row["kind"]
        chords = row["chords"] if chords_on else []
        if kind == "section":
            out.append(
                Line(
                    r,
                    kind,
                    [(0.0, row["text"].upper(), 0)],
                    [],
                    f.sm.height() * 1.4,
                    0.0,
                    f.size * 0.9,
                )
            )
        elif kind == "break":
            out.append(Line(r, kind, [], [], f.size * 0.6, 0.0, 0.0))
        elif kind == "chords":
            if not chords:
                continue
            x, lines = 0.0, [[]]
            for c in chords:
                w = f.chord_w(c["label"])
                if x > 0 and x + w > width:
                    lines.append([])
                    x = 0.0
                lines[-1].append((x, c))
                x += w + f.gap * 2
            for k, placed in enumerate(lines):
                out.append(
                    Line(
                        r,
                        kind,
                        [],
                        placed,
                        f.chord_h + f.size * 0.3,
                        f.chord_h,
                        f.size * 0.25 if k == 0 else 0.0,
                    )
                )
        else:
            visual = L.layout(row["text"], chords, width, f.tm.horizontalAdvance, f.chord_w, f.gap)
            for k, v in enumerate(visual):
                room = f.chord_h if v["chords"] else 0.0
                gap = (f.size * 0.25 if chords_on else f.size * 0.1) if k == 0 else 0.0
                placed = [(x, chords[n]) for x, n in v["chords"]]
                out.append(Line(r, kind, v["runs"], placed, room + f.text_h, room, gap))
    return out


def stack(lines: list[Line], top: float = 0.0) -> float:
    """Gives each line its place from the top; returns the bottom."""
    y = top
    for ln in lines:
        y += ln.gap
        ln.y = y
        y += ln.h
    return y


SCREEN_COLORS = {
    "text": theme.TEXT,
    "text_now": theme.TEXT,
    "chord": theme.SELECT,
    "approx": theme.TEXT_2,
    "manual": theme.EDITED,
    "now": theme.ACCENT,
    "section": theme.ACCENT,
}


def paint(
    p: QPainter,
    lines: list[Line],
    f: Fonts,
    colors: dict,
    *,
    x0: float = 0.0,
    now_row=None,
    now_key=None,
    clip: QRectF | None = None,
) -> None:
    for ln in lines:
        if clip is not None and (ln.y + ln.h < clip.top() or ln.y > clip.bottom()):
            continue
        if ln.kind == "section":
            p.setFont(f.section)
            p.setPen(QColor(colors["section"]))
            p.drawText(QPointF(x0, ln.y + f.sm.ascent() + f.sm.height() * 0.2), ln.runs[0][1])
            continue
        for x, c in ln.chords:
            approx = c["how"] in ("approx", "held")
            if c["key"] == now_key:
                color = colors["now"]
            elif c["how"] == "manual":
                color = colors["manual"]
            else:
                color = colors["approx"] if approx else colors["chord"]
            p.setFont(f.approx if approx else f.chord)
            p.setPen(QColor(color))
            p.drawText(QPointF(x0 + x, ln.y + f.cm.ascent()), c["label"])
        if ln.runs:
            p.setFont(f.text)
            p.setPen(QColor(colors["text_now"] if ln.row == now_row else colors["text"]))
            base = ln.y + ln.chord_h + f.tm.ascent()
            for x, piece, _ in ln.runs:
                p.drawText(QPointF(x0 + x, base), piece)


# The sheet --------------------------------------------------------------------------------------


class LyricsSheet(QWidget):
    """The lyrics, with or without the chords; a click on a line plays from it, a chord name
    dragged onto a letter moves it there (the harmony does not change)."""

    seekRequested = Signal(float)
    chordMoved = Signal(str, int, int)  # chord key, line, character
    chordReset = Signal(str)
    lineAction = Signal(int, str)  # line, what to do with its time
    linePicked = Signal(int)
    sizeStep = Signal(int)
    interacted = Signal()

    MARGIN = 28

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.setMouseTracking(True)
        self.rows: list[dict] = []
        self.lines: list[Line] = []
        self.size = 20
        self.chords_on = True
        self.now_row: int | None = None
        self.now_key: str | None = None
        self.picked_row: int | None = None
        self.player_position = lambda: 0.0
        self._drag: dict | None = None
        self._width = -1
        self.f = Fonts(self.size)

    def set_rows(self, rows: list[dict], size: int, chords_on: bool) -> None:
        self.rows, self.size, self.chords_on = rows, size, chords_on
        if self.picked_row is not None and self.picked_row >= len(rows):
            self.picked_row = None
        self._relayout()

    def _relayout(self) -> None:
        self.f = Fonts(self.size)
        self._width = self.width()
        self.lines = lay_out(
            self.rows, max(120.0, self.width() - 2 * self.MARGIN), self.f, self.chords_on
        )
        bottom = stack(self.lines, self.MARGIN * 0.6)
        # Room under the last line, so that it can still come up to where the eye reads.
        self.setMinimumHeight(int(bottom + 240))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != self._width:
            self._relayout()

    def set_now(self, row: int | None, key: str | None) -> None:
        if (row, key) != (self.now_row, self.now_key):
            self.now_row, self.now_key = row, key
            self.update()

    def row_rect(self, row: int | None) -> QRectF | None:
        mine = [ln for ln in self.lines if ln.row == row]
        if not mine:
            return None
        top, bottom = mine[0].y, mine[-1].y + mine[-1].h
        return QRectF(0, top, self.width(), bottom - top)

    def row_of_line(self, line: int) -> int | None:
        return next((r for r, x in enumerate(self.rows) if x["line"] == line), None)

    # Drawing
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(event.rect(), QColor(theme.BG))
        for row, color, fill in (
            (self.now_row, theme.ACCENT, theme.SURFACE_2),
            (self.picked_row, theme.SELECT, None),
        ):
            rect = self.row_rect(row)
            if rect is None:
                continue
            band = rect.adjusted(self.MARGIN * 0.4, -4, -self.MARGIN * 0.4, 4)
            if fill:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(fill))
                p.drawRoundedRect(band, 8, 8)
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(band.left(), band.top() + 6, 3, band.height() - 12), 1, 1)
            else:
                p.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(band, 8, 8)
        colors = dict(SCREEN_COLORS)
        if not self.chords_on:
            colors["text"] = theme.TEXT_2
        paint(
            p,
            self.lines,
            self.f,
            colors,
            x0=self.MARGIN,
            now_row=self.now_row,
            now_key=self.now_key,
            clip=QRectF(event.rect()),
        )
        if self._drag and self._drag["moved"]:
            target = self._drag.get("target")
            if target:
                x, y = target[2], target[3]
                p.setPen(QPen(QColor(theme.EDITED), 2))
                p.drawLine(QPointF(x, y), QPointF(x, y + self.f.chord_h + self.f.text_h))
            pos = self._drag["pos"]
            p.setFont(self.f.chord)
            p.setPen(QColor(theme.EDITED))
            p.drawText(QPointF(pos.x() + 6, pos.y() - 6), self._drag["chord"]["label"])
        p.end()

    # Finding what is under the mouse
    def _line_at(self, y: float) -> Line | None:
        return next((ln for ln in self.lines if ln.y - ln.gap <= y < ln.y + ln.h), None)

    def _chord_at(self, pos) -> dict | None:
        ln = self._line_at(pos.y())
        if ln is None or pos.y() > ln.y + ln.chord_h:
            return None
        for x, c in ln.chords:
            left = self.MARGIN + x
            if left - 4 <= pos.x() <= left + self.f.chord_w(c["label"]) + 4:
                return c
        return None

    def _target(self, pos) -> tuple | None:
        """(line, character, x, y) where a chord dropped here would go."""
        ln = self._line_at(pos.y())
        if ln is None or ln.kind != "line" or not ln.runs:
            return None
        char = L.char_at(ln.runs, pos.x() - self.MARGIN, self.f.tm.horizontalAdvance)
        text = self.rows[ln.row]["text"]
        start = next(first for _x, _piece, first in reversed(ln.runs) if first <= char)
        run = next(r for r in ln.runs if r[2] == start)
        x = self.MARGIN + run[0] + self.f.tm.horizontalAdvance(text[start:char])
        return self.rows[ln.row]["line"], char, x, ln.y

    # Mouse
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.interacted.emit()
        chord = self._chord_at(event.position()) if self.chords_on else None
        self._drag = {
            "chord": chord,
            "start": event.position(),
            "pos": event.position(),
            "moved": False,
        }

    def mouseMoveEvent(self, event):
        pos = event.position()
        drag = self._drag
        if drag and drag["chord"] is not None:
            if (pos - drag["start"]).manhattanLength() > 5:
                drag["moved"] = True
            drag["pos"] = pos
            drag["target"] = self._target(pos)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return
        if self._chord_at(pos) and self.chords_on:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            ln = self._line_at(pos.y())
            timed = ln is not None and self._start_of(ln.row) is not None
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if timed else Qt.CursorShape.ArrowCursor
            )

    def mouseReleaseEvent(self, event):
        drag, self._drag = self._drag, None
        self.unsetCursor()
        if not drag or event.button() != Qt.MouseButton.LeftButton:
            return
        chord = drag["chord"]
        if chord is not None and drag["moved"]:
            target = drag.get("target")
            if target:
                self.chordMoved.emit(chord["key"], target[0], target[1])
            self.update()
            return
        if chord is not None:
            self.seekRequested.emit(chord["time"])
            return
        ln = self._line_at(event.position().y())
        if ln is None:
            return
        row = self.rows[ln.row]
        if row["line"] is not None and row["kind"] == "line":
            self.picked_row = ln.row
            self.linePicked.emit(row["line"])
            self.update()
        start = self._start_of(ln.row)
        if start is not None:
            self.seekRequested.emit(start)

    def _start_of(self, row: int) -> float | None:
        r = self.rows[row]
        if r["start"] is not None:
            return r["start"]
        return r["chords"][0]["time"] if r["kind"] == "chords" and r["chords"] else None

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.sizeStep.emit(1 if event.angleDelta().y() > 0 else -1)
            return
        self.interacted.emit()
        super().wheelEvent(event)

    def contextMenuEvent(self, event):
        self.interacted.emit()
        pos = QPointF(event.pos())
        menu = QMenu(self)
        chord = self._chord_at(pos) if self.chords_on else None
        if chord is not None:
            menu.addAction(
                f"Aller à {chord['label']} ({fmt_time(chord['time'])})",
                lambda: self.seekRequested.emit(chord["time"]),
            )
            reset = menu.addAction(
                "Replacer automatiquement", lambda: self.chordReset.emit(chord["key"])
            )
            reset.setEnabled(chord["how"] == "manual")
            menu.addSeparator()
            hint = menu.addAction("Glissez le nom de l'accord sur un mot pour le déplacer")
            hint.setEnabled(False)
        else:
            ln = self._line_at(pos.y())
            row = self.rows[ln.row] if ln is not None else None
            if row is None or row["line"] is None or row["kind"] != "line":
                return
            line, start = row["line"], row["start"]
            if start is not None:
                menu.addAction(
                    f"Lire depuis cette ligne ({fmt_time(start)})",
                    lambda: self.seekRequested.emit(start),
                )
            menu.addAction(
                f"Faire commencer la ligne ici ({fmt_time(self.player_position())})",
                lambda: self.lineAction.emit(line, "here"),
            )
            for text, action in (
                ("Commencer 0,1 s plus tôt", "earlier"),
                ("Commencer 0,1 s plus tard", "later"),
                ("Retirer l'horodatage de la ligne", "clear"),
            ):
                item = menu.addAction(text, lambda a=action: self.lineAction.emit(line, a))
                item.setEnabled(start is not None)
        menu.exec(event.globalPos())


class LyricsStrip(QWidget):
    """Over the grid: the line being sung and the next one, so the grid keeps its room."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)
        self.now = ""
        self.next = ""

    def set_lines(self, now: str, next_: str) -> None:
        if (now, next_) != (self.now, self.next):
            self.now, self.next = now, next_
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.SURFACE))
        p.setPen(QColor(theme.BORDER))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        width = self.width() - 32
        for text, font, color, y in (
            (self.now or "…", theme.app_font(20, 600), theme.TEXT, 8),
            (self.next, theme.app_font(14), theme.TEXT_2, 38),
        ):
            p.setFont(font)
            p.setPen(QColor(color))
            m = QFontMetricsF(font)
            p.drawText(
                QPointF(16, y + m.ascent()), m.elidedText(text, Qt.TextElideMode.ElideRight, width)
            )
        p.end()


class LyricsPrompt(QWidget):
    """One thin line for a song without lyrics: what can be done, or what was found. The grid
    keeps its room; the cross hides it for this song."""

    def __init__(self):
        super().__init__()
        self.setObjectName("bar")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 2, 8, 2)
        row.setSpacing(2)
        self.text = ElidedLabel()
        self.text.setObjectName("caption")
        row.addWidget(self.text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(0)
        row.addLayout(self.actions)
        self.close = QToolButton()
        self.close.setObjectName("step")
        self.close.setIcon(theme.icon("close", size=12))
        self.close.setToolTip("Masquer pour ce morceau")
        self.close.setAccessibleName("Masquer l'invitation aux paroles pour ce morceau")
        row.addWidget(self.close)
        self.buttons: list[QPushButton] = []
        self._fns: list = []
        self.hide()

    def show_state(self, text: str, actions: list[tuple[str, object]]) -> None:
        self.text.set_full_text(text)
        self._fns = [fn for _label, fn in actions]
        if [b.text() for b in self.buttons] == [label for label, _fn in actions]:
            return  # the same buttons: kept, so a click under way is not lost
        while self.actions.count():
            item = self.actions.takeAt(0)
            if item.widget():
                item.widget().hide()  # at once: deleteLater waits for the event loop
                item.widget().deleteLater()
        self.buttons = []
        for i, (label, _fn) in enumerate(actions):
            if i:
                dot = QLabel("·")
                dot.setObjectName("caption")
                self.actions.addWidget(dot)
            button = QPushButton(label)
            button.setObjectName("link")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, i=i: self._fns[i]())
            self.actions.addWidget(button)
            self.buttons.append(button)


# The page -----------------------------------------------------------------------------------------


class LyricsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(8)
        self.origin = ElidedLabel()
        self.origin.setObjectName("caption")
        self.badge = QLabel()
        self.badge.setStyleSheet(
            f"color: {theme.ON_ACCENT}; background: {theme.ACCENT}; border-radius: 4px;"
            "padding: 1px 6px; font-weight: 600;"
        )
        self.badge.hide()
        row.addWidget(self.origin, 1)
        row.addWidget(self.badge)
        self.get = QToolButton()
        self.get.setText("Obtenir les paroles")
        self.get.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.get.setMenu(QMenu(self.get))
        self.edit = QPushButton("Modifier le texte…")
        self.sync = QPushButton("Synchroniser")
        self.sync.setCheckable(True)
        self.sync.setToolTip(
            "Mode synchronisation : choisissez une ligne, lancez la lecture, puis appuyez sur "
            "Entrée au début de chaque ligne chantée."
        )
        self.offset = Stepper(
            "Décalage",
            -200,
            200,
            0,
            lambda v: f"{v / 10:+.1f} s" if v else "0 s",
            "Avancer ou retarder toutes les paroles d'un coup",
        )
        self.text_size = Stepper("Texte", *SIZES, 20, str, "Taille du texte (Ctrl + molette)")
        self.follow = QPushButton("Suivre")
        self.follow.setCheckable(True)
        self.follow.setToolTip("Faire défiler les paroles avec la lecture")
        self.more = QToolButton()
        self.more.setIcon(theme.icon("menu"))
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more.setMenu(QMenu(self.more))
        self.more.setToolTip("Autres actions sur les paroles")
        self.more.setAccessibleName("Autres actions sur les paroles")
        for w in (
            self.get,
            self.edit,
            self.sync,
            self.offset,
            self.text_size,
            self.follow,
            self.more,
        ):
            row.addWidget(w)
        layout.addWidget(bar)
        self.bar = bar
        self.prompt = LyricsPrompt()
        layout.addWidget(self.prompt)

        # A transcription under way.
        self.work = QWidget()
        self.work.setObjectName("bar")
        work = QHBoxLayout(self.work)
        work.setContentsMargins(12, 4, 12, 4)
        self.work_text = QLabel()
        self.work_bar = QProgressBar()
        self.work_bar.setRange(0, 1000)
        self.work_bar.setTextVisible(False)
        self.work_bar.setMaximumWidth(260)
        self.work_cancel = QPushButton("Annuler")
        work.addWidget(self.work_text, 1)
        work.addWidget(self.work_bar)
        work.addWidget(self.work_cancel)
        self.work.hide()
        layout.addWidget(self.work)

        self.hint = QLabel()
        self.hint.setObjectName("caption")
        self.hint.setWordWrap(True)
        self.hint.setContentsMargins(16, 4, 16, 4)
        layout.addWidget(self.hint)

        self.stack = QStackedWidget()
        self.sheet = LyricsSheet()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.sheet)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack.addWidget(self.scroll)

        self.empty = QWidget()
        self.empty.setObjectName("page")
        box = QVBoxLayout(self.empty)
        box.addStretch()
        title = QLabel("Pas encore de paroles pour ce morceau")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail = QLabel(
            "Utilisez un fichier de paroles (.lrc, .srt, .txt), cherchez-les dans une base libre, "
            "transcrivez-les sur cet ordinateur ou saisissez-les."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)
        box.addWidget(detail)
        self.empty_buttons = QVBoxLayout()
        self.empty_buttons.setSpacing(8)
        center = QHBoxLayout()
        center.addStretch()
        center.addLayout(self.empty_buttons)
        center.addStretch()
        box.addSpacing(12)
        box.addLayout(center)
        box.addStretch()
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

    def adapt_to_width(self, width: int) -> None:
        """A tiling window manager can make the window small: the steppers give way first, and
        everything stays in the menu."""
        self.offset.setVisible(width >= 1100)
        self.text_size.setVisible(width >= 900)
        self.follow.setVisible(width >= 760)
        self.sync.setVisible(width >= 660)
        self.edit.setVisible(width >= 560)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adapt_to_width(event.size().width())


# What the window asks of the lyrics --------------------------------------------------------------


class LyricsController(QObject):
    """Everything about the lyrics, kept out of the main window: it calls refresh() after any
    change to the project, tick() with the playback position, tap() for Enter."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        s = window.song
        self.page = LyricsPage()
        self.sheet = self.page.sheet
        self.sheet.player_position = lambda: self.w.player.position
        s.middle.addWidget(self.page)
        self.strip = LyricsStrip()
        self.strip.hide()
        layout = s.layout()
        layout.insertWidget(layout.indexOf(s.progress_bar) + 1, self.strip)
        self.prompt = LyricsPrompt()  # over the grid, in the strip's place while there are none
        layout.insertWidget(layout.indexOf(self.strip), self.prompt)

        settings = window.settings
        self.mode = settings.get("lyrics_mode", "grid")
        if self.mode not in MODES:
            self.mode = "grid"
        self.last_mode = settings.get("lyrics_last", "sheet")
        if self.last_mode not in MODES or self.last_mode == "grid":
            self.last_mode = "sheet"

        # The button in the song's top bar.
        self.button = QToolButton()
        self.button.setText("Paroles")
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setToolTip("Grille, paroles, ou paroles et accords (K)")
        self.button.setAccessibleName("Paroles")
        menu = QMenu(self.button)
        self.mode_actions = {}
        for value, text in MODES.items():
            action = menu.addAction(text, lambda v=value: self.set_mode(v))
            action.setCheckable(True)
            self.mode_actions[value] = action
        self.button.setMenu(menu)
        top = s.key_button.parentWidget().layout()
        top.insertWidget(top.indexOf(s.key_button), self.button)

        p = self.page
        p.text_size.set_value(int(settings.get("lyrics_size", 20)))
        p.follow.setChecked(bool(settings.get("lyrics_follow", True)))
        get = p.get.menu()
        get.addAction("Rechercher en ligne (LRCLIB)…", self.search_online)
        get.addAction("Importer un fichier (.lrc, .srt, .txt)…", self.import_file)
        get.addAction("Transcrire avec l'IA, sur cet ordinateur…", self.transcribe)
        get.addAction("Saisir ou coller les paroles…", self.edit_text)
        p.edit.clicked.connect(self.edit_text)
        p.sync.toggled.connect(self._sync_toggled)
        p.offset.changed.connect(self._offset_changed)
        p.text_size.changed.connect(self._size_changed)
        p.follow.toggled.connect(lambda on: self.w._remember("lyrics_follow", on))
        p.work_cancel.clicked.connect(self.cancel)
        more = p.more.menu()
        more.addAction("Modifier le texte…", self.edit_text)
        self.sync_action = more.addAction("Mode synchronisation", p.sync.toggle)
        more.addAction("Décaler toutes les paroles de -0,1 s", lambda: p.offset.step(-1))
        more.addAction("Décaler toutes les paroles de +0,1 s", lambda: p.offset.step(1))
        more.addAction("Texte plus grand", lambda: p.text_size.step(2))
        more.addAction("Texte plus petit", lambda: p.text_size.step(-2))
        more.addAction("Suivre la lecture", p.follow.toggle)
        more.addSeparator()
        self.original_action = more.addAction("Revenir au texte d'origine", self.revert_original)
        self.previous_action = more.addAction(
            "Revenir aux paroles précédentes", self.revert_previous
        )
        more.addAction("Remettre tous les accords à leur place", self.reset_anchors)
        self.untime_action = more.addAction(
            "Retirer les horodatages (garder le texte)", self.clear_times
        )
        more.addSeparator()
        self.delete_action = more.addAction("Supprimer les paroles", self.delete)

        self.sheet.seekRequested.connect(self.w.seek)
        self.sheet.chordMoved.connect(self._chord_moved)
        self.sheet.chordReset.connect(self._chord_reset)
        self.sheet.lineAction.connect(self._line_action)
        self.sheet.linePicked.connect(lambda line: setattr(self, "picked", line))
        self.sheet.sizeStep.connect(lambda d: p.text_size.step(2 * d))
        self.sheet.interacted.connect(self._manual)
        p.scroll.verticalScrollBar().actionTriggered.connect(lambda _a: self._manual())

        # Exports with the lyrics, in the song's export menu.
        export_menu = s.export.menu()
        export_menu.addSeparator()
        self.exports = [
            export_menu.addAction("Paroles et accords (PDF)…", self.export_pdf),
            export_menu.addAction("Grille avec paroles (.txt)…", self.export_grid_text),
            export_menu.addAction(
                "Paroles synchronisées (.lrc)…", lambda: self.export_lyrics("lrc")
            ),
            export_menu.addAction("Paroles (.txt)…", lambda: self.export_lyrics("txt")),
        ]
        export_menu.setToolTipsVisible(True)

        self.picked: int | None = None
        self.rows: list[dict] = []
        self._starts: list[tuple[float, int]] = []
        self._project = None
        self._found: tuple | None = None
        self._manual_until = 0.0
        self._beat = None
        self._key = None
        self.task: transcribe.Task | None = None
        self.task_target = None  # (project, file) the transcription is for
        self.task_info: dict = {}
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._poll)
        self.anim = QPropertyAnimation(p.scroll.verticalScrollBar(), b"value", self)
        self.anim.setDuration(260)
        # The suggestion from LRCLIB, looked for in the background when the user allowed it.
        self.lookup: transcribe.Task | None = None
        self.lookup_for = None  # the project it is for
        self.suggestion: dict | None = None  # lyrics_online.suggest's answer, for self._project
        self._looked: set[str] = set()  # songs already looked up in this session
        self._has_grid = False
        self.lookup_timer = QTimer(self)
        self.lookup_timer.setInterval(150)
        self.lookup_timer.timeout.connect(self._poll_lookup)
        for prompt in (self.prompt, p.prompt):
            prompt.close.clicked.connect(self.hide_prompt)
        self._update_mode_actions()

    # Modes
    @property
    def full_page(self) -> bool:
        return self.mode in ("lyrics", "sheet")

    def middle_page(self):
        return self.page if self.full_page else self.w.song.scroll

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode != "grid":
            self.last_mode = mode
            self.w._remember("lyrics_last", mode)
        self.w._remember("lyrics_mode", mode)
        if mode != "grid" or not self.page.sync.isChecked():
            self.page.sync.setChecked(False)
        self._update_mode_actions()
        self.w._content_changed(save=False)

    def toggle_mode(self) -> None:
        if self.button.isVisible():
            self.set_mode(self.last_mode if self.mode == "grid" else "grid")

    def _update_mode_actions(self) -> None:
        for value, action in self.mode_actions.items():
            action.setChecked(value == self.mode)
        project = self.w.project
        found = bool(self._found or (self.suggestion and self.suggestion["verdict"] == "sure"))
        if self.mode != "grid":
            self.button.setText(MODES[self.mode])
        else:  # the grid alone: the button says when lyrics wait to be used
            waiting = found and project is not None and project.lyrics is None
            self.button.setText("Paroles trouvées" if waiting else "Paroles")

    # Following the project
    def refresh(self, has_grid: bool) -> None:
        w, p = self.w, self.page
        project = w.project
        if project is not self._project:
            self._project = project
            self.picked = None
            self.page.sync.setChecked(False)
            self.page.scroll.verticalScrollBar().setValue(0)
            self._found = None
            self.suggestion = None
            if project is not None and project.lyrics is None:
                self._found = self._local(project)
            self._maybe_look_up()
        self._has_grid = has_grid
        self.button.setVisible(has_grid)
        lyr = project.lyrics if project else None
        self.rows = export.lyric_rows(project) if lyr and has_grid else []
        self._starts = sorted(
            (r["start"], i)
            for i, r in enumerate(self.rows)
            if r["kind"] == "line" and r["start"] is not None
        )
        self.sheet.set_rows(self.rows, p.text_size.value, self.mode == "sheet")
        p.stack.setCurrentWidget(p.scroll if lyr else p.empty)
        self._fill_empty()
        self.strip.setVisible(has_grid and self.mode == "strip" and bool(lyr))
        # Where they come from, always in view.
        if lyr:
            src = lyr["source"]
            kind = src.get("kind")
            text = L.KINDS.get(kind, "")
            if src.get("name"):
                text += f" : {src['name']}"
            if kind == "catalog" and src.get("artist"):
                text += f" · {src.get('artist')} – {src.get('title')}"
            if L.edited(lyr):
                text += " · corrigées par vous"
            p.origin.set_full_text(text)
            p.badge.setText("Brouillon" if kind == "transcription" else "Non exportables")
            p.badge.setVisible(kind in ("transcription", "catalog"))
            p.badge.setToolTip(
                "Transcription automatique : vérifiez et corrigez le texte."
                if kind == "transcription"
                else NOT_EXPORTABLE
            )
            p.offset.set_value(round(float(lyr.get("offset") or 0) * 10))
        else:
            p.origin.set_full_text("")
            p.badge.hide()
        for widget in (p.edit, p.sync, p.offset, p.follow):
            widget.setEnabled(bool(lyr))
        self.original_action.setEnabled(bool(lyr) and L.edited(lyr))
        self.previous_action.setEnabled(bool(lyr and lyr.get("previous")))
        self.delete_action.setEnabled(bool(lyr))
        ok = L.exportable(lyr)
        for action in self.exports:
            action.setEnabled(ok)
            action.setToolTip("" if ok else (NOT_EXPORTABLE if lyr else "Pas de paroles."))
        self.untime_action.setEnabled(L.timed(lyr))
        self._update_hint()
        self._update_mode_actions()
        self._update_prompt()
        self._beat = self._key = None

    def _local(self, project) -> tuple | None:
        path = Path(project.audio.get("path", ""))
        if not path.is_file():
            return None
        try:
            tagged = audio.metadata(path).get("lyrics") or ""
        except (audio.AudioError, OSError):
            tagged = ""
        return L.find_local(path, tagged)

    def _fill_empty(self) -> None:
        box = self.page.empty_buttons
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        choices = []
        verdict = self.suggestion["verdict"] if self.suggestion else None
        if self._found:
            name = self._found[1]["name"]
            choices.append((f"Utiliser les paroles de « {name} »", self.use_found, True))
        elif verdict == "sure":
            choices.append(("Utiliser les paroles trouvées", self.use_suggestion, True))
        elif verdict == "choose":
            choices.append(("Choisir parmi les versions trouvées…", self.choose_suggestion, True))
        free = not choices  # nothing found yet: searching first, or transcribing when it failed
        choices += [
            ("Rechercher en ligne (LRCLIB)…", self.search_online, free and verdict != "none"),
            (
                "Transcrire avec l'IA, sur cet ordinateur…",
                self.transcribe,
                free and verdict == "none",
            ),
            ("Importer un fichier…", self.import_file, False),
            ("Saisir ou coller les paroles…", self.edit_text, False),
        ]
        for text, fn, primary in choices:
            button = QPushButton(text)
            if primary:
                button.setObjectName("primary")
            button.setMinimumWidth(320)
            button.clicked.connect(fn)
            box.addWidget(button)

    def _update_hint(self) -> None:
        p, lyr = self.page, self.w.project.lyrics if self.w.project else None
        if not lyr:
            p.hint.hide()
            return
        if p.sync.isChecked():
            text = (
                "Synchronisation : cliquez la ligne à minuter, lancez la lecture, puis Entrée "
                "au début de chaque ligne chantée. Ctrl + Z annule."
            )
        elif not L.timed(lyr):
            text = (
                "Ces paroles n'ont pas d'horodatage : elles ne suivent pas la lecture. "
                "« Synchroniser » permet de les minuter ligne par ligne."
            )
        elif self.mode == "sheet" and export.approximate(self.rows):
            text = (
                "En italique gris : accord placé approximativement dans la ligne. Glissez un "
                "nom d'accord sur le bon mot pour le corriger ; l'harmonie ne change pas."
            )
        elif self.mode == "sheet":
            text = (
                "Glissez un nom d'accord sur un autre mot pour le déplacer ; un clic sur une "
                "ligne lit depuis elle."
            )
        else:
            text = "Un clic sur une ligne lit depuis elle."
        p.hint.setText(text)
        p.hint.show()

    # The invitation, and the suggestion from LRCLIB
    def identity(self, project) -> dict:
        """What is known of the song: the names stored, and how they were found."""
        a = project.audio
        if "identity" not in a:  # a project from before 1.3.1: its names read again, as tags
            who = identify.from_file(
                {"title": a.get("title") or "", "artist": a.get("artist") or ""}, ""
            )
            return {**who, "album": a.get("album") or ""}
        return {
            "title": identify.clean_title(a.get("title") or ""),
            "artist": a.get("artist") or "",
            "album": a.get("album") or "",
            **{k: v for k, v in a["identity"].items() if k not in ("title", "artist", "album")},
        }

    def _maybe_look_up(self, asked: bool = False) -> None:
        """Ask LRCLIB in the background, only when allowed, for a song without lyrics that names
        its title and artist; once per song and session unless asked."""
        project = self.w.project
        if project is None or project.lyrics is not None or self._found:
            return
        if self.w.settings.get("lyrics_auto") is not True:
            return
        who = self.identity(project)
        key = self._song_key(project)
        if not identify.searchable(who) or (key in self._looked and not asked):
            return
        self._looked.add(key)
        duration = project.duration

        def work(_task):
            try:
                found = lyrics_online.search(who["title"], who["artist"], who["album"], duration)
            except lyrics_online.OnlineError as exc:
                raise transcribe.TranscribeError(str(exc)) from exc
            return lyrics_online.suggest(found, who, duration)

        self.suggestion = None
        self.lookup_for = project
        self.lookup = transcribe.run(work)
        self.lookup_timer.start()

    @staticmethod
    def _song_key(project) -> str:
        return project.audio.get("fingerprint") or project.audio.get("path") or ""

    def _poll_lookup(self) -> None:
        task = self.lookup
        if task is None or not task.done:
            return
        self.lookup_timer.stop()
        self.lookup = None
        if self.lookup_for is not self.w.project or self.w.settings.get("lyrics_auto") is not True:
            # Another song since, or no longer allowed: dropped, and asked again on its return.
            self._looked.discard(self._song_key(self.lookup_for))
            self._update_prompt()
            return
        self.suggestion = (
            {"verdict": "error", "error": task.error, "candidates": [], "synced": False}
            if task.error
            else task.result
        )
        self._fill_empty()
        self._update_mode_actions()
        self._update_prompt()

    def allow_auto(self, on: bool) -> None:
        """The user's answer, kept: whether songs without lyrics are looked up on LRCLIB."""
        self.w._remember("lyrics_auto", bool(on))
        action = getattr(self.w, "auto_lyrics_action", None)
        if action is not None and action.isChecked() != bool(on):
            action.blockSignals(True)
            action.setChecked(bool(on))
            action.blockSignals(False)
        if on:
            self._maybe_look_up(asked=True)
        self._update_prompt()

    def hide_prompt(self) -> None:
        if self.w.project:
            self.w.project.set_view(lyrics_prompt=False)
            self.w.save_timer.start()
        self._update_prompt()

    def _prompt_state(self, full: bool) -> tuple[str, list] | None:
        """(text, [(action, fn)]) for the invitation; None where the page already says it."""
        project = self.w.project
        who = self.identity(project)
        name = f"« {who['title']} »" + (f" ({who['artist']})" if who["artist"] else "")
        verdict = self.suggestion["verdict"] if self.suggestion else None
        search = ("Rechercher les paroles", self.search_online)
        transcribe_ = ("Transcrire avec l'IA", self.transcribe)
        import_ = ("Importer", self.import_file)
        if self.task is not None:  # a transcription: the page has its bar, the grid this line
            if full:
                return None
            return (self.page.work_text.text(), [("Annuler", self.cancel)])
        if self._found:
            if full:
                return None
            return (
                f"Paroles trouvées sur cet ordinateur : « {self._found[1]['name']} »",
                [("Utiliser", self.use_found), ("Autres choix", lambda: self.set_mode("lyrics"))],
            )
        if self.lookup is not None and self.lookup_for is project:
            return (f"Recherche des paroles de {name} sur LRCLIB…", [])
        if verdict == "sure":
            best = self.suggestion["candidates"][0]
            how = "synchronisées" if self.suggestion["synced"] else "texte seul"
            if best.get("syncedLyrics") and not self.suggestion["synced"]:
                how += " (autre version : les horodatages du catalogue ne tomberaient pas juste)"
            return (
                f"Paroles trouvées : {best.get('artistName')} – {best.get('trackName')} · {how}",
                [
                    ("Utiliser", self.use_suggestion),
                    ("Voir les autres versions", self.choose_suggestion),
                    ("Modifier la recherche", self.search_online),
                ],
            )
        if verdict == "choose":
            n = len(self.suggestion["candidates"])
            return (
                f"{n} version{'s' if n > 1 else ''} possible{'s' if n > 1 else ''} pour {name} "
                "sur LRCLIB : à vous de choisir",
                [
                    ("Choisir…", self.choose_suggestion),
                    ("Modifier la recherche", self.search_online),
                ],
            )
        if self.w.settings.get("lyrics_auto") is None and identify.searchable(who):
            return (
                "Rechercher automatiquement les paroles des morceaux sur LRCLIB ? Seuls le titre, "
                "l'artiste, l'album et la durée sont envoyés, jamais l'audio.",
                [
                    ("Autoriser", lambda: self.allow_auto(True)),
                    ("Non merci", lambda: self.allow_auto(False)),
                ],
            )
        if verdict == "none":  # better none than another song's: the transcription comes first
            return (
                f"Aucune parole fiable trouvée sur LRCLIB pour {name}",
                [transcribe_, ("Modifier la recherche", self.search_online), import_],
            )
        if verdict == "error":
            return (f"Recherche des paroles impossible : {self.suggestion['error']}", [search])
        if full:
            return None  # the page lists the same choices, larger
        unknown = "" if identify.searchable(who) else " (morceau non identifié)"
        return (f"Aucune parole disponible{unknown}", [search, transcribe_, import_])

    def _update_prompt(self) -> None:
        project = self.w.project
        show = bool(
            project is not None
            and project.lyrics is None
            and self._has_grid
            and (project.view.get("lyrics_prompt", True) or self.task is not None)
        )
        for prompt, full in ((self.prompt, False), (self.page.prompt, True)):
            here = show and (self.full_page if full else self.mode == "strip")
            state = self._prompt_state(full) if here else None
            if state:
                prompt.show_state(*state)
            prompt.setVisible(bool(state))

    def use_suggestion(self) -> None:
        sug = self.suggestion
        if not (sug and sug["candidates"] and self.w.project) or self.w.project.lyrics:
            return  # lyrics there already are never replaced by a suggestion
        record, synced = sug["candidates"][0], sug["synced"]
        self._replace(
            lyrics_online.lines_of(record, synced), lyrics_online.source_of(record, synced)
        )

    def choose_suggestion(self) -> None:
        self.search_online(self.suggestion["candidates"] if self.suggestion else None)

    # Playback
    def tick(self, position: float, beat: int) -> None:
        if not self.rows:
            return
        k = None
        if self._starts:
            from bisect import bisect_right

            i = bisect_right(self._starts, (position + 1e-3, float("inf"))) - 1
            k = self._starts[i][1] if i >= 0 else None
        if beat != self._beat:
            self._beat = beat
            seg = next(
                (x for x in self.w.project.segments() if x.start_beat <= beat < x.end_beat), None
            )
            self._key = L.chord_key(seg.start) if seg is not None and seg.chord != "N" else None
        changed = (k, self._key) != (self.sheet.now_row, self.sheet.now_key)
        self.sheet.set_now(k, self._key)
        if self.strip.isVisible():
            nxt = next(
                (
                    r["text"]
                    for r in self.rows[(k + 1 if k is not None else 0) :]
                    if r["kind"] == "line"
                ),
                "",
            )
            self.strip.set_lines(self.rows[k]["text"] if k is not None else "", nxt)
        if changed and self.w.player.playing:
            self._follow(k)

    def _manual(self) -> None:
        self._manual_until = time.monotonic() + MANUAL_SCROLL_PAUSE

    def _follow(self, row: int | None) -> None:
        p = self.page
        if (
            row is None
            or not p.follow.isChecked()
            or not self.full_page
            or time.monotonic() < self._manual_until
            or self.sheet._drag
        ):
            return
        rect = self.sheet.row_rect(row)
        if rect is None:
            return
        bar = p.scroll.verticalScrollBar()
        view = p.scroll.viewport().height()
        # Only when the line leaves the reading zone: no jolt at every line.
        if bar.value() + view * 0.12 <= rect.top() and rect.bottom() <= bar.value() + view * 0.6:
            return
        target = max(0, int(rect.top() - view * 0.3))
        self.anim.stop()
        self.anim.setStartValue(bar.value())
        self.anim.setEndValue(min(target, bar.maximum()))
        self.anim.start()

    # Changes, all through the project, so Ctrl + Z undoes them
    def _apply(self, lyr: dict | None) -> None:
        self.w.project.set_lyrics(lyr)
        self.w._content_changed()

    def _copy(self) -> dict:
        return copy.deepcopy(self.w.project.lyrics)

    def _chord_moved(self, key: str, line: int, char: int) -> None:
        lyr = self._copy()
        lyr["anchors"][key] = {"line": line, "char": char}
        self._apply(lyr)

    def _chord_reset(self, key: str) -> None:
        lyr = self._copy()
        lyr["anchors"].pop(key, None)
        self._apply(lyr)

    def reset_anchors(self) -> None:
        if self.w.project and self.w.project.lyrics and self.w.project.lyrics["anchors"]:
            lyr = self._copy()
            lyr["anchors"] = {}
            self._apply(lyr)

    def _line_action(self, line: int, action: str) -> None:
        lyr = self._copy()
        x = lyr["lines"][line]
        if action == "here":
            x["start"] = round(max(0.0, self.w.player.position - float(lyr["offset"])), 3)
            x.pop("words", None)  # the words' times belonged to the old start
            x.pop("end", None)
        elif action in ("earlier", "later") and x["start"] is not None:
            d = -0.1 if action == "earlier" else 0.1
            x["start"] = round(max(0.0, x["start"] + d), 3)
            if x.get("end") is not None:
                x["end"] = round(x["end"] + d, 3)
            for word in x.get("words") or []:
                word[1] = round(word[1] + d, 3)
        elif action == "clear":
            x["start"] = None
            x.pop("words", None)
            x.pop("end", None)
        self._apply(lyr)

    def _offset_changed(self, value: int) -> None:
        if self.w.project and self.w.project.lyrics:
            lyr = self._copy()
            lyr["offset"] = value / 10
            self._apply(lyr)

    def _size_changed(self, value: int) -> None:
        self.w._remember("lyrics_size", value)
        self.sheet.set_rows(self.rows, value, self.mode == "sheet")

    def _sync_toggled(self, on: bool) -> None:
        if on and not self.full_page:
            self.set_mode(self.last_mode)
        if on and self.picked is None and self.w.project and self.w.project.lyrics:
            first = next(
                (
                    i
                    for i, x in enumerate(self.w.project.lyrics["lines"])
                    if x["text"] and not x.get("section")
                ),
                None,
            )
            self._pick(first)
        self._update_hint()

    def _pick(self, line: int | None) -> None:
        self.picked = line
        self.sheet.picked_row = self.sheet.row_of_line(line) if line is not None else None
        self.sheet.update()
        rect = self.sheet.row_rect(self.sheet.picked_row)
        if rect is not None:
            self.page.scroll.ensureVisible(0, int(rect.center().y()), 0, int(rect.height() * 2))

    def tap(self) -> bool:
        """Enter in sync mode: the chosen line starts now, and the next one is chosen."""
        lyr = self.w.project.lyrics if self.w.project else None
        if not (self.page.sync.isChecked() and self.full_page and lyr and self.picked is not None):
            return False
        if self.picked >= len(lyr["lines"]):
            return True
        self._line_action(self.picked, "here")
        nxt = next(
            (
                i
                for i in range(self.picked + 1, len(lyr["lines"]))
                if lyr["lines"][i]["text"] and not lyr["lines"][i].get("section")
            ),
            None,
        )
        self._pick(nxt)
        if nxt is None:
            self.page.sync.setChecked(False)
        return True

    # Getting lyrics
    def _replace(self, lines: list[dict], source: dict) -> None:
        if not any(x["text"] for x in lines):
            self.w._alert("Ces paroles sont vides.")
            return
        old = self.w.project.lyrics
        self._apply(L.replaced(old, lines, source))
        self._found = None

    def _may_replace(self) -> bool:
        """Corrected lyrics are never replaced without asking; they stay one click away."""
        lyr = self.w.project.lyrics if self.w.project else None
        if not lyr or not L.edited(lyr):
            return True
        answer = QMessageBox.question(
            self.w,
            "Remplacer les paroles",
            "Ces paroles ont été corrigées. Les remplacer ? Elles resteront accessibles avec "
            "« Revenir aux paroles précédentes » et Ctrl + Z.",
        )
        return answer == QMessageBox.StandardButton.Yes

    def use_found(self) -> None:
        if self._found and self.w.project:
            lines, source = self._found
            self._replace(lines, source)

    def import_file(self) -> None:
        if not self.w.project or not self._may_replace():
            return
        start = str(Path(self.w.project.audio.get("path", "")).parent)
        path, _ = QFileDialog.getOpenFileName(
            self.w, "Importer des paroles", start, "Paroles (*.lrc *.srt *.txt)"
        )
        if not path:
            return
        try:
            lines = L.read_file(Path(path))
        except OSError as exc:
            self.w._alert(f"Lecture impossible : {exc.strerror or exc}")
            return
        self._replace(lines, {"kind": "file", "name": Path(path).name, "exportable": True})

    def search_online(self, records: list[dict] | None = None) -> None:
        """The search dialog, on the names known, or on the candidates already found."""
        from .lyrics_dialogs import SearchDialog

        project = self.w.project
        if not project or not self._may_replace():
            return
        who = self.identity(project)
        shown = (
            who["title"] or Path(project.audio.get("path", "")).stem,
            who["artist"],
            who["album"],
        )
        dialog = SearchDialog(
            *shown,
            project.duration,
            self.w,
            records=records or None,
            version=identify.is_version(who["title"], who.get("video_title", "")),
        )
        if not (dialog.exec() and dialog.choice):
            return
        if dialog.query and dialog.query != shown:
            self._rename(*dialog.query)  # the names that found them: the user's correction
        record, synced = dialog.choice
        self._replace(
            lyrics_online.lines_of(record, synced), lyrics_online.source_of(record, synced)
        )

    def _rename(self, title: str, artist: str, album: str) -> None:
        """The song's names as the user corrected them, kept: never read again from the file."""
        a = self.w.project.audio
        a.update(title=title, artist=artist, album=album)
        a["identity"] = {**(a.get("identity") or {}), "how": "user", "sure": True}
        s = self.w.song
        s.title.set_full_text(title)
        s.subtitle.set_full_text(artist)
        s.subtitle.setVisible(bool(artist))
        self.w.setWindowTitle(f"{title} : LocalChords")

    def edit_text(self) -> None:
        from .lyrics_dialogs import LyricsEditor

        project = self.w.project
        if not project:
            return
        lyr = project.lyrics
        text = L.to_editor(lyr["lines"]) if lyr else ""
        dialog = LyricsEditor(text, self.w, copyable=not lyr or L.exportable(lyr))
        if not dialog.exec():
            return
        lines = L.from_editor(dialog.text(), lyr["lines"] if lyr else [])
        if not lyr:
            if any(x["text"] for x in lines):
                self._apply(L.new(lines, {"kind": "user", "name": "", "exportable": True}))
            return
        new = self._copy()
        new["lines"] = lines
        new["anchors"] = _moved_anchors(lyr, lines)
        self._apply(new)

    def revert_original(self) -> None:
        lyr = self._copy()
        lyr["lines"], lyr["anchors"], lyr["offset"] = copy.deepcopy(lyr["original"]), {}, 0.0
        self._apply(lyr)

    def revert_previous(self) -> None:
        lyr = self.w.project.lyrics
        if lyr and lyr.get("previous"):
            back = copy.deepcopy(lyr["previous"])
            back["previous"] = {k: v for k, v in copy.deepcopy(lyr).items() if k != "previous"}
            self._apply(back)

    def clear_times(self) -> None:
        """The words kept without their times: another performance, or times to redo by hand."""
        if not (self.w.project and L.timed(self.w.project.lyrics)):
            return
        lyr = self._copy()
        for x in lyr["lines"]:
            x["start"] = None
            x.pop("words", None)
            x.pop("end", None)
        lyr["offset"] = 0.0
        self._apply(lyr)

    def delete(self) -> None:
        answer = QMessageBox.question(
            self.w,
            "Supprimer les paroles",
            "Supprimer les paroles de ce morceau ? Ctrl + Z les rétablit.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._apply(None)

    # Transcribing, in the background
    def transcribe(self) -> None:
        from .lyrics_dialogs import TranscribeDialog

        project = self.w.project
        if not project or self.task is not None:
            return
        path = library.audio_file(project.audio)
        if not path.is_file():
            self.w._alert("Le fichier audio est introuvable : il faut l'écouter pour transcrire.")
            return
        dialog = TranscribeDialog(
            self.w.settings.get("whisper_model", transcribe.DEFAULT_MODEL),
            self.w.settings.get("whisper_language", "auto"),
            self.w,
        )
        if not dialog.exec() or not self._may_replace():
            return
        model, language = dialog.model, dialog.language
        self.w._remember("whisper_model", model)
        self.w._remember("whisper_language", language)
        self.task_target = (project, self.w.project_file)
        self.task_info = {"model": model, "language": language, "began": time.monotonic()}
        self.task = transcribe.run(lambda t: transcribe.transcribe(path, model, language, t))
        p = self.page
        p.work_text.setText("Transcription en cours, sur cet ordinateur…")
        p.work_bar.setValue(0)
        p.work.show()
        self._update_prompt()
        self.timer.start()

    def _poll(self) -> None:
        task, p = self.task, self.page
        if task is None:
            self.timer.stop()
            return
        elapsed = time.monotonic() - self.task_info["began"]
        p.work_bar.setValue(int(task.progress * 1000))
        p.work_text.setText(
            f"Transcription en cours, sur cet ordinateur : {task.status} "
            f"{round(task.progress * 100)} % · {fmt_time(elapsed)}"
        )
        if self.prompt.isVisible():
            self._update_prompt()
        if not task.done:
            return
        self.timer.stop()
        self.task = None
        p.work.hide()
        self._update_prompt()
        if task.error:
            if not task.cancelled:
                self.w._alert(task.error)
            return
        result = task.result
        model = transcribe.model_info(self.task_info["model"])
        source = {
            "kind": "transcription",
            "name": f"whisper.cpp, modèle {model['id']}",
            "model": model["id"],
            "language": result["language"],
            "date": date.today().isoformat(),
            "seconds": round(elapsed, 1),
            "exportable": True,
        }
        if not result["lines"]:
            self.w._alert(
                "Aucune parole reconnue : le morceau est peut-être instrumental, ou la "
                "voix trop couverte par la musique."
            )
            return
        project, file = self.task_target
        # The same song reopened meanwhile is another Project object, but the same file.
        open_now = self.w.project is not None
        if open_now and (project is self.w.project or (file and file == self.w.project_file)):
            self._replace(result["lines"], source)
        elif file is not None:  # another song is open: the transcription goes to its own project
            from ..project import Project, ProjectError

            try:
                other = Project.load(file)
                other.set_lyrics(L.replaced(other.lyrics, result["lines"], source))
                other.save(file)
            except (ProjectError, OSError) as exc:
                self.w._alert(f"La transcription n'a pas pu être enregistrée : {exc}")

    def cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()

    # Exporting
    def _save_path(self, title: str, suffix: str, kind: str) -> Path | None:
        project = self.w.project
        if not project or not L.exportable(project.lyrics):
            self.w._alert(NOT_EXPORTABLE if project and project.lyrics else "Pas de paroles.")
            return None
        name = f"{project.audio.get('title') or 'paroles'}{suffix}"
        path, _ = QFileDialog.getSaveFileName(self.w, title, name, kind)
        return Path(path) if path else None

    def export_lyrics(self, kind: str) -> None:
        path = self._save_path(
            "Exporter les paroles", f".{kind}", "LRC (*.lrc)" if kind == "lrc" else "Texte (*.txt)"
        )
        if path:
            project = self.w.project
            text = (
                L.to_lrc(
                    project.lyrics,
                    project.audio.get("title") or "",
                    project.audio.get("artist") or "",
                )
                if kind == "lrc"
                else L.to_text(project.lyrics)
            )
            self._write(path, text)

    def export_grid_text(self) -> None:
        path = self._save_path(
            "Exporter la grille avec les paroles", " - paroles et accords.txt", "Texte (*.txt)"
        )
        if path:
            self._write(path, export.to_text_with_lyrics(self.w.project))

    def _write(self, path: Path, text: str) -> None:
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self.w._alert(f"Export impossible : {exc.strerror or exc}")

    def export_pdf(self) -> None:
        from .lyrics_dialogs import LyricsPdfDialog
        from .pdf import write_lyrics_sheet

        project = self.w.project
        if not project or not L.exportable(project.lyrics):
            self.w._alert(NOT_EXPORTABLE if project and project.lyrics else "Pas de paroles.")
            return
        dialog = LyricsPdfDialog(self.w.settings.get("lyrics_pdf") or {}, self.w)
        if not dialog.exec():
            return
        options = dialog.options()
        self.w._remember("lyrics_pdf", options)
        path = self._save_path(
            "Exporter les paroles et accords", " - paroles et accords.pdf", "PDF (*.pdf)"
        )
        if path:
            try:
                write_lyrics_sheet(
                    project, path, options, self.w.song.chords.all_items, self.w.song.positions
                )
            except OSError as exc:
                self.w._alert(f"Export impossible : {exc.strerror or exc}")


def _moved_anchors(before: dict, lines: list[dict]) -> dict:
    """After the text is edited, each chord placed by hand follows its line, found by its words;
    a chord whose line is gone goes back to its automatic place."""
    out = {}
    texts = [x["text"] for x in lines]
    for key, a in before.get("anchors", {}).items():
        if not 0 <= a["line"] < len(before["lines"]):
            continue
        text = before["lines"][a["line"]]["text"]
        same = [i for i, t in enumerate(texts) if t == text]
        if same and a["char"] <= len(text):
            out[key] = {"line": min(same, key=lambda i: abs(i - a["line"])), "char": a["char"]}
    return out
