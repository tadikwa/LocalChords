"""PyAV built against an LGPL-only FFmpeg, for the distributed program.

PyAV's own Windows wheels link avcodec to libx264 and libx265 (GPL), whatever avcodec_license()
says. This rebuilds the same PyAV release against BtbN's LGPL shared build of the same FFmpeg
branch: no GPL library, every decoder LocalChords uses. Both downloads are pinned by SHA-256.

    python scripts/build_av_lgpl.py            -> build/av-lgpl/wheel/av-*.whl
    python scripts/build_av_lgpl.py --sources <zip>   -> the sources to publish with the program
Needs Python 3.12, uv and the MSVC build tools (found by setuptools).
"""

import hashlib
import json
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PYAV = "19.0.2"
FFMPEG_TAG = "autobuild-2026-11-07-12-47"
FFMPEG_NAME = "ffmpeg-n9.0.2-48-gd4070a14ce-win64-lgpl-shared-9.0"
FFMPEG_SHA256 = "0cf5bd578e201901f4afff4fee53f4a8e08b899de7e4bb91c357d43e81ba3d54"
FFMPEG_URL = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{FFMPEG_TAG}/{FFMPEG_NAME}.zip"
# FFmpeg n9.0.2 configure: EXTERNAL_LIBRARY_GPL_LIST, _GPLV3_LIST, _NONFREE_LIST and the non-free hwaccels.
NOT_LGPL = ("gpl", "nonfree", "avisynth", "frei0r", "libcdio", "libdavs2", "libdvdnav", "libdvdread",
            "librubberband", "libvidstab", "libx264", "libx265", "libxavs", "libxavs2", "libxvid",
            "libsmbclient", "decklink", "libfdk_aac", "libmpeghdec", "cuda_nvcc", "cuda_sdk")
CHECK = """
import av._core as c, sys
meta = c.library_meta["libavcodec"]
on = {x[len("--enable-"):].replace("-", "_") for x in meta["configuration"].split()
      if x.startswith("--enable-")}
bad = sorted(on & set(sys.argv[1:]))
assert meta["license"].startswith("LGPL"), meta["license"]
assert not bad, bad
print(c.ffmpeg_version_info, meta["license"])
"""

# The commits behind FFMPEG_NAME: FFmpeg itself, and BtbN's scripts (which pin every external library).
FFMPEG_COMMIT = "d4070a14cecc7e29eb278f9b6036c2284255f70d"
BUILDS_COMMIT = "c63bb308a1de656b425c132a8102f8fd5389afc5"
SOURCES_README = f"""Sources tierces LGPL de LocalChords

- ffmpeg-{FFMPEG_COMMIT[:10]}.tar.gz : FFmpeg au commit {FFMPEG_COMMIT}, source des DLL avcodec,
  avformat, avutil, avfilter, avdevice, swresample et swscale livrees avec le programme.
- FFmpeg-Builds-{FFMPEG_TAG}.tar.gz : scripts de BtbN/FFmpeg-Builds au commit {BUILDS_COMMIT}, qui ont
  produit {FFMPEG_NAME} ; chaque script de scripts.d donne le depot et le commit d'une bibliotheque externe.
- av-{PYAV}.tar.gz : source de PyAV {PYAV} (PyPI), recompilee contre cette construction par
  scripts/build_av_lgpl.py (https://github.com/tadikwa/LocalChords).

Qt 6 (PySide6) : https://download.qt.io/official_releases/qt/ et https://code.qt.io/cgit/pyside/pyside-setup.git/
Licences : LGPL-3.0-or-later pour FFmpeg (textes dans licences/ du programme), BSD-3-Clause pour PyAV.
"""

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "av-lgpl"


