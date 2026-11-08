"""The chart and the chord sheet as PDF: Qt's own writer, nothing to install."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)

from ..export import bar_symbols, header
from ..project import Project
from . import diagrams, theme
from .diagrams import GuitarDiagram, PianoDiagram, Positions, positions_of

BARS_PER_LINE = 4
INK = QColor("#111111")
FAINT = QColor("#9A9A9A")
ROW_H = 62  # one line of the grid
ROW_GAP = 10

# The chord sheet is laid out in screen pixels and scaled to the page: at 144 dpi, 1.5 makes a
# pixel about the size it is on a screen, so the diagrams print as they look in the program.
SHEET_SCALE = 1.5
CARD_GAP = 12
NAME_H = 30
PLACE_H = 16
CAPTION_H = 18
GUITAR_H = 176
PIANO_H = 112
FOOTER_H = 22  # device pixels at the foot of each page
COLUMNS = {"guitar": 4, "piano": 3, "both": 3}

# What the diagrams draw in on paper: dark lines on white, the colours a little deeper.
PRINT_COLORS = {
    "BG": "#333333",
    "SURFACE": "#FFFFFF",
    "TEXT": "#111111",
    "TEXT_2": "#3A3A3A",
    "TEXT_3": "#8A8A8A",
    "BORDER": "#BBBBBB",
    "ACCENT": "#C2410C",
    "ON_ACCENT": "#FFFFFF",
    "SELECT": "#2F6FB5",
}
PRINT_KEYS = {"WHITE_KEY": "#FFFFFF", "BLACK_KEY": "#222222"}


def _writer(path: Path, title: str, landscape: bool = False) -> tuple[QPdfWriter, QPainter]:
    writer = QPdfWriter(str(path))
    orientation = (
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait
    )
    writer.setPageLayout(
        QPageLayout(QPageSize(QPageSize.PageSizeId.A4), orientation, QMarginsF(14, 14, 14, 14))
    )
    writer.setResolution(144)
    writer.setTitle(title or "LocalChords")
    writer.setCreator("LocalChords")
    p = QPainter(writer)
    if not p.isActive():
        raise OSError(f"Impossible d'écrire dans {path}")
    return writer, p


def _title(p: QPainter, project: Project, width: float, draw: bool = True) -> float:
    """The title and what to know before playing; returns where the page goes on."""
    fields = dict(header(project))
    title = fields.pop("Titre", "")
    p.setPen(INK)
    p.setFont(theme.app_font(30, 700))
    metrics = QFontMetricsF(p.font())
    if draw:
        p.drawText(
            QRectF(0, 0, width, metrics.height()),
            Qt.AlignmentFlag.AlignLeft,
            metrics.elidedText(title, Qt.TextElideMode.ElideRight, width),
        )
    y = metrics.height() + 4
    p.setFont(theme.app_font(14))
    metrics = QFontMetricsF(p.font())
    line = "   ·   ".join(f"{k} : {v}" for k, v in fields.items())
    box = metrics.boundingRect(QRectF(0, 0, width, 1000), Qt.TextFlag.TextWordWrap, line)
    if draw:
        p.drawText(QRectF(0, y, width, box.height()), Qt.TextFlag.TextWordWrap, line)
    return y + box.height() + 18


def _grid_rows(count: int, y: float, height: float) -> list[tuple[int, float]]:
    """Where each line of the grid goes: (pages turned before it, top)."""
    rows, turned = [], 0
    for _ in range(count):
        if y + ROW_H > height:
            turned += 1
            y = 0
        rows.append((turned, y))
        y += ROW_H + ROW_GAP
    return rows


def _draw_grid(
    p: QPainter, project: Project, rows: list[tuple[int, float]], width: float,
    new_page: Callable[[], None],
) -> None:  # fmt: skip
    bars = bar_symbols(project, ascii_only=False)
    bar_w = width / BARS_PER_LINE
    numbers = [bar.number for bar in project.bars()]
    page = 0
    for (turned, y), i in zip(rows, range(0, len(bars), BARS_PER_LINE), strict=True):
        while page < turned:
            new_page()
            page += 1
        for col, cells in enumerate(bars[i : i + BARS_PER_LINE]):
            x = col * bar_w
            p.setPen(QPen(INK, 1.4))
            p.drawLine(int(x), int(y), int(x), int(y + ROW_H))
            beat_w = bar_w / max(len(cells), 1)
            if numbers[i + col]:
                p.setPen(FAINT)
                p.setFont(theme.app_font(10))
                p.drawText(
                    QRectF(x + 5, y, bar_w, 16), Qt.AlignmentFlag.AlignLeft, str(numbers[i + col])
                )
            for j, text in enumerate(cells):
                if not text:
                    continue
                # The name may run over the beats that hold no change after it.
                span = 1
                while j + span < len(cells) and not cells[j + span]:
                    span += 1
                room = beat_w * span - 8
                p.setPen(INK)
                size = 22.0
                p.setFont(theme.app_font(size, 600))
                measured = QFontMetricsF(p.font()).horizontalAdvance(text)
                if measured > room:
                    p.setFont(theme.app_font(max(size * room / measured, 9), 600))
                p.drawText(
                    QRectF(x + j * beat_w + 6, y + 16, room + 6, ROW_H - 18),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
        end = min(BARS_PER_LINE, len(bars) - i) * bar_w
        p.setPen(QPen(INK, 1.4))
        p.drawLine(int(end), int(y), int(end), int(y + ROW_H))


def _grid_count(project: Project) -> int:
    return -(-len(bar_symbols(project, ascii_only=False)) // BARS_PER_LINE)


def write_pdf(project: Project, path: Path) -> None:
    writer, p = _writer(path, project.audio.get("title"))
    width, height = writer.width(), writer.height()
    y = _title(p, project, width)
    _draw_grid(p, project, _grid_rows(_grid_count(project), y, height), width, writer.newPage)
    p.end()


@contextmanager
def _print_palette():
    """shortcut: the diagrams read their colours from the theme when they draw, so the sheet
    swaps the theme's colours for paper ones while it draws; a print palette passed to draw()
    would be cleaner if the diagrams ever draw from another thread."""
    saved = {name: getattr(theme, name) for name in PRINT_COLORS}
    keys = {name: getattr(diagrams, name) for name in PRINT_KEYS}
    try:
        for name, value in PRINT_COLORS.items():
            setattr(theme, name, value)
        for name, value in PRINT_KEYS.items():
            setattr(diagrams, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(theme, name, value)
        for name, value in keys.items():
            setattr(diagrams, name, value)


def card_height(mode: str) -> float:
    h = NAME_H + PLACE_H
    if mode != "piano":
        h += GUITAR_H + CAPTION_H
    if mode != "guitar":
        h += PIANO_H + CAPTION_H
    return h + 8


def sheet_layout(
    count: int, mode: str, first_top: float, page_h: float
) -> list[tuple[int, float, float]]:
    """Where each card goes, in sheet pixels: (page, x, y). A row that would not fit whole
    starts the next page, so no diagram is ever cut in two."""
    columns = COLUMNS[mode]
    h = card_height(mode)
    places, page, y = [], 0, first_top
    for i in range(count):
        col = i % columns
        if col == 0 and y > 0 and y + h > page_h:
            page, y = page + 1, 0.0
        places.append((page, col, y))
        if col == columns - 1:
            y += h + CARD_GAP
    return places


def _fit_font(text: str, size: float, weight: int, room: float):
    font = theme.app_font(size, weight)
    measured = QFontMetricsF(font).horizontalAdvance(text)
    if measured > room:
        font = theme.app_font(max(size * room / measured, 10), weight)
    return font


def _draw_card(
    p: QPainter, rect: QRectF, item, mode: str, positions: Positions,
    guitar: GuitarDiagram, piano: PianoDiagram,
) -> None:  # fmt: skip
    shown = item.shown
    p.setPen(QPen(QColor("#CCCCCC"), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect, 8, 8)
    inner = rect.adjusted(10, 6, -10, -6)
    p.setPen(INK)
    p.setFont(_fit_font(shown.shape.title, 20, 700, inner.width()))
    p.drawText(
        QRectF(inner.left(), inner.top(), inner.width(), NAME_H),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        shown.shape.title,
    )
    y = inner.top() + NAME_H
    p.setPen(QColor("#666666"))
    p.setFont(_fit_font(f"première fois : {item.place}", 11, 400, inner.width()))
    p.drawText(
        QRectF(inner.left(), y, inner.width(), PLACE_H),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
        f"première fois : {item.place}",
    )
    y += PLACE_H
    fingerings, voicing_list = positions_of(shown)

    def caption(text: str) -> None:
        p.setPen(QColor("#444444"))
        font = _fit_font(text, 11, 400, inner.width())
        if QFontMetricsF(font).horizontalAdvance(text) > inner.width():  # a narrow card
            text = text.split(" · ", 1)[-1]
            font = _fit_font(text, 11, 400, inner.width())
            text = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, inner.width())
        p.setFont(font)
        p.drawText(
            QRectF(inner.left(), y, inner.width(), CAPTION_H),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            text,
        )

    if mode != "piano":
        box = QRectF(inner.left(), y, inner.width(), GUITAR_H)
        if fingerings:
            i = positions.index(Positions.guitar_key(shown), len(fingerings))
            f = fingerings[i]
            guitar.fingering, guitar.chord, guitar.capo = f, shown.shape, shown.capo
            guitar.draw(p, box)
            text = f"Guitare · {f.kind}"
            if len(fingerings) > 1:
                text += f" · position {i + 1}/{len(fingerings)}"
        else:
            guitar.fingering, guitar.message = None, "Pas de position vérifiée à la guitare."
            guitar.draw(p, box)
            text = "Guitare"
        y += GUITAR_H
        caption(text)
        y += CAPTION_H
    if mode != "guitar":
        box = QRectF(inner.left(), y, inner.width(), PIANO_H)
        k = positions.index(Positions.piano_key(shown), len(voicing_list))
        v = voicing_list[k]
        piano.voicing, piano.chord = v, shown.sound
        piano.draw(p, box)
        y += PIANO_H
        text = f"Piano · son réel {shown.sound.title}" if shown.capo else f"Piano · {v.name}"
        caption(text)


def _foot(p: QPainter, project: Project, width: float, height: float, page: int, total: int):
    """The title and the page number, under the page's content (device pixels)."""
    p.setPen(FAINT)
    p.setFont(theme.app_font(11))
    title = project.audio.get("title") or "LocalChords"
    p.drawText(
        QRectF(0, height + 4, width, FOOTER_H - 4),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        QFontMetricsF(p.font()).elidedText(
            f"{title} · LocalChords", Qt.TextElideMode.ElideRight, width * 0.7
        ),
    )
    p.drawText(
        QRectF(0, height + 4, width, FOOTER_H - 4),
        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
        f"Page {page} / {total}",
    )


