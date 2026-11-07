"""How to play the chord in front of you: a guitar diagram and a piano keyboard, drawn from the
positions that voicings.py worked out and checked note by note. Nothing here decides a note."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import voicings
from . import theme

WHITE_KEY = "#D7DBE2"
BLACK_KEY = "#14171D"
MODES = ("guitar", "piano", "both")
STATES = ("full", "reduced", "hidden")
FADE_MS = 140


class _Diagram(QWidget):
    """Paints once per change into a cached image and fades from the old one to the new one, so
    that the per-frame cost during playback is drawing two pictures."""

    def __init__(self):
        super().__init__()
        self._cache: QPixmap | None = None
        self._old: QPixmap | None = None
        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self.update)
        self._fade.finished.connect(self._drop_old)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _changed(self, animate: bool = True) -> None:
        if animate and self.isVisible() and self._cache is not None:
            self._old = self._cache
            self._fade.stop()
            self._fade.start()
        self._cache = None
        self.update()

    def _drop_old(self) -> None:
        self._old = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache = self._old = None

    def paintEvent(self, event):
        if self._cache is None:
            ratio = self.devicePixelRatioF()
            self._cache = QPixmap(self.size() * ratio)
            self._cache.setDevicePixelRatio(ratio)
            self._cache.fill(Qt.GlobalColor.transparent)
            p = QPainter(self._cache)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self.draw(p, QRectF(self.rect()))
            p.end()
        p = QPainter(self)
        if self._old is not None:
            t = float(self._fade.currentValue() or 0.0)
            p.setOpacity(1.0 - t)
            p.drawPixmap(0, 0, self._old)
            p.setOpacity(t)
        p.drawPixmap(0, 0, self._cache)

    def draw(self, p: QPainter, r: QRectF) -> None:
        raise NotImplementedError

    @staticmethod
    def _message(p: QPainter, r: QRectF, text: str) -> None:
        p.setPen(QColor(theme.TEXT_2))
        p.setFont(theme.app_font(13))
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        p.drawText(r.adjusted(12, 8, -12, -8), int(flags), text)


class GuitarDiagram(_Diagram):
    """Six strings seen from the front, low E on the left, the nut at the top."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(110, 120)
        self.fingering: voicings.Fingering | None = None
        self.chord: voicings.Chord | None = None
        self.capo = 0
        self.message = ""
        self.compact = False
        self.setAccessibleName("Diagramme de guitare")

    def set_fingering(self, fingering, chord, capo: int, message: str = "", animate=True) -> None:
        self.fingering, self.chord, self.capo, self.message = fingering, chord, capo, message
        self.setAccessibleDescription(
            describe_fingering(fingering, chord) if fingering else message
        )
        self._changed(animate)

    def draw(self, p: QPainter, r: QRectF) -> None:
        f = self.fingering
        if f is None:
            self._message(p, r, self.message)
            return
        top_fret = f.highest_fret
        start = 1 if top_fret <= 4 else f.lowest_fret
        rows = max(4, top_fret - start + 1)
        names_h = 0 if self.compact else 20
        left_w = 26
        # A string spacing that fits both ways, frets a little taller than strings are apart.
        sx = min((r.width() - left_w - 14) / 5, (r.height() - names_h - 8) / (rows * 1.2 + 0.8))
        sx = max(8.0, min(sx, 44.0))
        fy = sx * 1.2
        mark_h = sx * 0.8
        board_w, board_h = 5 * sx, rows * fy
        x0 = r.left() + left_w + (r.width() - left_w - 14 - board_w) / 2
        y0 = r.top() + (r.height() - names_h - board_h - mark_h) / 2 + mark_h
        xs = [x0 + s * sx for s in range(6)]

        # Frets, then strings, the low ones a little thicker.
        p.setPen(QPen(QColor(theme.TEXT_3), 1.0))
        for i in range(rows + 1):
            y = y0 + i * fy
            p.drawLine(QPointF(x0, y), QPointF(x0 + board_w, y))
        for s, x in enumerate(xs):
            p.setPen(QPen(QColor(theme.TEXT_2), 1.0 + (5 - s) * 0.22))
            p.drawLine(QPointF(x, y0), QPointF(x, y0 + board_h))
        if start == 1:
            p.setPen(QPen(QColor(theme.TEXT), max(3.0, sx * 0.14)))
            p.drawLine(QPointF(x0 - 1, y0), QPointF(x0 + board_w + 1, y0))
        else:
            p.setPen(QColor(theme.TEXT_2))
            p.setFont(theme.app_font(max(11, sx * 0.42), 600))
            p.drawText(
                QRectF(r.left(), y0, x0 - r.left() - 6, fy),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                str(start),
            )

        # Open and muted strings, above the nut.
        size = min(mark_h * 0.5, sx * 0.42)
        for s, fret in enumerate(f.frets):
            c = QPointF(xs[s], y0 - mark_h * 0.5)
            if fret == 0:
                p.setPen(QPen(QColor(theme.TEXT), 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, size * 0.5, size * 0.5)
            elif fret is None:
                p.setPen(QPen(QColor(theme.TEXT_3), 1.6))
                h = size * 0.45
                p.drawLine(c + QPointF(-h, -h), c + QPointF(h, h))
                p.drawLine(c + QPointF(-h, h), c + QPointF(h, -h))

        radius = min(sx, fy) * 0.38
        finger_font = theme.app_font(max(10, radius * 1.15), 700)
        accent = QColor(theme.ACCENT)

        def dot_center(s, fret):
            return QPointF(xs[s], y0 + (fret - start + 0.5) * fy)

        def number(center, finger):
            p.setPen(QColor(theme.ON_ACCENT))
            p.setFont(finger_font)
            box = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(finger))

        barred = set()
        if f.barre:
            fret, first, last = f.barre
            barred = {s for s in range(first, last + 1) if f.frets[s] == fret}
            a, b = dot_center(first, fret), dot_center(last, fret)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            bar = QRectF(a.x() - radius, a.y() - radius * 0.85, b.x() - a.x() + 2 * radius,
                         radius * 1.7)  # fmt: skip
            p.drawRoundedRect(bar, radius * 0.85, radius * 0.85)
            number(a, 1)
        for s, fret in enumerate(f.frets):
            if not fret or s in barred:
                continue
            c = dot_center(s, fret)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawEllipse(c, radius, radius)
            number(c, f.fingers[s])

        # What each string plays, the bass in the accent colour: reading it is checking it.
        if self.compact or self.chord is None:
            return
        lowest = min(f.notes())
        p.setFont(theme.app_font(max(10, min(13, sx * 0.4))))
        for s, note in zip(
            [s for s, x in enumerate(f.frets) if x is not None], f.notes(), strict=True
        ):
            name = self.chord.names.get(note % 12, "")
            is_bass = note == lowest
            p.setPen(QColor(theme.ACCENT if is_bass else theme.TEXT_2))
            font = theme.app_font(max(10, min(13, sx * 0.4)), 700 if is_bass else 400)
            p.setFont(font)
            box = QRectF(xs[s] - sx / 2 - 4, y0 + board_h + 3, sx + 8, names_h)
            p.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), name)


