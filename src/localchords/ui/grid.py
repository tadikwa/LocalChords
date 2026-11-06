"""The chord grid: what a musician reads. Painted by hand so that it stays sharp and fast at any
size, from a laptop to a 5120 × 1440 screen, only the changed cells repainted during playback."""

from __future__ import annotations

import re

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..export import chord_text
from ..project import Project
from . import theme

MARGIN = 16
BAR_GAP = 8
ROW_GAP = 10
MIN_CELL = 72
MAX_CELL = 210
ROW_MAX = 132
# Bars per line, in the multiples that keep phrases lined up.
BARS_PER_ROW = (16, 12, 8, 4, 2, 1)


class ChordGrid(QWidget):
    beatClicked = Signal(int)  # the user wants to play from there
    editRequested = Signal(int, int)  # first and last beat of what to correct
    contextRequested = Signal(int, QPoint)
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.cells: dict[int, QRectF] = {}
        self.bar_rects: list[tuple[QRectF, int]] = []
        self.rows: list[tuple[float, float]] = []  # top and bottom of each row
        self.row_of: dict[int, int] = {}
        self.symbols: dict[int, tuple[str, float, object]] = {}  # beat → (text, width, segment)
        self.continued: dict[int, str] = {}  # first beat of a row inside a chord → its text
        self.segment_of: dict[int, object] = {}
        self.current = -1
        self.progress = 0.0
        self.anchor: int | None = None
        self.selection: tuple[int, int] | None = None
        self.loop_beats: tuple[int, int] | None = None
        self.cell_w = 80.0
        self.row_h = 80.0
        self.bars_per_row = 4
        self.view_height = 600
        self._drag_from: int | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setAccessibleName("Grille d'accords")

    # Content -----------------------------------------------------------------------------------
    def set_project(self, project: Project | None) -> None:
        self.project = project
        self.current = -1
        self.selection = None
        self.anchor = None
        self.loop_beats = None
        self.refresh()

    def refresh(self) -> None:
        """Recompute after anything that changes what the grid shows."""
        self._build()
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        if event.size().width() != event.oldSize().width():
            self._build()
        super().resizeEvent(event)

    def set_view_height(self, height: int) -> None:
        if height != self.view_height:
            self.view_height = height
            self._build()
            self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return int(self.rows[-1][1] + MARGIN) if self.rows else 0

    def sizeHint(self):
        return QSize(self.width() or 800, self.heightForWidth(self.width()))

    def _build(self) -> None:
        self.cells.clear()
        self.bar_rects.clear()
        self.rows.clear()
        self.row_of.clear()
        self.symbols.clear()
        self.continued.clear()
        self.segment_of.clear()
        project = self.project
        if not project or not project.grid():
            self.setMinimumHeight(0)
            return
        bars = project.bars()
        per_bar = max(len(bars[0].beats), 1)
        avail = max(self.width() - 2 * MARGIN, 200)

        def cell_width(n_bars):
            return (avail - (n_bars - 1) * BAR_GAP) / (n_bars * per_bar)

        numerals = project.view.get("show_numerals")

        def row_height(cell_w):
            return min(max(cell_w * 0.8, 64.0), ROW_MAX) + (18 if numerals else 0)

        def total_height(n_bars):
            rows = -(-len(bars) // n_bars)
            return rows * (row_height(cell_width(n_bars)) + ROW_GAP) + 2 * MARGIN

        segments = project.segments()
        texts = {s.start_beat: chord_text(project, s) for s in segments}
        # The biggest cells that show the whole song without scrolling; when it can't all show,
        # the densest layout that stays readable, since a line is what the eye follows.
        readable = [b for b in BARS_PER_ROW if cell_width(b) >= MIN_CELL] or [1]
        comfortable = [b for b in readable if cell_width(b) <= MAX_CELL] or readable[-1:]
        fitting = [b for b in comfortable if total_height(b) <= self.view_height]
        n_bars = fitting[-1] if fitting else comfortable[0]
        self.bars_per_row = n_bars
        cell_w = cell_width(n_bars)
        self.cell_w = cell_w
        self.row_h = row_height(cell_w)

        y = float(MARGIN)
        for i, bar in enumerate(bars):
            col = i % n_bars
            row = i // n_bars
            if col == 0 and i:
                y += self.row_h + ROW_GAP
            if col == 0:
                self.rows.append((y, y + self.row_h))
            x = MARGIN + col * (per_bar * cell_w + BAR_GAP)
            self.bar_rects.append((QRectF(x, y, per_bar * cell_w, self.row_h), bar.number))
            for j, beat in enumerate(bar.beats):
                if beat is not None:
                    self.cells[beat] = QRectF(x + j * cell_w, y, cell_w, self.row_h)
                    self.row_of[beat] = row
        bar_starts = {next((b for b in bar.beats if b is not None), None) for bar in bars}
        for s in segments:
            text = texts[s.start_beat]
            for beat in range(s.start_beat, s.end_beat):
                self.segment_of[beat] = s
            # How many beats of the same row the label may run across.
            span = 0
            for beat in range(s.start_beat, s.end_beat):
                if self.row_of.get(beat) != self.row_of.get(s.start_beat):
                    break
                span += 1
            self.symbols[s.start_beat] = (text, span * cell_w, s)
            # A chord held over a bar line is named again, dimly: an empty bar reads as nothing.
            for beat in range(s.start_beat + 1, s.end_beat):
                if beat in bar_starts:
                    self.continued[beat] = text
        height = int(self.rows[-1][1] + MARGIN) if self.rows else 0
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    # Playback ----------------------------------------------------------------------------------
    def set_playhead(self, t: float) -> None:
        if not self.project or not self.cells:
            return
        beat = self.project.beat_at(t)
        grid = self.project.grid()
        progress = 0.0
        if 0 <= beat < len(grid):
            end = grid[beat + 1] if beat + 1 < len(grid) else self.project.duration
            progress = (t - grid[beat]) / max(end - grid[beat], 1e-3)
        if beat != self.current:
            # The whole chord's tint moves with it, not only the two cells.
            self._update_segment(self.current)
            self.current = beat
            self._update_segment(beat)
        elif abs(progress - self.progress) * self.cell_w >= 1:
            self._update_cell(beat)
        self.progress = progress

    def _update_cell(self, beat: int) -> None:
        rect = self.cells.get(beat)
        if rect:
            self.update(rect.toAlignedRect().adjusted(-2, -2, 2, 2))

    def _update_segment(self, beat: int) -> None:
        segment = self.segment_of.get(beat)
        if segment is None:
            self._update_cell(beat)
            return
        for b in range(segment.start_beat, segment.end_beat):
            self._update_cell(b)

    def current_rect(self) -> QRect | None:
        rect = self.cells.get(self.current)
        return rect.toAlignedRect() if rect else None

    def rect_of(self, beat: int) -> QRect | None:
        rect = self.cells.get(beat)
        return rect.toAlignedRect() if rect else None

    # Selection ---------------------------------------------------------------------------------
    def set_selection(self, first: int | None, last: int | None = None) -> None:
        self.selection = None if first is None else (min(first, last), max(first, last))
        self.update()
        self.selectionChanged.emit()

    def set_loop(self, beats: tuple[int, int] | None) -> None:
        self.loop_beats = beats
        self.update()

    def beat_at_point(self, point: QPointF) -> int | None:
        hit = next((i for i, (top, bot) in enumerate(self.rows) if top <= point.y() <= bot), None)
        if hit is None:
            return None
        top = self.rows[hit][0]
        n = self.bars_per_row
        bars = self.bar_rects[hit * n : hit * n + n]
        for rect, _number in bars:
            if rect.left() <= point.x() <= rect.right():
                col = int((point.x() - rect.left()) / self.cell_w)
                top_left = QPointF(rect.left() + col * self.cell_w + 1, top + 1)
                for beat, cell in self.cells.items():
                    if cell.contains(top_left):
                        return beat
        return None

    def mousePressEvent(self, event):
        beat = self.beat_at_point(event.position())
        if beat is None:
            return super().mousePressEvent(event)
        self.setFocus()
        if event.button() == Qt.MouseButton.RightButton:
            if not self.selection or not self.selection[0] <= beat <= self.selection[1]:
                self.anchor = beat
                self.set_selection(beat, beat)
            self.contextRequested.emit(beat, event.globalPosition().toPoint())
            return None
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.anchor is not None:
            self.set_selection(self.anchor, beat)
            return None
        self.anchor = beat
        self._drag_from = beat
        self.set_selection(beat, beat)
        self.beatClicked.emit(beat)
        return None

    def mouseMoveEvent(self, event):
        if self._drag_from is None:
            return
        beat = self.beat_at_point(event.position())
        if beat is not None:
            self.set_selection(self._drag_from, beat)

    def mouseReleaseEvent(self, event):
        self._drag_from = None

    def mouseDoubleClickEvent(self, event):
        beat = self.beat_at_point(event.position())
        if beat is None:
            return
        # A double click means the chord, not the one beat it landed on.
        segment = self.segment_of.get(beat)
        if segment is not None:
            self.set_selection(segment.start_beat, segment.end_beat - 1)
            self.editRequested.emit(segment.start_beat, segment.end_beat - 1)

    # Painting ----------------------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(event.rect(), QColor(theme.BG))
        if not self.project or not self.cells:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(event.rect())
        current_segment = self.segment_of.get(self.current)
        loop = self.loop_beats
        selection = self.selection
        small = theme.app_font(11 if self.cell_w < 120 else 13)

        for rect, _number in self.bar_rects:
            if not rect.intersects(area):
                continue
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(rect, 8, 8)

        for beat, rect in self.cells.items():
            if not rect.intersects(area):
                continue
            segment = self.segment_of.get(beat)
            inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            if loop and loop[0] <= beat <= loop[1]:
                p.setPen(Qt.PenStyle.NoPen)
                color = QColor(theme.LOOP)
                color.setAlpha(46)
                p.setBrush(color)
                p.drawRoundedRect(inner, 6, 6)
            if segment is not None and segment is current_segment and beat != self.current:
                color = QColor(theme.ACCENT)
                color.setAlpha(34)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(inner, 6, 6)
            if beat == self.current:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.ACCENT))
                p.drawRoundedRect(inner, 6, 6)
            if selection and selection[0] <= beat <= selection[1]:
                color = QColor(theme.SELECT)
                pen = QPen(color, 2)
                p.setPen(pen)
                color.setAlpha(30 if beat != self.current else 0)
                p.setBrush(color)
                p.drawRoundedRect(inner, 6, 6)

        # Beat dividers, faint, over the fills.
        p.setPen(QPen(QColor(theme.SURFACE_3), 1))
        for beat, rect in self.cells.items():
            if rect.intersects(area) and beat + 1 in self.cells:
                next_rect = self.cells[beat + 1]
                if abs(next_rect.left() - rect.right()) < 0.5:
                    x = rect.right()
                    p.drawLine(QPointF(x, rect.top() + 10), QPointF(x, rect.bottom() - 10))

        # Bar numbers.
        p.setFont(small)
        p.setPen(QColor(theme.TEXT_3))
        for rect, number in self.bar_rects:
            if rect.intersects(area) and number:
                p.drawText(rect.adjusted(8, 5, 0, 0), Qt.AlignmentFlag.AlignLeft, str(number))

        # Chord names run across the whole span of a chord, drawn after the fills.
        numerals = self.project.view.get("show_numerals")
        base_size = min(max(self.cell_w * 0.40, 20.0), 46.0)
        for beat, text in self.continued.items():
            rect = self.cells[beat]
            if rect.intersects(area):
                self._draw_symbol(p, rect, text, self.cell_w, base_size * 0.72, theme.TEXT_3, 400)
        for beat, (text, width, segment) in self.symbols.items():
            rect = self.cells.get(beat)
            if rect is None:
                continue
            band = QRectF(rect.left(), rect.top(), width, rect.height())
            if not band.intersects(area):
                continue
            on_accent = beat == self.current
            is_none = segment.chord == "N"
            color = theme.ON_ACCENT if on_accent else (theme.TEXT_3 if is_none else theme.TEXT)
            size = base_size * (0.6 if is_none else 1.0)
            self._draw_symbol(p, rect, text, width, size, color, 400 if is_none else 600)
            if segment.edited:
                # A shape as well as a colour: a small triangle in the corner of a correction.
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.ON_ACCENT if on_accent else theme.EDITED))
                corner = rect.topRight() + QPointF(-5, 5)
                p.drawPolygon([corner, corner + QPointF(-9, 0), corner + QPointF(0, 9)])
            if numerals and segment.numeral and not is_none:
                p.setFont(small)
                role = theme.ROLE_COLORS.get(segment.role or "", theme.TEXT_2)
                p.setPen(QColor(theme.ON_ACCENT if on_accent else role))
                p.drawText(
                    rect.adjusted(10, 0, 0, -6),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                    segment.numeral,
                )

        # The lit cell always names the chord, so the eye can stay on it.
        rect = self.cells.get(self.current)
        lit = rect and rect.intersects(area) and current_segment is not None
        if lit and self.current != current_segment.start_beat and current_segment.chord != "N":
            text = self.symbols[current_segment.start_beat][0]
            self._draw_symbol(p, rect, text, self.cell_w, base_size * 0.72, theme.ON_ACCENT, 600)

        # The beat's progress, a thin line along the bottom of the current cell.
        rect = self.cells.get(self.current)
        if rect and rect.intersects(area):
            y = rect.bottom() - 5
            p.setPen(QPen(QColor(theme.ON_ACCENT), 2))
            p.drawLine(
                QPointF(rect.left() + 6, y),
                QPointF(rect.left() + 6 + (rect.width() - 12) * min(self.progress, 1.0), y),
            )

        # Loop brackets at both ends, so a loop reads without its colour.
        if loop:
            p.setPen(QPen(QColor(theme.LOOP), 3))
            for beat, flip in ((loop[0], False), (loop[1], True)):
                r = self.cells.get(beat)
                if r and r.intersects(area):
                    x = r.right() - 1.5 if flip else r.left() + 1.5
                    p.drawLine(QPointF(x, r.top() + 4), QPointF(x, r.bottom() - 4))
        if self.hasFocus() and selection:
            r = self.cells.get(selection[1])
            if r and r.intersects(area):
                p.setPen(QPen(QColor(theme.TEXT), 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 5, 5)
        p.end()

    def _draw_symbol(self, p, rect, text, width, size, color, weight) -> None:
        """Root large, accidental raised, the rest smaller on the baseline: as charts print them."""
        room = width - 14
        parts = symbol_parts(text)

        def advance(scale):
            total = 0.0
            for piece, ratio, _raise, piece_weight in parts:
                font = theme.app_font(size * scale * ratio, piece_weight or weight)
                total += QFontMetricsF(font).horizontalAdvance(piece)
            return total

        scale = 1.0
        measured = advance(1.0)
        if measured > room:
            scale = max(room / measured, 11 / size)
        x = rect.left() + 10
        baseline = rect.top() + rect.height() / 2 + size * scale * 0.42
        p.setPen(QColor(color))
        for piece, ratio, lift, piece_weight in parts:
            font = theme.app_font(size * scale * ratio, piece_weight or weight)
            p.setFont(font)
            p.drawText(QPointF(x, baseline - lift * size * scale), piece)
            x += QFontMetricsF(font).horizontalAdvance(piece)


_SYMBOL = re.compile(r"^(Do|Ré|Mi|Fa|Sol|La|Si|[A-G])([♯♭]?)([^/]*)(/.*)?$")


def symbol_parts(text: str) -> list[tuple[str, float, float, int | None]]:
    """(piece, size ratio, baseline lift, weight or None to inherit) for each piece of a symbol."""
    match = _SYMBOL.match(text)
    if not match:
        return [(text, 1.0, 0.0, None)]
    root, accidental, quality, bass = match.groups()
    parts = [(root, 1.0, 0.0, None)]
    if accidental:
        parts.append((accidental, 0.62, 0.30, None))
    if quality:
        parts.append((quality, 0.66, 0.0, 500))
    if bass:
        parts.append((bass, 0.62, 0.0, 400))
    return parts
