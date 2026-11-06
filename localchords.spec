# PyInstaller: a portable folder, dist/LocalChords/LocalChords.exe. See scripts/build.ps1.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

weights = Path.home() / ".cache" / "chordotomy" / "beat_this-final0.ckpt"
if not weights.exists():
    raise SystemExit("Run `chordotomy fetch-weights` first: the weights ship with the program.")

datas = [
    (str(weights), "models"),
    ("assets/localchords.ico", "."),
    ("LICENCES-TIERS.md", "."),
]
# The engines read their own version, weights and tables at run time.
for package in ("chordotomy", "lv-chordia", "beat-this", "librosa", "soundfile", "numpy"):
    datas += copy_metadata(package)
datas += collect_data_files("lv_chordia")
# The nets' weights sit outside the package; lv_chordia looks for them two levels above itself.
nets = next(Path(sys.prefix).rglob("*.sdict")).parent
datas += [(str(f), "cache_data") for f in nets.glob("*.sdict")]
datas += collect_data_files("librosa")

hidden = (
    collect_submodules("chordotomy")
    + collect_submodules("lv_chordia")
    + collect_submodules("beat_this")
    + collect_submodules("librosa")
    + ["localchords.selftest"]
    + ["sklearn.utils._typedefs", "scipy.special.cython_special"]
)

# Heavy things nothing here calls; each saves megabytes without touching what runs.
excludes = [
    "tkinter", "matplotlib", "IPython", "jupyter", "pytest", "torchvision", "tensorboard",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork", "PySide6.QtOpenGL",
    "PySide6.QtSvg", "PySide6.QtPdfWidgets", "PySide6.QtWebEngineCore",
    "mir_eval",
]

a = Analysis(
    ["src/localchords/__main__.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
)

# Qt translations, unused Qt modules' DLLs and C headers carry no behaviour.
drop = ("Qt6Quick", "Qt6Qml", "Qt6Network", "Qt6OpenGL", "opengl32sw", "Qt6Pdf", "Qt6VirtualKeyboard")
a.binaries = [b for b in a.binaries if not Path(b[0]).name.startswith(drop)]
a.datas = [
    d
    for d in a.datas
    if not d[0].startswith(("PySide6/translations", "torch/include", "torch/share"))
    and not d[0].endswith((".h", ".hpp", ".lib"))
    # librosa finds its own lazy imports through its .pyi files at run time.
    and not (d[0].endswith(".pyi") and not d[0].startswith("librosa"))
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalChords",
    console=False,
    icon="assets/localchords.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalChords", upx=False)
