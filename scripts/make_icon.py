"""Write assets/localchords.ico from the program's own drawing: PNG images in an ICO container."""

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from localchords.ui import theme
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

app = QApplication([])
images = []
for size in (16, 24, 32, 48, 64, 128, 256):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    theme.app_image(size).save(buffer, "PNG")
    images.append((size, bytes(buffer.data())))
header = struct.pack("<HHH", 0, 1, len(images))
offset = len(header) + 16 * len(images)
entries = b""
for size, data in images:
    side = 0 if size == 256 else size
    entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
out = Path("assets/localchords.ico")
out.parent.mkdir(exist_ok=True)
out.write_bytes(header + entries + b"".join(d for _, d in images))
print(out, out.stat().st_size)
