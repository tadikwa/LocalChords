"""The song's chords at a glance under the grid: each one once, in the order it first comes, or the
one playing and the next few. Each card shows how to play it with the panel's own diagrams and
positions, so a song can be learnt before it is played."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import voicings
from . import theme
from .diagrams import (
    MODES,
    GuitarDiagram,
    PianoDiagram,
    Positions,
    _Instrument,
    describe_fingering,
    describe_voicing,
    positions_of,
)
from .widgets import segmented

VIEWS = ("all", "next")
STATES = ("compact", "expanded", "hidden")
UPCOMING = 5  # the chord playing and the four after it
GAP = 10


@dataclass
class Item:
    """One card: the chord as the grid writes it, where it is, and when (for the panel)."""

    shown: voicings.Shown
    time: float
    place: str
    current: bool = False


def chord_key(shown: voicings.Shown) -> tuple:
    """Two chords are the same card when the guitar plays the same thing: a different bass is a
    different position, a different spelling of the same notes is not."""
    s = shown.shape
    return (s.root, s.quality, s.bass if s.inverted else None)


class _Flow(QLayout):
    """Cards side by side on one line (the strip scrolls sideways), or wrapped into rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.wrap = False
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return self.wrap

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), apply=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        sizes = [i.sizeHint() for i in self.items if not i.isEmpty()]
        if not sizes:
            return QSize(0, 0)
        tall = max(s.height() for s in sizes)
        if self.wrap:
            return QSize(max(s.width() for s in sizes), tall)
        return QSize(sum(s.width() for s in sizes) + GAP * (len(sizes) - 1), tall)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, apply=True)

    def _place(self, rect: QRect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if self.wrap and x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, line = rect.x(), y + line + GAP, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + GAP
            line = max(line, size.height())
        return y + line - rect.y()


class ChordCard(QFrame):
    """A chord, where it comes, and its diagrams with the position chosen for it."""

    chosen = Signal()
    moved = Signal(int)  # the arrow keys: the card before or after

    def __init__(self, positions: Positions):
        super().__init__()
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.positions = positions
        self.item: Item | None = None
        self.mode = "guitar"
        self.guitar_positions: tuple = ()
        self.piano_voicings: tuple = ()
        self._drawn = None
        self.current = self.selected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("cardChord")
        self.place = QLabel()
        self.place.setObjectName("caption")
        self.place.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.place)
        layout.addLayout(head)
        guitar = GuitarDiagram()
        guitar.setFixedSize(140, 150)
        piano = PianoDiagram()
        piano.fit = True
        piano.setFixedSize(224, 110)
        self.guitar = _Instrument("Guitare", guitar, "", "Accordage standard.", kind_below=True)
        self.piano = _Instrument(
            "Piano", piano, "", "Une disposition possible parmi d'autres.", kind_below=True
        )
        self.guitar.stepped.connect(lambda d: self._step("guitar", d))
        self.piano.stepped.connect(lambda d: self._step("piano", d))
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self.guitar, 0, Qt.AlignmentFlag.AlignTop)
        body.addWidget(self.piano, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body)
        positions.changed.connect(self.refresh)
        self._style()

    def set_item(self, item: Item, mode: str) -> None:
        same = self.item is not None and self.item.shown == item.shown
        self.item = item
        self.place.setText(item.place)
        self.title.setText(item.shown.shape.title)
        if not same:
            self.guitar_positions, self.piano_voicings = positions_of(item.shown)
        self.set_mode(mode)
        self.set_flags(item.current, self.selected)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.guitar.setVisible(mode != "piano")
        self.piano.setVisible(mode != "guitar")
        for instrument in (self.guitar, self.piano):  # the strip's switch already says which
            instrument.name.setVisible(mode == "both")
        self.refresh()
        self.adjustSize()

    def set_flags(self, current: bool, selected: bool) -> None:
        if (current, selected) == (self.current, self.selected):
            return
        self.current, self.selected = current, selected
        self._style()

    def _style(self) -> None:
        theme.restyle(self, now=self.current, selected=self.selected)
        theme.restyle(self.title, now=self.current)

    def _step(self, instrument: str, delta: int) -> None:
        shown = self.item.shown
        if instrument == "guitar":
            self.positions.step(Positions.guitar_key(shown), len(self.guitar_positions), delta)
        else:
            self.positions.step(Positions.piano_key(shown), len(self.piano_voicings), delta)

    def refresh(self) -> None:
        """Draws again only what changed: the store says when any chord's position changes."""
        if self.item is None:
            return
        shown = self.item.shown
        g = self.positions.index(Positions.guitar_key(shown), len(self.guitar_positions))
        k = self.positions.index(Positions.piano_key(shown), len(self.piano_voicings))
        drawn = (shown, g, k, self.mode)
        if drawn == self._drawn:
            return
        animate = self._drawn is not None and self._drawn[0] == shown
        self._drawn = drawn
        words = [shown.shape.title]
        if self.mode != "piano":
            if self.guitar_positions:
                f = self.guitar_positions[g]
                self.guitar.diagram.set_fingering(f, shown.shape, shown.capo, animate=animate)
                self.guitar.set_place(g, len(self.guitar_positions), f.kind)
                self.guitar.diagram.setToolTip(describe_fingering(f, shown.shape))
                words.append(describe_fingering(f, shown.shape))
            else:
                text = "Pas de position vérifiée à la guitare."
                self.guitar.diagram.set_fingering(None, shown.shape, shown.capo, text, animate)
                self.guitar.set_place(0, 0, "Aucune position")
                words.append(text)
        if self.mode != "guitar":
            v = self.piano_voicings[k]
            self.piano.diagram.set_voicing(v, shown.sound, animate=animate)
            kind = f"son réel {shown.sound.title}" if shown.capo else v.name
            self.piano.set_place(k, len(self.piano_voicings), kind)
            self.piano.diagram.setToolTip(describe_voicing(v, shown.sound))
            words.append(describe_voicing(v, shown.sound))
        self.setAccessibleName(f"{shown.shape.title}, {self.item.place}")
        self.setAccessibleDescription(" ".join(words[1:]))

    # Mouse and keyboard: the card picks its chord; its arrows only change the position.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.chosen.emit()
        super().mousePressEvent(event)

    _KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Left, Qt.Key.Key_Right)

    def event(self, event):
        # The window uses these keys too: a focused card takes them first.
        if (
            event.type() == event.Type.ShortcutOverride
            and event.key() in self._KEYS
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.chosen.emit()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.moved.emit(-1 if key == Qt.Key.Key_Left else 1)
        else:
            super().keyPressEvent(event)


class _Strip(QScrollArea):
    """Asks for the cards' height, but gives it up first when the window is short."""

    def sizeHint(self):
        inner = self.widget().sizeHint() if self.widget() else QSize(0, 0)
        return QSize(super().sizeHint().width(), inner.height() + 16)

    def minimumSizeHint(self):
        return QSize(0, 0)


class SongChords(QFrame):
    viewChanged = Signal(str)
    modeChanged = Signal(str)
    stateChanged = Signal(str)
    chordChosen = Signal(float)  # where the chord is, for the panel; playback does not move

    def __init__(self, positions: Positions):
        super().__init__()
        self.setObjectName("songchords")
        self.positions = positions
        self.view = "all"
        self.mode = "guitar"
        self.state = "compact"
        self.restore = "compact"
        self.all_items: list[Item] = []
        self.next_items: list[Item] = []
        self.all_cards: list[ChordCard] = []
        self.next_cards: list[ChordCard] = []
        self.selected = None
        self.current = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 8)
        outer.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel("Accords du morceau")
        title.setObjectName("h2")
        self.count = QLabel()
        self.count.setObjectName("caption")
        self.count.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(title)
        head.addSpacing(4)
        head.addWidget(self.count, 1)

        self.view_buttons = {}
        group = QButtonGroup(self)
        tips = {
            "all": "Chaque accord du morceau une fois, dans l'ordre où il arrive. "
            "Rien à lancer : cliquer un accord l'affiche dans le panneau.",
            "next": "L'accord en cours et les suivants, qui avancent avec la lecture.",
        }
        for view, text in zip(VIEWS, ("Tous les accords", "À venir"), strict=True):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(tips[view])
            b.setAccessibleName(f"Accords du morceau : {text.lower()}")
            group.addButton(b)
            self.view_buttons[view] = b
            b.clicked.connect(lambda _=False, v=view: self._choose_view(v))
        self.view_switch = segmented(self.view_buttons.values())
        head.addWidget(self.view_switch)
        head.addSpacing(8)
        self.mode_buttons = {}
        group = QButtonGroup(self)
        for mode, text in zip(MODES, ("Guitare", "Piano", "Les deux"), strict=True):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setAccessibleName(f"Accords du morceau : {text.lower()}")
            group.addButton(b)
            self.mode_buttons[mode] = b
            b.clicked.connect(lambda _=False, m=mode: self._choose_mode(m))
        self.mode_switch = segmented(self.mode_buttons.values())
        head.addWidget(self.mode_switch)
        head.addSpacing(6)
        self.resize_button = QToolButton()
        self.resize_button.setObjectName("step")
        self.resize_button.clicked.connect(
            lambda: self.set_state("expanded" if self.state == "compact" else "compact")
        )
        self.hide_button = QToolButton()
        self.hide_button.setObjectName("step")
        self.hide_button.setIcon(theme.icon("close", size=14))
        self.hide_button.setAccessibleName("Masquer les accords du morceau")
        self.hide_button.setToolTip("Masquer les accords du morceau (T)")
        self.hide_button.clicked.connect(lambda: self.set_state("hidden"))
        head.addWidget(self.resize_button)
        head.addWidget(self.hide_button)
        outer.addLayout(head)

        self.scroll = _Strip()
        self.scroll.setAccessibleName("Accords du morceau")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.flow = _Flow(self.inner)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.flow.addWidget(self.empty)
        self.scroll.setWidget(self.inner)
        outer.addWidget(self.scroll, 1)
        self.set_view("all")
        self.set_mode("guitar")
        self.set_state("compact", emit=False)

    # Settings ----------------------------------------------------------------------------------
    def _choose_view(self, view: str) -> None:
        self.set_view(view)
        self.viewChanged.emit(self.view)

    def _choose_mode(self, mode: str) -> None:
        self.set_mode(mode)
        self.modeChanged.emit(self.mode)

    def set_view(self, view: str) -> None:
        self.view = view if view in VIEWS else "all"
        self.view_buttons[self.view].setChecked(True)
        self._show()

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "guitar"
        self.mode_buttons[self.mode].setChecked(True)
        for card in self.all_cards + self.next_cards:
            if card.item is not None:
                card.set_mode(self.mode)
        self.flow.invalidate()

    def set_state(self, state: str, emit: bool = True) -> None:
        self.state = state if state in STATES else "compact"
        if self.state != "hidden":
            self.restore = self.state
        compact = self.state == "compact"
        self.flow.wrap = not compact
        policy = Qt.ScrollBarPolicy
        self.scroll.setHorizontalScrollBarPolicy(
            policy.ScrollBarAsNeeded if compact else policy.ScrollBarAlwaysOff
        )
        self.resize_button.setIcon(theme.icon("grow" if compact else "shrink", size=14))
        self.resize_button.setAccessibleName("Agrandir" if compact else "Réduire")
        self.resize_button.setToolTip(
            "Agrandir : tous les accords sur plusieurs rangées"
            if compact
            else "Réduire : une rangée qui défile"
        )
        self.flow.invalidate()
        self.inner.updateGeometry()
        self.setVisible(self.state != "hidden")
        if emit:
            self.stateChanged.emit(self.state)

    def toggle(self) -> None:
        self.set_state(self.restore if self.state == "hidden" else "hidden")

    # Content -----------------------------------------------------------------------------------
    def set_all(self, items: list[Item]) -> None:
        self.all_items = items
        if self.view == "all":
            self._show()

    def set_upcoming(self, items: list[Item]) -> None:
        self.next_items = items
        if self.view == "next":
            self._show()

    def set_current(self, key) -> None:
        """The chord playing, outlined in the list of all chords."""
        self.current = key
        for card in self.all_cards:
            if card.item is not None:
                card.set_flags(chord_key(card.item.shown) == key, self._is_selected(card))

    def set_selected(self, key) -> None:
        self.selected = key
        for card in self.all_cards + self.next_cards:
            if card.item is not None:
                card.set_flags(card.item.current, self._is_selected(card))

    def _is_selected(self, card: ChordCard) -> bool:
        return self.selected is not None and chord_key(card.item.shown) == self.selected

    def cards(self) -> list[ChordCard]:
        """The cards on show, in order."""
        pool = self.all_cards if self.view == "all" else self.next_cards
        return [c for c in pool if not c.isHidden()]

    def _show(self) -> None:
        showing, items = (
            (self.all_cards, self.all_items)
            if self.view == "all"
            else (self.next_cards, self.next_items)
        )
        other = self.next_cards if self.view == "all" else self.all_cards
        for card in other:
            card.hide()
        while len(showing) < len(items):
            card = ChordCard(self.positions)
            card.chosen.connect(lambda c=card: self._chosen(c))
            card.moved.connect(lambda d, c=card: self._move(c, d))
            self.flow.addWidget(card)
            showing.append(card)
        for card, item in zip(showing, items, strict=False):
            if self.view == "all":
                item.current = chord_key(item.shown) == self.current
            card.set_item(item, self.mode)
            card.set_flags(item.current, self._is_selected(card))
            card.show()
        for card in showing[len(items) :]:
            card.hide()
        if self.view == "all":
            n = len(items)
            self.count.setText(f"{n} accord{'s' if n > 1 else ''} différent{'s' if n > 1 else ''}")
            self.empty.setText("Aucun accord dans ce morceau.")
        else:
            self.count.setText("l'accord en cours et les suivants")
            self.empty.setText("Plus d'accord à venir : c'est la fin du morceau.")
        self.empty.setVisible(not items)
        self.flow.invalidate()
        self.scroll.updateGeometry()  # the strip asks for the cards' new height

    def _chosen(self, card: ChordCard) -> None:
        self.chordChosen.emit(card.item.time)

    def _move(self, card: ChordCard, delta: int) -> None:
        cards = self.cards()
        i = cards.index(card) + delta
        if 0 <= i < len(cards):
            cards[i].setFocus(Qt.FocusReason.TabFocusReason)
            self.scroll.ensureWidgetVisible(cards[i], 12, 0)
