# PyInstaller: a portable folder, dist/LocalChords/LocalChords.exe, or with LOCALCHORDS_ONEFILE=1 a
# single LocalChords.exe. See scripts/build.ps1 and docs/PORTABLE.md.
#
# The nets run on ONNX Runtime (src/localchords/onnx_engine.py) from models/*.onnx, which
# scripts/export_onnx.py writes; torch, a third of the program's size, then stays out.
# LOCALCHORDS_TORCH_BUILD=1 builds the previous way, with torch and the original weights.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

onnx_models = sorted(Path("models").glob("*.onnx"))
torch_build = bool(os.environ.get("LOCALCHORDS_TORCH_BUILD"))
if not torch_build and len(onnx_models) != 6:
    raise SystemExit("Run scripts/export_onnx.py first: the ONNX models ship with the program.")

# The distributed program must carry an LGPL FFmpeg: scripts/build_av_lgpl.py, LICENCES-TIERS.md.
if not os.environ.get("LOCALCHORDS_ALLOW_GPL_AV"):
    import subprocess

    sys.path.insert(0, "scripts")
    import build_av_lgpl

    subprocess.run([sys.executable, "-c", build_av_lgpl.CHECK, *build_av_lgpl.NOT_LGPL], check=True)

datas = [
    ("assets/localchords.ico", "."),
    ("LICENSE", "."),
    ("LICENCES-TIERS.md", "."),
    ("licences/*.txt", "licences"),
]
# The engines read their own version, weights and tables at run time.
for package in ("chordotomy", "lv-chordia", "beat-this", "librosa", "soundfile", "numpy"):
    datas += copy_metadata(package)
datas += collect_data_files("lv_chordia")
datas += collect_data_files("librosa")
datas += collect_data_files("yt_dlp_ejs")
# The transcription engine (scripts/fetch_whisper.py), run as its own process from whisper/.
if not Path("vendor/whisper/whisper-cli.exe").exists():
    raise SystemExit("Run scripts/fetch_whisper.py first: the transcription engine ships with the program.")
datas += [(str(f), "whisper") for f in Path("vendor/whisper").iterdir()]

hidden = (
    collect_submodules("chordotomy")
    + collect_submodules("librosa")
    + collect_submodules("yt_dlp")
    + ["localchords.selftest", "scipy.special.cython_special"]
)

# Heavy things nothing here calls; each saves megabytes without touching what runs.
excludes = [
    "tkinter", "matplotlib", "IPython", "jupyter", "pytest", "torchvision", "tensorboard",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork", "PySide6.QtOpenGL",
    "PySide6.QtSvg", "PySide6.QtPdfWidgets", "PySide6.QtWebEngineCore",
    "mir_eval", "onnx", "onnxscript",
]

if torch_build:
    weights = Path.home() / ".cache" / "chordotomy" / "beat_this-final0.ckpt"
    if not weights.exists():
        raise SystemExit("Run `chordotomy fetch-weights` first: the weights ship with the program.")
    datas.append((str(weights), "models"))
    # The nets' weights sit outside the package; lv_chordia looks for them two levels above itself.
    nets = next(Path(sys.prefix).rglob("*.sdict")).parent
    datas += [(str(f), "cache_data") for f in nets.glob("*.sdict")]
    hidden += collect_submodules("lv_chordia") + collect_submodules("beat_this")
    hidden += ["sklearn.utils._typedefs"]
    excludes += ["onnxruntime"]
else:
    datas += [(str(f), "models") for f in onnx_models]
    # Only lv_chordia's HMM decoder runs (onnx_engine registers its packages empty); what imports
    # torch in it is never executed. sklearn and h5py are loaded by neither engine.
    hidden += ["lv_chordia.extractors.xhmm_ismir", "lv_chordia.complex_chord"]
    excludes += ["torch", "torchaudio", "beat_this", "sklearn", "h5py", "einops"]

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
# sounddevice loads libportaudio64bit.dll alone; the ASIO builds carry Steinberg's SDK.
portaudio = "_sounddevice_data/portaudio-binaries/"


def unused_portaudio(entry):
    name = entry[0].replace("\\", "/")
    return name.startswith(portaudio) and not name.endswith(("libportaudio64bit.dll", "README.md"))


a.binaries = [b for b in a.binaries if not unused_portaudio(b)]
a.datas = [d for d in a.datas if not unused_portaudio(d)]
a.datas = [
    d
    for d in a.datas
    if not d[0].startswith(("PySide6/translations", "torch/include", "torch/share"))
    and not d[0].endswith((".h", ".hpp", ".lib"))
    # librosa finds its own lazy imports through its .pyi files at run time.
    and not (d[0].endswith(".pyi") and not d[0].startswith("librosa"))
]

pyz = PYZ(a.pure)
if os.environ.get("LOCALCHORDS_ONEFILE"):
    # One file: everything above, unpacked to a temporary folder at each start. See docs/PORTABLE.md.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name="LocalChords",
        console=False,
        icon="assets/localchords.ico",
        upx=False,
    )
else:
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
