"""Colours, type and icons: one place, so that every screen looks like the same program."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

# Direction: a music stand under a stage light. Calm, exact, warm. The amber marks what is
# playing now (current chord, beat, play) and the one primary action of a screen; everything
# else stays in warm graphite and lets the grid and the diagrams be the bright things.
# See docs/DESIGN.md.

# Neutrals, darkest to lightest: page, bars and panels, controls, raised or selected.
BG = "#121316"
SURFACE = "#18191D"
SURFACE_2 = "#202126"
SURFACE_3 = "#2B2C32"
BORDER = "#3A3B42"  # hairlines around controls and between panels
BORDER_SOFT = "#26272C"  # between rows
BORDER_HOVER = "#4A4B53"
TEXT = "#EEEDE9"  # 15.9:1 on BG
TEXT_2 = "#B3B1AA"  # 8.7:1 on BG, 7.5:1 on SURFACE_2
TEXT_3 = "#8E8C85"  # 5.5:1 on BG, 4.8:1 on SURFACE_2: hints and disabled text
# The stage light.
ACCENT = "#F5B94A"  # the current chord, the play button, the primary action
ACCENT_HOVER = "#FFCB66"
ON_ACCENT = "#17130A"  # 10.5:1 on ACCENT
ACCENT_SOFT = "#3A3020"  # a switch that is on: a glow, not a light
ACCENT_SOFT_HOVER = "#463A26"
ACCENT_LINE = "#7A6234"
ACCENT_TEXT = "#FFD48A"  # 9.3:1 on ACCENT_SOFT
# Meanings.
EDITED = "#5FD6C6"
LOOP = "#8F9BFF"
SELECT = "#6FB1FF"  # selection and keyboard focus
ERROR = "#FF8A80"
ROLE_COLORS = {"secondary_dominant": "#8FD08A", "borrowed": "#E6A2F0", "chromatic": "#F0A58A"}
FONT = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"

# Space on a 4 px grid, and the few radii.
S1, S2, S3, S4, S6 = 4, 8, 12, 16, 24
RADIUS = 6
RADIUS_SMALL = 4
# Type scale in pixels: caption, body, heading, song title, title, chord now, display.
SIZE_CAPTION, SIZE_BODY, SIZE_H2, SIZE_SONG = 12, 13, 15, 17
SIZE_TITLE, SIZE_NOW, SIZE_H1 = 20, 30, 32


def app_font(size: float = 13, weight: int = 400) -> QFont:
    font = QFont([FONT, FONT_FALLBACK])
    font.setPixelSize(max(1, int(size)))
    font.setWeight(QFont.Weight(weight))
    return font


def chord_color(root_pc: int, alpha: int = 255) -> QColor:
    """A colour per root, laid around the circle of fifths so that related chords look related."""
    color = QColor.fromHslF((root_pc * 7 % 12) / 12, 0.42, 0.46)
    color.setAlpha(alpha)
    return color


def restyle(widget, **props) -> None:
    """Sets the dynamic properties the style sheet reads (now, selected, edge…) and applies
    them: Qt does not restyle a widget by itself when a property changes."""
    for name, value in props.items():
        widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


QSS = f"""
* {{ font-family: "{FONT}", "{FONT_FALLBACK}"; font-size: {SIZE_BODY}px; color: {TEXT}; }}
QMainWindow, QDialog, QStackedWidget, #page {{ background: {BG}; }}
QWidget#bar {{ background: {SURFACE}; }}
QLabel {{ background: transparent; }}

/* Type: weights 400 and 600, 700 only for chord names. */
QLabel#h1 {{ font-size: {SIZE_H1}px; font-weight: 600; }}
QLabel#title {{ font-size: {SIZE_TITLE}px; font-weight: 600; }}
QLabel#songTitle {{ font-size: {SIZE_SONG}px; font-weight: 600; }}
QLabel#h2 {{ font-size: {SIZE_H2}px; font-weight: 600; }}
QLabel#muted {{ color: {TEXT_2}; }}
QLabel#caption {{ color: {TEXT_2}; font-size: {SIZE_CAPTION}px; }}
QLabel#time {{ font-size: {SIZE_H2}px; font-weight: 600; }}
QLabel#error {{ color: {ERROR}; }}
QLabel#chordNow {{ font-size: {SIZE_NOW}px; font-weight: 700; color: {ACCENT}; }}
QLabel#chordNext {{ font-size: 18px; color: {TEXT_2}; }}
QLabel#panelChord {{ font-size: 26px; font-weight: 700; color: {ACCENT}; }}
QLabel#cardChord {{ font-size: {SIZE_TITLE}px; font-weight: 700; color: {TEXT}; }}
QLabel#cardChord[now="true"] {{ color: {ACCENT}; }}
QLineEdit#chordInput {{ font-size: 22px; font-weight: 600; padding: 8px 12px; }}
QLabel#badge {{
    color: {ACCENT_TEXT}; background: {ACCENT_SOFT}; border: 1px solid {ACCENT_LINE};
    border-radius: {RADIUS_SMALL}px; padding: 1px 6px; font-size: {SIZE_CAPTION}px;
    font-weight: 600;
}}
QLabel#key {{
    background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: {RADIUS_SMALL}px;
    padding: 1px 6px; font-weight: 600;
}}
QLabel#sectionHead {{ color: {TEXT_2}; font-size: {SIZE_CAPTION}px; font-weight: 600; }}

