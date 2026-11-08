"""Colours, type and icons: one place, so that every screen looks like the same program."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

BG = "#0F1115"
SURFACE = "#171A21"
SURFACE_2 = "#1F232C"
SURFACE_3 = "#2A2F3A"
BORDER = "#333945"
TEXT = "#EEF0F4"
TEXT_2 = "#AEB4C0"  # 8.9:1 on BG, 7.9:1 on SURFACE
TEXT_3 = "#8A91A0"  # for large or secondary marks only, 5.7:1 on BG
ACCENT = "#F5B94A"  # the current chord: a stage light
ON_ACCENT = "#17130A"
EDITED = "#5FD6C6"
LOOP = "#8F9BFF"
SELECT = "#6FB1FF"
ERROR = "#FF8A80"
ROLE_COLORS = {"secondary_dominant": "#8FD08A", "borrowed": "#E6A2F0", "chromatic": "#F0A58A"}
FONT = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"


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


QSS = f"""
* {{ font-family: "{FONT}", "{FONT_FALLBACK}"; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QStackedWidget, #page {{ background: {BG}; }}
QWidget#bar {{ background: {SURFACE}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#h1 {{ font-size: 32px; font-weight: 600; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {TEXT_2}; }}
QLabel#caption {{ color: {TEXT_2}; font-size: 12px; }}
QLabel#time {{ font-size: 15px; font-weight: 600; }}
QLabel#error {{ color: {ERROR}; }}
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 12px; min-height: 22px;
}}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {BORDER}; }}
QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QSlider:focus {{
    border: 1px solid {SELECT};
}}
QPushButton:disabled, QToolButton:disabled {{ color: {TEXT_3}; background: {SURFACE}; }}
QPushButton:checked, QToolButton:checked {{
    background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; font-weight: 600;
}}
QPushButton#primary {{
    background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT}; font-weight: 600;
    padding: 8px 18px;
}}
QPushButton#primary:hover {{ background: #FFCB66; }}
QPushButton#primary:disabled {{ background: {SURFACE_2}; color: {TEXT_3}; border-color: {BORDER}; }}
QPushButton#link {{ background: transparent; border: none; color: {SELECT}; padding: 2px 4px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#recent {{ text-align: left; padding: 10px 14px; background: {SURFACE}; }}
QPushButton#recent:hover {{ background: {SURFACE_2}; }}
QToolButton#play {{
    background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 22px;
    min-width: 42px; min-height: 42px; padding: 0;
}}
QToolButton#play:hover {{ background: #FFCB66; }}
QToolButton#play:disabled {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QToolButton::menu-indicator {{ image: none; }}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {SELECT}; selection-color: {BG};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_3};
    selection-color: {TEXT}; outline: 0;
}}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
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
QScrollBar::handle:vertical:hover {{ background: {BORDER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 40px; margin: 2px; }}
QScrollBar::handle:horizontal:hover {{ background: {BORDER}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ width: 0; background: none; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 8px; border: 1px solid {TEXT_2}; background: {SURFACE_2};
}}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 3px solid {SURFACE_3}; }}
QToolButton#star:checked {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QToolButton#step {{ padding: 4px 5px; min-height: 20px; min-width: 20px; }}
QListWidget#side {{ background: transparent; border: none; outline: 0; }}
QListWidget#side::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget#side::item:hover {{ background: {SURFACE_2}; }}
QListWidget#side::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}
QTableView#songs, QListView#cards {{
    background: {BG}; border: none; outline: 0; selection-background-color: {SURFACE_3};
    selection-color: {TEXT};
}}
QTableView#songs::item {{ padding: 0 6px; border-bottom: 1px solid {SURFACE_2}; }}
QTableView#songs::item:selected {{ background: {SURFACE_3}; }}
QHeaderView::section {{
    background: {BG}; color: {TEXT_3}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-size: 12px; font-weight: 600;
}}
QHeaderView::section:hover {{ color: {TEXT}; }}
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


def icon(name: str, color: str = TEXT, size: int = 18) -> QIcon:
    result = QIcon(pixmap(name, color, size))
    result.addPixmap(pixmap(name, TEXT_3, size), QIcon.Mode.Disabled)
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