STRINGS = ("6", "5", "4", "3", "2", "1")


def describe_fingering(f: voicings.Fingering, chord: voicings.Chord | None) -> str:
    """The diagram in words, for a screen reader and for the tooltip."""
    parts = []
    for s, fret in enumerate(f.frets):
        if fret is None:
            parts.append(f"corde {STRINGS[s]} étouffée")
        elif fret == 0:
            parts.append(f"corde {STRINGS[s]} à vide")
        else:
            parts.append(f"corde {STRINGS[s]} case {fret} doigt {f.fingers[s]}")
    head = f"{chord.title} : " if chord else ""
    return f"{head}{f.text}, {f.kind.lower()}. " + ", ".join(parts) + "."


class PianoDiagram(_Diagram):
    """Three octaves, C3 to B5. One hand in the accent colour; with two, the left in blue."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(160, 70)
        self.voicing: voicings.PianoVoicing | None = None
        self.chord: voicings.Chord | None = None
        self.message = ""
        self.compact = False
        self.setAccessibleName("Clavier de piano")

    def set_voicing(self, voicing, chord, message: str = "", animate=True) -> None:
        self.voicing, self.chord, self.message = voicing, chord, message
        self.setAccessibleDescription(describe_voicing(voicing, chord) if voicing else message)
        self._changed(animate)

    def draw(self, p: QPainter, r: QRectF) -> None:
        v = self.voicing
        if v is None:
            self._message(p, r, self.message)
            return
        whites = [n for n in range(voicings.LOW_KEY, voicings.HIGH_KEY + 1) if _is_white(n)]
        labels_h = 0 if self.compact else 34
        hands_h = 0 if self.compact or not v.left else 16
        kw = min((r.width() - 8) / len(whites), (r.height() - labels_h - hands_h - 4) / 4.2)
        kw = max(6.0, kw)
        kh = min(kw * 5.0, r.height() - labels_h - hands_h - 4)
        width = kw * len(whites)
        x0 = r.left() + (r.width() - width) / 2
        y0 = r.top() + (r.height() - labels_h - hands_h - kh) / 2 + hands_h
        left, right = set(v.left), set(v.right)
        lowest = min(v.notes)

        def color(n):
            if n in left:
                return QColor(theme.SELECT)
            if n in right:
                return QColor(theme.ACCENT)
            return None

        centers = {}
        p.setPen(QPen(QColor(theme.BG), 1.0))
        for i, n in enumerate(whites):
            rect = QRectF(x0 + i * kw, y0, kw, kh)
            centers[n] = rect.center().x()
            p.setBrush(color(n) or QColor(WHITE_KEY))
            p.drawRoundedRect(rect.adjusted(0.5, 0, -0.5, 0), 2.5, 2.5)
        bw, bh = kw * 0.62, kh * 0.62
        for n in range(voicings.LOW_KEY, voicings.HIGH_KEY + 1):
            if _is_white(n):
                continue
            x = centers[n - 1] + kw / 2
            centers[n] = x
            rect = QRectF(x - bw / 2, y0, bw, bh)
            p.setPen(QPen(QColor(theme.BG), 1.0))
            p.setBrush(color(n) or QColor(BLACK_KEY))
            p.drawRoundedRect(rect, 2.0, 2.0)
        # The bass: a dot on its key, so it reads without colour too.
        tip = kh - 0.32 * kw if _is_white(lowest) else bh - 0.32 * kw
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BG))
        p.drawEllipse(QPointF(centers[lowest], y0 + tip), kw * 0.16, kw * 0.16)

        if hands_h:
            p.setFont(theme.app_font(11, 600))
            for notes, text, tint in ((v.left, "MG", theme.SELECT), (v.right, "MD", theme.ACCENT)):
                middle = (centers[min(notes)] + centers[max(notes)]) / 2
                p.setPen(QColor(tint))
                p.drawText(QRectF(middle - 30, y0 - hands_h, 60, hands_h - 2),
                           int(Qt.AlignmentFlag.AlignCenter), text)  # fmt: skip
        if self.compact or self.chord is None:
            return
        # Names under their keys, on two rows when neighbours would touch.
        font = theme.app_font(12)
        p.setFont(font)
        metrics = p.fontMetrics()
        ends = [-1e9, -1e9]
        for n in v.notes:
            name = self.chord.names.get(n % 12, "")
            w = metrics.horizontalAdvance(name) + 6
            x = centers[n] - w / 2
            row = 0 if x >= ends[0] else 1
            ends[row] = x + w
            tint = theme.SELECT if n in left else theme.ACCENT
            p.setPen(QColor(tint))
            p.setFont(theme.app_font(12, 700 if n == lowest else 500))
            box = QRectF(x, y0 + kh + 2 + row * 16, w, 16)
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), name)


def _is_white(note: int) -> bool:
    return note % 12 in (0, 2, 4, 5, 7, 9, 11)


def describe_voicing(v: voicings.PianoVoicing, chord: voicings.Chord | None) -> str:
    names = chord.names if chord else {}

    def spell(notes):
        return ", ".join(f"{names.get(n % 12, '?')}{n // 12 - 1}" for n in notes)

    if v.left:
        text = f"main gauche {spell(v.left)} ; main droite {spell(v.right)}"
    else:
        text = spell(v.right)
    head = f"{chord.title} : " if chord else ""
    return f"{head}{v.name.lower()}, de la plus grave à la plus aiguë : {text}."


class _Instrument(QWidget):
    """A diagram under a line that says which position it is and moves between them."""

    stepped = Signal(int)

    def __init__(self, title: str, diagram: _Diagram, key: str, tip: str):
        super().__init__()
        self.diagram = diagram
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.header = QWidget()
        row = QHBoxLayout(self.header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        name = QLabel(title)
        name.setObjectName("h2")
        name.setToolTip(tip)
        self.kind = QLabel()
        self.kind.setObjectName("caption")
        self.kind.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.prev = QToolButton()
        self.prev.setObjectName("step")
        self.prev.setIcon(theme.icon("left", size=14))
        self.prev.setAccessibleName(f"{title} : position précédente")
        self.prev.setToolTip(f"Position précédente (Maj + {key})")
        self.count = QLabel()
        self.count.setObjectName("caption")
        self.count.setMinimumWidth(34)
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next = QToolButton()
        self.next.setObjectName("step")
        self.next.setIcon(theme.icon("right", size=14))
        self.next.setAccessibleName(f"{title} : position suivante")
        self.next.setToolTip(f"Position suivante ({key})")
        row.addWidget(name)
        row.addWidget(self.kind, 1)
        row.addWidget(self.prev)
        row.addWidget(self.count)
        row.addWidget(self.next)
        layout.addWidget(self.header)
        layout.addWidget(diagram, 1)
        self.prev.clicked.connect(lambda: self.stepped.emit(-1))
        self.next.clicked.connect(lambda: self.stepped.emit(1))

    def set_place(self, index: int, total: int, kind: str) -> None:
        self.kind.setText(kind)
        self.kind.setToolTip(kind)
        self.count.setText(f"{index + 1} / {total}" if total else "")
        for button in (self.prev, self.next):
            button.setEnabled(total > 1)


class ChordPanel(QFrame):
    """The chord being played, or the one the user pinned, ready to play."""

    modeChanged = Signal(str)
    stateChanged = Signal(str)
    followRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self.mode = "guitar"
        self.state = "full"
        self.side = True
        self.wide = False
        self.side_width = 340
        self.shown: voicings.Shown | None = None
        self.guitar_positions: tuple = ()
        self.piano_voicings: tuple = ()
        self.guitar_index = self.piano_index = 0

        # The chord and its controls: above the diagrams at the side, left of them at the bottom.
        self.outer = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.outer.setContentsMargins(14, 10, 14, 12)
        self.outer.setSpacing(14)
        self.lead = QWidget()
        lead = QVBoxLayout(self.lead)
        lead.setContentsMargins(0, 0, 0, 0)
        lead.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel("—")
        self.title.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {theme.ACCENT};")
        self.title.setAccessibleName("Accord des diagrammes")
        self.status = QLabel()
        self.status.setObjectName("caption")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.follow = QPushButton("Suivre la lecture")
        self.follow.setObjectName("link")
        self.follow.setToolTip(
            "Les diagrammes restent sur l'accord cliqué. Revenir à l'accord joué (Échap) ; "
            "lancer la lecture y revient aussi."
        )
        self.follow.setStyleSheet(
            f"QPushButton#link {{ background: transparent; border: none; padding: 0 2px; "
            f"color: {theme.ACCENT}; font-weight: 600; text-decoration: underline; }}"
        )
        self.follow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.follow.hide()
        self.follow.clicked.connect(self.followRequested)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.follow)
        titles.addWidget(self.title)
        titles.addLayout(status_row)
        head.addLayout(titles, 1)
        self.resize_button = QToolButton()
        self.resize_button.setObjectName("step")
        self.hide_button = QToolButton()
        self.hide_button.setObjectName("step")
        self.hide_button.setIcon(theme.icon("close", size=14))
        self.hide_button.setAccessibleName("Masquer les diagrammes")
        self.hide_button.setToolTip("Masquer les diagrammes (D)")
        head.addWidget(self.resize_button, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.hide_button, 0, Qt.AlignmentFlag.AlignTop)
        lead.addLayout(head)

        self.modes = QWidget()
        modes = QHBoxLayout(self.modes)
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(4)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for mode, text in zip(MODES, ("Guitare", "Piano", "Les deux"), strict=True):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setAccessibleName(f"Diagrammes : {text.lower()}")
            b.setStyleSheet("padding: 4px 10px;")
            self.mode_group.addButton(b)
            self.mode_buttons[mode] = b
            modes.addWidget(b)
            b.clicked.connect(lambda _=False, m=mode: self._choose_mode(m))
        modes.addStretch(1)
        lead.addWidget(self.modes)

        self.capo_note = QLabel()
        self.capo_note.setObjectName("caption")
        self.capo_note.setWordWrap(True)
        self.capo_note.hide()
        lead.addWidget(self.capo_note)
        lead.addStretch(1)
        self.outer.addWidget(self.lead)

        self.guitar = _Instrument(
            "Guitare",
            GuitarDiagram(),
            "G",
            "Accordage standard. Les doigts sont une suggestion : 1 index, 2 majeur, 3 annulaire, "
            "4 auriculaire.",
        )
        self.piano = _Instrument(
            "Piano",
            PianoDiagram(),
            "P",
            "Une disposition possible parmi d'autres ; "
            "la répartition des mains est une suggestion.",
        )
        self.guitar.stepped.connect(lambda d: self.step("guitar", d))
        self.piano.stepped.connect(lambda d: self.step("piano", d))
        self.body = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.body.setSpacing(12)
        self.body.addWidget(self.guitar, 3)
        self.body.addWidget(self.piano, 2)
        self.body.addStretch(0)  # beside the grid, a short keyboard stays at the top
        self.outer.addLayout(self.body, 1)
        self.resize_button.clicked.connect(
            lambda: self.set_state("reduced" if self.state == "full" else "full")
        )
        self.hide_button.clicked.connect(lambda: self.set_state("hidden"))
        self.set_mode("guitar")
        self.set_state("full", emit=False)
        self.show_chord(None, "", False, "—")

    # Settings ----------------------------------------------------------------------------------
    def _choose_mode(self, mode: str) -> None:
        self.set_mode(mode)
        self.modeChanged.emit(mode)

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "guitar"
        self.mode_buttons[self.mode].setChecked(True)
        self.guitar.setVisible(self.mode != "piano")
        self.piano.setVisible(self.mode != "guitar")
        self._fit()
        self._refresh(animate=False)

    def set_state(self, state: str, emit: bool = True) -> None:
        self.state = state if state in STATES else "full"
        full = self.state == "full"
        self.resize_button.setIcon(theme.icon("shrink" if full else "grow", size=14))
        self.resize_button.setAccessibleName("Réduire les diagrammes" if full else "Agrandir")
        self.resize_button.setToolTip(
            "Réduire : les diagrammes seuls" if full else "Agrandir : positions et notes"
        )
        for part in (self.guitar.header, self.piano.header):
            part.setVisible(full)
        for diagram in (self.guitar.diagram, self.piano.diagram):
            diagram.compact = not full
        self.modes.setVisible(full)
        self.capo_note.setVisible(full and bool(self.capo_note.text()))
        self.setVisible(self.state != "hidden")
        self._fit()
        self._refresh(animate=False)
        if emit:
            self.stateChanged.emit(self.state)

    def set_orientation(self, side: bool, wide: bool = False) -> None:
        """Beside the grid on a wide window, under it on a narrow one."""
        if (side, wide) == (self.side, self.wide):
            return
        self.side, self.wide = side, wide
        self._fit()
        self.updateGeometry()

    def _fit(self) -> None:
        full = self.state == "full"
        if self.side:
            self.outer.setDirection(QBoxLayout.Direction.TopToBottom)
            self.lead.setMaximumWidth(16777215)
            self.lead.setMinimumWidth(0)
            self.body.setDirection(QBoxLayout.Direction.TopToBottom)
            self.side_width = (420 if self.wide else 340) if full else 240
            self.setMinimumSize(0, 0)
            self.setMaximumSize(self.side_width, 16777215)
            self.piano.setMaximumHeight(230)  # wider than tall: more height is empty
            edge = "border-left"
        else:
            self.outer.setDirection(QBoxLayout.Direction.LeftToRight)
            self.lead.setFixedWidth(250 if full else 170)
            self.body.setDirection(QBoxLayout.Direction.LeftToRight)
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.piano.setMaximumHeight(16777215)
            height = (250 if full else 150) if self.mode != "piano" else (200 if full else 120)
            self.setFixedHeight(height)
            edge = "border-top"
        # Stacked, the fretboard wants height; side by side, the keyboard wants width.
        self.body.setStretchFactor(self.guitar, 3 if self.side else 2)
        self.body.setStretchFactor(self.piano, 2 if self.side else 3)
        self.setStyleSheet(
            f"QFrame#panel {{ background: {theme.SURFACE}; border: none; "
            f"{edge}: 1px solid {theme.BORDER}; }}"
        )

    # Beside the grid, the panel asks for its width but never forces the window wider: a tiling
    # window manager can jump straight to a narrow size, and then the panel moves under the grid.
    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(self.side_width, hint.height()) if self.side else hint

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(0, hint.height()) if self.side else hint

    # The chord ---------------------------------------------------------------------------------
    def show_chord(self, shown, status: str, pinned: bool, empty: str = "—") -> None:
        """`shown` from voicings.describe, None for no chord (then `empty` is the title)."""
        self.status.setText(status)
        self.status.setToolTip(status)
        self.follow.setVisible(pinned)
        if shown == self.shown and (shown is not None or self.title.text() == empty):
            return
        self.shown = shown
        self.guitar_index = self.piano_index = 0
        if shown is None:
            self.guitar_positions = self.piano_voicings = ()
            self.title.setText(empty)
            self.title.setToolTip("")
            self.capo_note.setText("")
        else:
            shape, sound = shown.shape, shown.sound
            self.guitar_positions = voicings.guitar(
                shape.root, shape.quality, shape.bass if shape.inverted else None, shown.capo
            )
            self.piano_voicings = voicings.piano(
                sound.root, sound.quality, sound.bass if sound.inverted else None
            )
            self.title.setText(shape.title)
            self.title.setToolTip(f"Notes : {' · '.join(shape.names[pc] for pc in shape.tones)}")
            self.capo_note.setText(
                f"Capo en case {shown.capo} : forme de {shape.title}, son réel {sound.title}. "
                "Les cases se comptent depuis le capo."
                if shown.capo
                else ""
            )
        self.capo_note.setVisible(self.state == "full" and bool(self.capo_note.text()))
        self._refresh()

    def step(self, instrument: str, delta: int) -> None:
        if instrument == "guitar" and self.guitar_positions:
            self.guitar_index = (self.guitar_index + delta) % len(self.guitar_positions)
        elif instrument == "piano" and self.piano_voicings:
            self.piano_index = (self.piano_index + delta) % len(self.piano_voicings)
        else:
            return
        self._refresh()

    def _refresh(self, animate: bool = True) -> None:
        shown = self.shown
        if shown is None:
            text = (
                "Pas d'accord ici : rien à jouer pendant ce passage."
                if self.title.text() == "N.C."
                else "Les diagrammes suivent l'accord joué."
            )
            self.guitar.diagram.set_fingering(None, None, 0, text, animate)
            self.piano.diagram.set_voicing(None, None, text, animate)
            self.guitar.set_place(0, 0, "")
            self.piano.set_place(0, 0, "")
            return
        positions, index = self.guitar_positions, self.guitar_index
        if positions:
            f = positions[index]
            self.guitar.diagram.set_fingering(f, shown.shape, shown.capo, animate=animate)
            self.guitar.set_place(index, len(positions), f.kind)
            self.guitar.diagram.setToolTip(describe_fingering(f, shown.shape))
        else:
            self.guitar.diagram.set_fingering(None, shown.shape, shown.capo,
                                              _unplayable(shown), animate)  # fmt: skip
            self.guitar.set_place(0, 0, "Aucune position")
            self.guitar.diagram.setToolTip("")
        v = self.piano_voicings[self.piano_index]
        self.piano.diagram.set_voicing(v, shown.sound, animate=animate)
        # With a capo the title is the guitar shape; the keyboard plays what is heard.
        kind = f"son réel {shown.sound.title} · {v.name}" if shown.capo else v.name
        self.piano.set_place(self.piano_index, len(self.piano_voicings), kind)
        self.piano.diagram.setToolTip(describe_voicing(v, shown.sound))


def _unplayable(shown: voicings.Shown) -> str:
    """Said instead of a diagram that would be wrong."""
    shape = shown.shape
    where = f" avec le capo en case {shown.capo}" if shown.capo else ""
    if shape.inverted:
        return (
            f"Aucune position vérifiée de {shape.title} avec {shape.names[shape.bass]} à la basse"
            f"{where}. Masquer les basses ou retirer le capo propose l'accord sans elle."
        )
    return f"Aucune position vérifiée de {shape.title}{where} dans les {voicings.MAX_FRET} cases."
