"""Put the transcription engine in vendor/whisper: whisper.cpp's command-line build for Windows x64
(MIT, https://github.com/ggml-org/whisper.cpp), pinned and checked by SHA-256. The program
ships these 12 MB; the speech models are downloaded later, only
by those who want them (src/localchords/transcribe.py).

The engine links the Visual C++ runtime; its OpenMP part (vcomp140.dll) is not in the Python
build, so the four DLLs are copied from this machine's System32 (Microsoft allows shipping them).
"""

from __future__ import annotations

import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ENGINE = (
    "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip",
    "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb",
)
KEEP = ("whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll")  # and ggml-cpu-*.dll
RUNTIME = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "vcomp140.dll")
OUT = Path("vendor/whisper")


def fetch(url: str, sha: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        raise SystemExit(f"{url}: SHA-256 {got}, {sha} attendu")
    return data


def main() -> None:
    if (OUT / "whisper-cli.exe").exists() and (OUT / "vcomp140.dll").exists():
        print(f"{OUT} déjà prêt")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(fetch(*ENGINE))) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if name in KEEP or (name.startswith("ggml-cpu-") and name.endswith(".dll")):
                (OUT / name).write_bytes(z.read(info))
    system = Path(r"C:\Windows\System32")
    for name in RUNTIME:
        if not (system / name).exists():
            raise SystemExit(f"{name} manque : installez le Visual C++ Redistributable x64.")
        shutil.copy2(system / name, OUT / name)
    print(f"{OUT} : {sum(f.stat().st_size for f in OUT.iterdir()) / 2**20:.1f} Mo")


if __name__ == "__main__":
    sys.exit(main())