/* Buttons: neutral by default, a soft amber glow when switched on, solid amber only for
   the primary action and play. */
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    padding: 6px 12px; min-height: 22px;
}}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_3}; border-color: {BORDER_HOVER}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {TEXT_3}; background: {SURFACE}; }}
QPushButton:checked, QToolButton:checked {{
    background: {ACCENT_SOFT}; border-color: {ACCENT_LINE}; color: {ACCENT_TEXT};
}}
QPushButton:checked:hover, QToolButton:checked:hover {{ background: {ACCENT_SOFT_HOVER}; }}
QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QSlider:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {SELECT};
}}
QToolButton::menu-indicator {{ image: none; }}
QPushButton#primary, QToolButton#primary {{
    background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT}; font-weight: 600;
    padding: 6px 16px;
}}
QPushButton#primary:hover, QToolButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:focus, QToolButton#primary:focus {{ border: 2px solid {ON_ACCENT}; }}
QPushButton#primary:disabled {{ background: {SURFACE_2}; color: {TEXT_3}; border-color: {BORDER}; }}
QPushButton#link {{
    background: transparent; border: 1px solid transparent; color: {SELECT}; padding: 2px 4px;
    min-height: 0;
}}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#link:focus {{ border: 1px solid {SELECT}; }}
QPushButton#recent {{ text-align: left; padding: 10px 14px; background: {SURFACE}; }}
QPushButton#recent:hover {{ background: {SURFACE_2}; }}

/* In the song's header, and for icon-only buttons in any bar, tool buttons stay quiet until
   pointed at: chrome, not content. A text button in a work bar keeps its frame, like its
   neighbours. toolButtonStyle 0 is Qt.ToolButtonIconOnly; restyle() after changing it. */
QWidget#bar[quiet="true"] QToolButton, QWidget#bar QToolButton[toolButtonStyle="0"] {{ background: transparent; border: 1px solid transparent; }}
QWidget#bar[quiet="true"] QToolButton:hover, QWidget#bar QToolButton[toolButtonStyle="0"]:hover {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QWidget#bar[quiet="true"] QToolButton:pressed, QWidget#bar QToolButton[toolButtonStyle="0"]:pressed {{ background: {SURFACE_3}; }}
QWidget#bar[quiet="true"] QToolButton:checked, QWidget#bar QToolButton[toolButtonStyle="0"]:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT_LINE}; color: {ACCENT_TEXT}; }}
QWidget#bar[quiet="true"] QToolButton:checked:hover, QWidget#bar QToolButton[toolButtonStyle="0"]:checked:hover {{ background: {ACCENT_SOFT_HOVER}; }}
QWidget#bar[quiet="true"] QToolButton:focus, QWidget#bar QToolButton[toolButtonStyle="0"]:focus {{ border: 1px solid {SELECT}; }}
QWidget#bar[quiet="true"] QToolButton:disabled, QWidget#bar QToolButton[toolButtonStyle="0"]:disabled {{ background: transparent; }}
QToolButton#play, QWidget#bar QToolButton#play {{
    background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 22px;
    min-width: 42px; min-height: 42px; padding: 0;
}}
QToolButton#play:hover, QWidget#bar QToolButton#play:hover {{
    background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER};
}}
QToolButton#play:focus, QWidget#bar QToolButton#play:focus {{ border: 2px solid {ON_ACCENT}; }}
QToolButton#play:disabled, QWidget#bar QToolButton#play:disabled {{
    background: {SURFACE_2}; border-color: {BORDER};
}}
QToolButton#star:checked, QWidget#bar QToolButton#star:checked {{
    background: transparent; border-color: transparent;
}}
QToolButton#star:checked:hover, QWidget#bar QToolButton#star:checked:hover {{
    background: {SURFACE_2}; border-color: {BORDER};
}}
QToolButton#sortDir:checked {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QToolButton#step {{ padding: 4px; min-height: 20px; min-width: 20px; }}

