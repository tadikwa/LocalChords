"""Small widgets shared by the screens."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class ElidedLabel(QLabel):
    """A label that cuts long text with an ellipsis instead of widening the window."""

    def __init__(self):
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._apply()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        metrics = self.fontMetrics()
        self.setText(metrics.elidedText(self._full, Qt.TextElideMode.ElideRight, self.width()))


def segmented(buttons) -> QFrame:
    """A few exclusive choices side by side in one track (the theme's QFrame#segmented); the
    caller keeps its QButtonGroup and its signals."""
    frame = QFrame()
    frame.setObjectName("segmented")
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    for b in buttons:
        row.addWidget(b)
    return frame


class Stepper(QWidget):
    """− value +: for anything counted in steps, such as semitones."""

    changed = Signal(int)

    def __init__(self, label: str, low: int, high: int, value: int = 0, render=str, tip=""):
        super().__init__()
        self.low, self.high, self.value, self.render = low, high, value, render
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.minus = QToolButton()
        self.minus.setObjectName("step")
        self.minus.setIcon(theme.icon("minus", size=14))
        self.minus.setAccessibleName(f"{label} : moins")
        self.plus = QToolButton()
        self.plus.setObjectName("step")
        self.plus.setIcon(theme.icon("plus", size=14))
        self.plus.setAccessibleName(f"{label} : plus")
        middle = QVBoxLayout()
        middle.setSpacing(0)
        caption = QLabel(label)
        caption.setObjectName("caption")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel()
        self.text.setMinimumWidth(52)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle.addWidget(caption)
        middle.addWidget(self.text)
        self.setToolTip(tip)
        row.addWidget(self.minus)
        row.addLayout(middle)
        row.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self.step(-1))
        self.plus.clicked.connect(lambda: self.step(1))
        self.set_value(value)

    def set_value(self, value: int) -> None:
        self.value = max(self.low, min(self.high, value))
        self.text.setText(self.render(self.value))
        self.minus.setEnabled(self.value > self.low)
        self.plus.setEnabled(self.value < self.high)

    def step(self, delta: int) -> None:
        before = self.value
        self.set_value(self.value + delta)
        if self.value != before:
            self.changed.emit(self.value)
