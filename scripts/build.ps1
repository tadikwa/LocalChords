# Build dist\LocalChords\LocalChords.exe from a checkout. Needs uv (https://docs.astral.sh/uv/).
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true   # a failing tool stops the build
if (-not (Test-Path .venv)) { uv venv --python 3.12 .venv }
uv pip install --python .venv\Scripts\python.exe -r requirements-lock.txt
uv pip install --python .venv\Scripts\python.exe -e . --no-deps
# PyAV's own wheel carries a GPL FFmpeg (libx264, libx265): rebuild it against an LGPL one (MSVC needed).
.venv\Scripts\python.exe scripts\build_av_lgpl.py
uv pip install --python .venv\Scripts\python.exe --reinstall --no-deps build\av-lgpl\wheel\av-19.0.2-cp312-abi3-win_amd64.whl
.venv\Scripts\python.exe -c "from chordotomy import beats; beats.fetch()"   # weights ship with the program
.venv\Scripts\python.exe scripts\export_onnx.py   # models\*.onnx, which the program runs without torch
.venv\Scripts\python.exe scripts\make_icon.py
.venv\Scripts\python.exe -m PyInstaller localchords.spec --noconfirm
# The single LocalChords.exe (docs/PORTABLE.md): the same build, packed into one file.
$env:LOCALCHORDS_ONEFILE = "1"
.venv\Scripts\python.exe -m PyInstaller localchords.spec --noconfirm --distpath dist\onefile --workpath build\onefile
Remove-Item Env:LOCALCHORDS_ONEFILE
# The proof: the whole scenario inside the built program. Exit code 0 and report.json say it passed.
Write-Host "Auto-test : dist\LocalChords\LocalChords.exe --self-test <audio> <dossier>"