/* Segmented control: one choice among a few, side by side in a recessed track. */
QFrame#segmented {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 7px; }}
QFrame#segmented QPushButton, QFrame#segmented QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 5px;
    padding: 3px 10px; margin: 2px; min-height: 20px; color: {TEXT_2};
}}
QFrame#segmented QPushButton:hover, QFrame#segmented QToolButton:hover {{
    background: {SURFACE_2}; color: {TEXT};
}}
QFrame#segmented QPushButton:checked, QFrame#segmented QToolButton:checked {{
    background: {SURFACE_3}; border-color: {TEXT_3}; color: {TEXT};
}}
QFrame#segmented QPushButton:focus, QFrame#segmented QToolButton:focus {{
    border: 1px solid {SELECT};
}}

/* Fields */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    padding: 5px 8px; selection-background-color: {SELECT}; selection-color: {BG};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: {BORDER_HOVER}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QLineEdit QToolButton {{ background: transparent; border: none; padding: 0; min-height: 0; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_3};
    selection-color: {TEXT}; outline: 0;
}}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: {RADIUS_SMALL}px; }}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMenu::item:disabled {{ color: {TEXT_3}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QProgressBar {{
    background: {SURFACE_2}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {TEXT_2}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QScrollArea {{ border: none; background: {BG}; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 40px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 40px; margin: 2px; }}
QScrollBar::handle:horizontal:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ width: 0; background: none; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 8px; border: 1px solid {TEXT_2}; background: {SURFACE_2};
}}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 3px solid {SURFACE_3}; }}

/* Panels: told apart by a hairline and a tone, never by a shadow. */
QFrame#panel {{ background: {SURFACE}; border: none; }}
QFrame#panel[edge="left"] {{ border-left: 1px solid {BORDER}; }}
QFrame#panel[edge="top"] {{ border-top: 1px solid {BORDER}; }}
QFrame#songchords {{ background: {SURFACE}; border: none; border-top: 1px solid {BORDER}; }}
QFrame#songchords QScrollArea, QFrame#songchords QScrollArea > QWidget > QWidget {{
    background: {SURFACE};
}}
QFrame#card {{ background: {SURFACE_2}; border: 2px solid {SURFACE_2}; border-radius: 8px; }}
QFrame#card[now="true"] {{ border-color: {ACCENT}; }}
QFrame#card[selected="true"] {{ border-color: {SELECT}; }}
QFrame#card:focus {{ border-color: {SELECT}; }}

