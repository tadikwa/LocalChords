"""The chart as a PDF: Qt's own writer, nothing to install."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from ..export import bar_symbols, header
from ..project import Project
from . import theme

BARS_PER_LINE = 4
INK = QColor("#111111")
FAINT = QColor("#9A9A9A")


def write_pdf(project: Project, path: Path) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(14, 14, 14, 14),
        )
    )
    writer.setResolution(144)
    writer.setTitle(project.audio.get("title") or "LocalChords")
    writer.setCreator("LocalChords")
    p = QPainter(writer)
    if not p.isActive():
        raise OSError(f"Impossible d'écrire dans {path}")
    width = writer.width()
    height = writer.height()
    bars = bar_symbols(project, ascii_only=False)
    fields = dict(header(project))
    title = fields.pop("Titre", "")

    p.setPen(INK)
    p.setFont(theme.app_font(30, 700))
    metrics = QFontMetricsF(p.font())
    p.drawText(
        QRectF(0, 0, width, metrics.height()),
        Qt.AlignmentFlag.AlignLeft,
        metrics.elidedText(title, Qt.TextElideMode.ElideRight, width),
    )
    y = metrics.height() + 4
    p.setFont(theme.app_font(14))
    metrics = QFontMetricsF(p.font())
    line = "   ·   ".join(f"{k} : {v}" for k, v in fields.items())
    p.drawText(QRectF(0, y, width, metrics.height() * 2), Qt.TextFlag.TextWordWrap, line)
    y += metrics.height() * (2 if metrics.horizontalAdvance(line) > width else 1) + 18

    row_h = 62
    bar_w = width / BARS_PER_LINE
    number = 0
    for i in range(0, len(bars), BARS_PER_LINE):
        if y + row_h > height:
            writer.newPage()
            y = 0
        for col, cells in enumerate(bars[i : i + BARS_PER_LINE]):
            x = col * bar_w
            p.setPen(QPen(INK, 1.4))
            p.drawLine(int(x), int(y), int(x), int(y + row_h))
            beat_w = bar_w / max(len(cells), 1)
            if any(cells) or cells:
                number += 1
            p.setPen(FAINT)
            p.setFont(theme.app_font(10))
            p.drawText(QRectF(x + 5, y, bar_w, 16), Qt.AlignmentFlag.AlignLeft, str(number))
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
                    QRectF(x + j * beat_w + 6, y + 16, room + 6, row_h - 18),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
        end = min(BARS_PER_LINE, len(bars) - i) * bar_w
        p.setPen(QPen(INK, 1.4))
        p.drawLine(int(end), int(y), int(end), int(y + row_h))
        y += row_h + 10
    p.end()