def write_chord_sheet(
    project: Project, path: Path, items: list, mode: str, include_grid: bool,
    positions: Positions,
) -> int:  # fmt: skip
    """Every chord of the song once, with its diagrams as chosen in the program, on A4 pages;
    the grid on pages of its own if asked. Returns the number of pages."""
    writer, p = _writer(path, project.audio.get("title"))
    width, height = writer.width(), writer.height() - FOOTER_H
    sheet_w, sheet_h = width / SHEET_SCALE, height / SHEET_SCALE

    # Laid out first, drawn second: the foot of each page knows how many there are.
    top = _title(p, project, width, draw=False)
    intro_h = 26
    places = sheet_layout(len(items), mode, (top + intro_h) / SHEET_SCALE, sheet_h)
    sheet_pages = (places[-1][0] + 1) if places else 1
    grid = _grid_rows(_grid_count(project), 40, height) if include_grid else []
    total = sheet_pages + ((grid[-1][0] + 1) if grid else 0)
    page = [1]

    def foot() -> None:
        _foot(p, project, width, height, page[0], total)

    def new_page() -> None:
        foot()
        writer.newPage()
        page[0] += 1

    _title(p, project, width)
    p.setPen(QColor("#444444"))
    p.setFont(theme.app_font(14, 600))
    count = len(items)
    intro = f"{count} accord{'s' if count > 1 else ''} différent{'s' if count > 1 else ''}"
    intro += ", dans l'ordre où ils arrivent" if count > 1 else ""
    if not items:
        intro = "Aucun accord dans ce morceau."
    p.drawText(QRectF(0, top, width, intro_h), int(Qt.AlignmentFlag.AlignLeft), intro)

    guitar, piano = GuitarDiagram(), PianoDiagram()
    piano.fit = True
    columns = COLUMNS[mode]
    card_w = (sheet_w - CARD_GAP * (columns - 1)) / columns
    h = card_height(mode)
    with _print_palette():
        for item, (on_page, col, y) in zip(items, places, strict=True):
            while page[0] - 1 < on_page:
                new_page()
            p.save()
            p.scale(SHEET_SCALE, SHEET_SCALE)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = QRectF(col * (card_w + CARD_GAP), y, card_w, h)
            _draw_card(p, rect, item, mode, positions, guitar, piano)
            p.restore()
    guitar.deleteLater()
    piano.deleteLater()

    if grid:
        new_page()
        p.setPen(INK)
        p.setFont(theme.app_font(20, 700))
        p.drawText(QRectF(0, 0, width, 34), int(Qt.AlignmentFlag.AlignLeft), "Grille")
        _draw_grid(p, project, grid, width, new_page)
    foot()
    p.end()
    return total