/* Library */
QListWidget#side {{ background: transparent; border: 1px solid transparent; outline: 0; }}
QListWidget#side::item {{ padding: 7px 30px 7px 8px; border-radius: {RADIUS}px; }}
QListWidget#side::item:hover {{ background: {SURFACE_2}; }}
QListWidget#side::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}
QListWidget#side::item:focus {{ border: 1px solid {SELECT}; }}  /* keyboard focus on the current view */
QTableView#songs, QListView#cards {{
    background: {BG}; border: none; outline: 0; selection-background-color: {SURFACE_3};
    selection-color: {TEXT};
}}
QTableView#songs::item {{ padding: 0 6px; border-bottom: 1px solid {BORDER_SOFT}; }}
QTableView#songs::item:selected {{ background: {SURFACE_3}; }}
QHeaderView::section {{
    background: {BG}; color: {TEXT_2}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-size: {SIZE_CAPTION}px; font-weight: 600;
}}
QHeaderView::section:hover {{ color: {TEXT}; }}
QHeaderView {{ background: {BG}; border: none; }}
QLabel#drop {{
    background: rgba(245, 185, 74, 36); border: 2px dashed {ACCENT}; border-radius: 12px;
    font-size: 26px; font-weight: 600;
}}
"""

# On a 24 × 24 grid: a list of strokes (open polylines) and fills (closed polygons).
_STAR = [(12, 3.3), (14.4, 9.6), (21, 9.9), (15.8, 14), (17.6, 20.5), (12, 16.8), (6.4, 20.5),
         (8.2, 14), (3, 9.9), (9.6, 9.6)]  # fmt: skip
_ICONS: dict[str, dict] = {
    "play": {"fill": [[(7, 4), (20, 12), (7, 20)]]},
    "pause": {"fill": [[(6, 4), (10, 4), (10, 20), (6, 20)], [(14, 4), (18, 4), (18, 20), (14, 20)]]},
    "prev": {"fill": [[(19, 5), (9, 12), (19, 19)], [(5, 5), (8, 5), (8, 19), (5, 19)]]},
    "next": {"fill": [[(5, 5), (15, 12), (5, 19)], [(16, 5), (19, 5), (19, 19), (16, 19)]]},
    "loop": {
        "stroke": [
            [(17, 2), (21, 6), (17, 10)], [(3, 12), (3, 10), (5, 6), (21, 6)],
            [(7, 22), (3, 18), (7, 14)], [(21, 12), (21, 14), (19, 18), (3, 18)],
        ]
    },
    "open": {
        "stroke": [[(3, 6), (9, 6), (11, 9), (21, 9), (21, 19), (3, 19), (3, 6)]],
    },
    "export": {"stroke": [[(12, 3), (12, 15)], [(7, 10), (12, 15), (17, 10)], [(4, 20), (20, 20)]]},
    "undo": {"stroke": [[(8, 5), (3, 10), (8, 15)], [(3, 10), (15, 10), (20, 13), (20, 17), (16, 20), (10, 20)]]},
    "redo": {"stroke": [[(16, 5), (21, 10), (16, 15)], [(21, 10), (9, 10), (4, 13), (4, 17), (8, 20), (14, 20)]]},
    "home": {"stroke": [[(3, 11), (12, 3), (21, 11)], [(5, 10), (5, 21), (19, 21), (19, 10)]]},
    "menu": {"stroke": [[(4, 6), (20, 6)], [(4, 12), (20, 12)], [(4, 18), (20, 18)]]},
    "minus": {"stroke": [[(6, 12), (18, 12)]]},
    "plus": {"stroke": [[(6, 12), (18, 12)], [(12, 6), (12, 18)]]},
    "edit": {"stroke": [[(4, 20), (5, 15), (16, 4), (20, 8), (9, 19), (4, 20)]]},
    "close": {"stroke": [[(6, 6), (18, 18)], [(18, 6), (6, 18)]]},
    "left": {"stroke": [[(15, 5), (8, 12), (15, 19)]]},
    "right": {"stroke": [[(9, 5), (16, 12), (9, 19)]]},
    "shrink": {"stroke": [[(4, 10), (10, 10), (10, 4)], [(20, 14), (14, 14), (14, 20)]]},
    "grow": {"stroke": [[(4, 10), (4, 4), (10, 4)], [(20, 14), (20, 20), (14, 20)]]},
    "diagram": {
        "stroke": [[(5, 4), (19, 4)], [(5, 9), (19, 9)], [(5, 14), (19, 14)], [(5, 19), (19, 19)],
                   [(5, 4), (5, 21)], [(9.7, 4), (9.7, 21)], [(14.3, 4), (14.3, 21)],
                   [(19, 4), (19, 21)]],
        "fill": [[(8, 10.5), (11.4, 10.5), (11.4, 12.5), (8, 12.5)]],
    },
    "cards": {"stroke": [[(3, 6), (10, 6), (10, 18), (3, 18), (3, 6)],
                         [(14, 6), (21, 6), (21, 18), (14, 18), (14, 6)]]},
    "star": {"fill": [_STAR]},
    "star_line": {"stroke": [_STAR + [_STAR[0]]]},
    "rows": {"stroke": [[(4, 6), (20, 6)], [(4, 10), (20, 10)], [(4, 14), (20, 14)], [(4, 18), (20, 18)]]},
    "tiles": {"stroke": [[(4, 4), (10, 4), (10, 10), (4, 10), (4, 4)], [(14, 4), (20, 4), (20, 10), (14, 10), (14, 4)],
                         [(4, 14), (10, 14), (10, 20), (4, 20), (4, 14)], [(14, 14), (20, 14), (20, 20), (14, 20), (14, 14)]]},
    "volume": {
        "fill": [[(3, 9), (7, 9), (12, 5), (12, 19), (7, 15), (3, 15)]],
        "stroke": [[(15, 9), (17, 12), (15, 15)], [(18, 6), (21, 12), (18, 18)]],
    },
    "search": {"stroke": [[(10.5, 4), (14.5, 5.5), (16.5, 9.5), (15, 14), (10.5, 16.5), (6, 15),
                           (4, 10.5), (5.5, 6), (10.5, 4)], [(15, 15), (20, 20)]]},
    "sliders": {"stroke": [[(4, 7), (20, 7)], [(4, 17), (20, 17)], [(9, 4.5), (9, 9.5)],
                           [(15, 14.5), (15, 19.5)]]},
    "mixer": {"stroke": [[(6, 4), (6, 20)], [(12, 4), (12, 20)], [(18, 4), (18, 20)]],
              "fill": [[(3.5, 13), (8.5, 13), (8.5, 16), (3.5, 16)], [(9.5, 7), (14.5, 7), (14.5, 10), (9.5, 10)],
                       [(15.5, 11), (20.5, 11), (20.5, 14), (15.5, 14)]]},
    "more": {"fill": [[(5, 11), (7, 11), (7, 13), (5, 13)], [(11, 11), (13, 11), (13, 13), (11, 13)],
                      [(17, 11), (19, 11), (19, 13), (17, 13)]]},
    "lyrics": {"stroke": [[(4, 6), (20, 6)], [(4, 11), (16, 11)], [(4, 16), (12, 16)],
                          [(17, 14), (17, 20)]], "fill": [[(14, 18), (17, 18), (17, 21), (14, 21)]]},
    "collection": {"stroke": [[(4, 8), (20, 8), (20, 20), (4, 20), (4, 8)], [(6, 5), (18, 5)]]},
    "clock": {"stroke": [[(12, 3.5), (18, 6), (20.5, 12), (18, 18), (12, 20.5), (6, 18), (3.5, 12),
                          (6, 6), (12, 3.5)], [(12, 7.5), (12, 12), (15.5, 14)]]},
    "music": {"stroke": [[(9, 17), (9, 5), (19, 3), (19, 15)]],
              "fill": [[(5, 15.5), (9, 15.5), (9, 19), (5, 19)], [(15, 13.5), (19, 13.5), (19, 17), (15, 17)]]},
    "hidden": {"stroke": [[(3, 12), (7, 7.5), (12, 6), (17, 7.5), (21, 12), (17, 16.5), (12, 18),
                           (7, 16.5), (3, 12)], [(4, 20), (20, 4)]]},
    "save": {"stroke": [[(5, 4), (16, 4), (20, 8), (20, 20), (4, 20), (4, 4), (5, 4)],
                        [(8, 4), (8, 9), (15, 9), (15, 4)], [(8, 20), (8, 14), (16, 14), (16, 20)]]},
    "down": {"stroke": [[(6, 9), (12, 15), (18, 9)]]},
    "sort_up": {"stroke": [[(8, 20), (8, 4)], [(4, 8), (8, 4), (12, 8)], [(14, 8), (20, 8)],
                           [(14, 13), (19, 13)], [(14, 18), (18, 18)]]},
    "sort_down": {"stroke": [[(8, 4), (8, 20)], [(4, 16), (8, 20), (12, 16)], [(14, 6), (20, 6)],
                             [(14, 11), (19, 11)], [(14, 16), (18, 16)]]},
}  # fmt: skip


def pixmap(name: str, color: str = TEXT, size: int = 18, ratio: float = 2.0) -> QPixmap:
    px = QPixmap(QSize(int(size * ratio), int(size * ratio)))
    px.setDevicePixelRatio(ratio)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    spec = _ICONS[name]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    for poly in spec.get("fill", []):
        path = QPainterPath(QPointF(*poly[0]))
        for point in poly[1:]:
            path.lineTo(*point)
        path.closeSubpath()
        p.drawPath(path)
    pen = QPen(QColor(color), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for line in spec.get("stroke", []):
        path = QPainterPath(QPointF(*line[0]))
        for point in line[1:]:
            path.lineTo(*point)
        p.drawPath(path)
    p.end()
    return px


def icon(name: str, color: str = TEXT, size: int = 18, on: str | None = ACCENT_TEXT) -> QIcon:
    """`on`: the colour when a switch is on, the glow's (None keeps `color`, as in a
    segmented control, where the choice shows by its background)."""
    result = QIcon(pixmap(name, color, size))
    result.addPixmap(pixmap(name, TEXT_3, size), QIcon.Mode.Disabled)
    if on is not None and color == TEXT:
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active):
            result.addPixmap(pixmap(name, on, size), mode, QIcon.State.On)
    return result


def app_image(size: int = 256) -> QImage:
    """The program's icon: a grid of chord cells with one lit, drawn rather than shipped."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(BG))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)
    gap, margin = size * 0.05, size * 0.14
    cell = (size - 2 * margin - gap) / 2
    for row in range(2):
        for col in range(2):
            lit = (row, col) == (0, 0)
            p.setBrush(QColor(ACCENT if lit else SURFACE_3))
            rect = QRectF(margin + col * (cell + gap), margin + row * (cell + gap), cell, cell)
            p.drawRoundedRect(rect, size * 0.05, size * 0.05)
    p.end()
    return image