def fetch(url: str, target: Path, sha256: str) -> Path:
    if not target.exists():
        print("téléchargement", url, flush=True)
        urllib.request.urlretrieve(url, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != sha256:
        target.unlink()
        raise SystemExit(f"{target.name} : empreinte {digest}, attendue {sha256}")
    return target


def run(*args, **kw):
    print(">", " ".join(map(str, args)), flush=True)
    subprocess.run([str(a) for a in args], check=True, **kw)


def sources(target: Path) -> None:
    """The Corresponding Source of the shipped FFmpeg, for each release (LGPL-3.0 section 4, GPL-3.0 6)."""
    import zipfile as zf

    archives = {
        f"ffmpeg-{FFMPEG_COMMIT[:10]}.tar.gz": f"https://github.com/FFmpeg/FFmpeg/archive/{FFMPEG_COMMIT}.tar.gz",
        f"FFmpeg-Builds-{FFMPEG_TAG}.tar.gz":
            f"https://github.com/BtbN/FFmpeg-Builds/archive/{BUILDS_COMMIT}.tar.gz",
    }
    folder = WORK / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in archives.items():
        if not (folder / name).exists():  # named by commit: no digest to pin, GitHub builds the archive
            print("téléchargement", url, flush=True)
            urllib.request.urlretrieve(url, folder / name)
    sdist = WORK / f"av-{PYAV}.tar.gz"
    if not sdist.exists():
        raise SystemExit("Construire la roue d'abord : la source de PyAV vient de cette étape.")
    with zf.ZipFile(target, "w", zf.ZIP_STORED) as z:
        z.writestr("LISEZMOI.txt", SOURCES_README.replace(chr(10), chr(13) + chr(10)))
        for f in [folder / n for n in archives] + [sdist]:
            z.write(f, f.name)
    print("sources :", target)


def main() -> None:
    if sys.argv[1:2] == ["--sources"]:
        return sources(Path(sys.argv[2]))
    WORK.mkdir(parents=True, exist_ok=True)
    archive = fetch(FFMPEG_URL, WORK / f"{FFMPEG_NAME}.zip", FFMPEG_SHA256)
    ffmpeg = WORK / FFMPEG_NAME
    if not ffmpeg.exists():
        with zipfile.ZipFile(archive) as z:
            z.extractall(WORK)

    info = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/av/{PYAV}/json"))
    sdist = next(u for u in info["urls"] if u["packagetype"] == "sdist")
    source = fetch(sdist["url"], WORK / sdist["filename"], sdist["digests"]["sha256"])
    src = WORK / f"av-{PYAV}"
    if not src.exists():
        with tarfile.open(source) as t:
            t.extractall(WORK, filter="data")

    venv = WORK / "venv"
    python = venv / "Scripts" / "python.exe"
    if not python.exists():
        run("uv", "venv", "--python", "3.12", venv)
    run("uv", "pip", "install", "--python", python, "setuptools>=78", "cython>=3.3,<4", "wheel",
        "delvewheel")
    raw = WORK / "raw"
    # setuptools does not always find MSVC by itself: build inside vcvars64, as a developer prompt would.
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    vs = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property",
                         "installationPath"], capture_output=True, text=True, check=True).stdout.strip()
    vcvars = Path(vs) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    command = (f'call "{vcvars}" && set DISTUTILS_USE_SDK=1 && "{python}" setup.py bdist_wheel '
               f'"--ffmpeg-dir={ffmpeg}" --dist-dir "{raw}"')
    print(">", command, flush=True)
    subprocess.run(f'cmd /d /s /c "{command}"', check=True, cwd=src)
    wheel = max(raw.glob(f"av-{PYAV}-*.whl"), key=lambda p: p.stat().st_mtime)
    out = WORK / "wheel"
    run(python, "-m", "delvewheel", "repair", "--add-path", ffmpeg / "bin", "-w", out, wheel)

    # The proof, from the FFmpeg inside the wheel: its licence and no library outside the LGPL.
    built = max(out.glob(f"av-{PYAV}-*.whl"), key=lambda p: p.stat().st_mtime)
    run("uv", "pip", "install", "--python", python, "--reinstall", "--no-deps", built)
    run(python, "-c", CHECK, *NOT_LGPL, cwd=WORK)
    print("roue LGPL :", built)


if __name__ == "__main__":
    sys.exit(main())