# The lyrics with the chords over them ------------------------------------------------------------

LYRIC_SIZES = {"small": 13, "medium": 16, "large": 20}  # sheet pixels: 16 prints at 12 pt
PORTRAIT_SHEET_W = 688  # the sheet's width in portrait, which COLUMNS were chosen for
LYRIC_COLORS = {
    "text": "#111111",
    "text_now": "#111111",
    "chord": "#1F4E8C",
    "approx": "#5A5A5A",
    "manual": "#0F766E",
    "now": "#1F4E8C",
    "section": "#C2410C",
}


def _paginate(blocks: list[dict], first_top: float, page_h: float) -> list[tuple[int, float]]:
    """(page, top) of each block, in sheet pixels. A block is never cut; one marked keep (a
    heading) goes to the next page with the block after it rather than stay alone at the foot."""
    places, page, y = [], 0, first_top
    for i, b in enumerate(blocks):
        y += b["gap"] if y > 0 else 0.0
        need = b["h"] + (
            blocks[i + 1]["gap"] + blocks[i + 1]["h"]
            if b.get("keep") and i + 1 < len(blocks)
            else 0.0
        )
        if y > 0 and y + min(need, page_h) > page_h:
            page, y = page + 1, 0.0
        places.append((page, y))
        y += b["h"]
    return places


