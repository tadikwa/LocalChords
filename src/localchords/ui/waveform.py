"""The overview: the whole song as a waveform over a strip of its chords. Click or drag to move."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..chords import parse
from ..export import chord_text
from ..i18n import translate
from ..project import Project
from . import theme

STRIP_H = 24


class Waveform(QWidget):
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks = np.zeros(0, dtype=np.uint8)
        self.duration = 0.0
        self.position = 0.0
        self.project: Project | None = None
        self.loop: tuple[float, float] | None = None
        self.cache: QPixmap | None = None
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(translate("Waveform", "Forme d'onde et chronologie des accords"))
        self.setToolTip(translate("Waveform", "Cliquez pour vous déplacer dans le morceau"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_peaks(self, peaks: np.ndarray, duration: float) -> None:
        self.peaks, self.duration = peaks, duration
        self.invalidate()

    def set_project(self, project: Project | None) -> None:
        self.project = project
        self.invalidate()

    def invalidate(self) -> None:
        self.cache = None
        self.update()

    def set_position(self, t: float) -> None:
        old, self.position = self._x(self.position), t
        new = self._x(t)
        if int(old) != int(new):
            self.update(int(min(old, new)) - 3, 0, int(abs(new - old)) + 7, self.height())

    def set_loop(self, loop) -> None:
        self.loop = loop
        self.update()

    def _x(self, t: float) -> float:
        return t / self.duration * self.width() if self.duration else 0.0

    def resizeEvent(self, event):
        self.cache = None
        super().resizeEvent(event)

    def _render_cache(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        px = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        px.setDevicePixelRatio(ratio)
        px.fill(QColor(theme.SURFACE))
        p = QPainter(px)
        w, h = self.width(), self.height()
        wave_h = h - STRIP_H - 2
        if len(self.peaks):
            center = wave_h / 2
            xs = np.linspace(0, len(self.peaks), w + 1).astype(int)
            p.setPen(QColor(theme.TEXT_3))
            for x in range(w):
                part = self.peaks[xs[x] : max(xs[x + 1], xs[x] + 1)]
                amp = (int(part.max()) if len(part) else 0) / 255 * (wave_h / 2 - 3)
                p.drawLine(QPointF(x + 0.5, center - amp), QPointF(x + 0.5, center + amp))
        project = self.project
        if project and self.duration:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            font = theme.app_font(11, 500)
            p.setFont(font)
            top = h - STRIP_H
            for s in project.segments():
                x0, x1 = self._x(s.start), self._x(s.end)
                rect = QRectF(x0, top, max(x1 - x0 - 1, 1), STRIP_H)
                parsed = parse(s.chord)
                if parsed is None:
                    p.fillRect(rect, QColor(theme.SURFACE_2))
                    continue
                p.fillRect(rect, theme.chord_color(parsed[0], 200))
                text = chord_text(project, s)
                if rect.width() > 8 * len(text) + 6:
                    p.setPen(QColor(theme.TEXT))
                    p.drawText(rect.adjusted(4, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
        p.end()
        return px

    def paintEvent(self, event):
        if self.cache is None:
            self.cache = self._render_cache()
        p = QPainter(self)
        p.drawPixmap(0, 0, self.cache)
        if self.loop and self.duration:
            x0, x1 = self._x(self.loop[0]), self._x(self.loop[1])
            color = QColor(theme.LOOP)
            color.setAlpha(60)
            p.fillRect(QRectF(x0, 0, x1 - x0, self.height()), color)
            p.setPen(QPen(QColor(theme.LOOP), 2))
            p.drawLine(QPointF(x0, 0), QPointF(x0, self.height()))
            p.drawLine(QPointF(x1, 0), QPointF(x1, self.height()))
        if self.duration:
            x = self._x(self.position)
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.end()

    def _seek(self, event) -> None:
        if self.duration and self.width():
            fraction = min(max(event.position().x() / self.width(), 0.0), 1.0)
            self.seekRequested.emit(fraction * self.duration)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._seek(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek(event)