def write_lyrics_sheet(
    project: Project,
    path: Path,
    options: dict,
    items: list,
    positions: Positions,
) -> int:
    """The lyrics with the chords over their words, as on screen, the diagrams before or after
    them. Vector text on A4 pages; nothing cut, a line too long wraps. Returns the page count."""
    from ..export import approximate, lyric_rows
    from ..lyrics import KINDS
    from .lyrics_view import Fonts, lay_out, paint, stack

    writer, p = _writer(path, project.audio.get("title"), bool(options.get("landscape")))
    width, height = writer.width(), writer.height() - FOOTER_H
    sheet_w, sheet_h = width / SHEET_SCALE, height / SHEET_SCALE
    blocks: list[dict] = []

    def text_block(text: str, font, color, gap: float, keep: bool = False) -> None:
        m = QFontMetricsF(font)
        box = m.boundingRect(QRectF(0, 0, sheet_w, 10_000), Qt.TextFlag.TextWordWrap, text)

        h = box.height()

        def draw(y, text=text, font=font, color=color, h=h):
            p.setFont(font)
            p.setPen(QColor(color))
            p.drawText(QRectF(0, y, sheet_w, h + 2), Qt.TextFlag.TextWordWrap, text)

        blocks.append({"h": h, "gap": gap, "draw": draw, "keep": keep})

    # The head: the title, what to know before playing, where the words come from.
    fields = dict(header(project))
    title = fields.pop("Titre", "") or "Sans titre"
    artist = fields.pop("Artiste", "")
    text_block(title, theme.app_font(26, 700), "#111111", 0)
    if artist:
        text_block(artist, theme.app_font(16, 600), "#3A3A3A", 2)
    if options.get("details", True) and fields:
        text_block(
            "   ·   ".join(f"{k} : {v}" for k, v in fields.items()),
            theme.app_font(12),
            "#3A3A3A",
            8,
        )
    lyr = project.lyrics
    src = lyr["source"]
    origin = f"Paroles : {KINDS.get(src.get('kind'), '')}"
    if src.get("name"):
        origin += f" ({src['name']})"
    rows = lyric_rows(project)
    if approximate(rows):
        origin += ". En italique gris : accord placé approximativement dans la ligne."
    text_block(origin, theme.app_font(11), "#5A5A5A", 6)

    # The diagrams, a row of cards per block.
    mode = options.get("diagrams", "guitar")
    card_blocks: list[dict] = []
    if mode != "none" and items:
        columns = max(COLUMNS[mode], int(COLUMNS[mode] * sheet_w / PORTRAIT_SHEET_W))
        card_w = (sheet_w - CARD_GAP * (columns - 1)) / columns
        h = card_height(mode)
        guitar, piano = GuitarDiagram(), PianoDiagram()
        piano.fit = True
        for i in range(0, len(items), columns):

            def draw(y, row=items[i : i + columns], h=h):
                with _print_palette():
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    for col, item in enumerate(row):
                        rect = QRectF(col * (card_w + CARD_GAP), y, card_w, h)
                        _draw_card(p, rect, item, mode, positions, guitar, piano)

            card_blocks.append({"h": h, "gap": CARD_GAP, "draw": draw})
        heading = {
            "h": 26,
            "gap": 18,
            "keep": True,
            "draw": lambda y: (
                p.setFont(theme.app_font(15, 700)),
                p.setPen(INK),
                p.drawText(QRectF(0, y, sheet_w, 26), "Accords"),
            ),
        }
        card_blocks.insert(0, heading)
    else:
        guitar = piano = None

    # The lyrics, a sung line (wrapped or not) per block, a section heading kept with its line.
    f = Fonts(LYRIC_SIZES.get(options.get("size"), 16))
    lines = lay_out(rows, sheet_w, f, True)
    lyric_blocks: list[dict] = []
    for r in sorted({ln.row for ln in lines}):
        mine = [ln for ln in lines if ln.row == r]
        gap = mine[0].gap
        mine[0].gap = 0.0
        h = stack(mine)

        def draw(y, mine=mine):
            p.save()
            p.translate(0, y)
            paint(p, mine, f, LYRIC_COLORS)
            p.restore()

        lyric_blocks.append({"h": h, "gap": gap, "draw": draw, "keep": mine[0].kind == "section"})
    if lyric_blocks:
        lyric_blocks[0]["gap"] = 20

    first = options.get("diagrams_first", True)
    blocks += (card_blocks + lyric_blocks) if first else (lyric_blocks + card_blocks)

    places = _paginate(blocks, 0.0, sheet_h)
    total = places[-1][0] + 1 if places else 1
    page = 0
    for b, (on_page, y) in zip(blocks, places, strict=True):
        while page < on_page:
            _foot(p, project, width, height, page + 1, total)
            writer.newPage()
            page += 1
        p.save()
        p.scale(SHEET_SCALE, SHEET_SCALE)
        b["draw"](y)
        p.restore()
    _foot(p, project, width, height, page + 1, total)
    p.end()
    if guitar is not None:
        guitar.deleteLater()
        piano.deleteLater()
    return total
