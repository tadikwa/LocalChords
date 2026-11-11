"""Transcribing the words sung, on this computer: whisper.cpp (MIT) run as its own process.

The engine ships with the program (scripts/fetch_whisper.py, 12 MB); a speech model is downloaded
only when asked, from Hugging Face, checked by SHA-256, and kept in the data folder (portable mode
included), never in the folder a one-file build unpacks itself into. Nothing is sent anywhere: the
audio is decoded here, written to a temporary WAV and read by the engine.

docs/BENCHMARKS.md gives the measurements behind the choice of models and settings.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import wave
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import audio, library
from .lyrics_online import USER_AGENT

# Pinned to a revision: the sizes and hashes below are this one's, a later upload would not match.
HF = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/"
)
MODELS = [
    {
        "id": "small-q5_1",
        "file": "ggml-small-q5_1.bin",
        "size": 190_085_487,
        "sha256": "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
        "label": "Standard (small, 190 Mo)",
        "note": "Le meilleur compromis : rapide, correct en français et en anglais.",
    },
    {
        "id": "large-v3-turbo-q5_0",
        "file": "ggml-large-v3-turbo-q5_0.bin",
        "size": 574_041_195,
        "sha256": "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
        "label": "Précis (large-v3-turbo, 574 Mo)",
        "note": "Moins d'erreurs sur le chant, deux à trois fois plus lent.",
    },
]
DEFAULT_MODEL = "small-q5_1"
LANGUAGES = {
    "auto": "Détection automatique",
    "fr": "Français",
    "en": "Anglais",
    "es": "Espagnol",
    "de": "Allemand",
    "it": "Italien",
    "pt": "Portugais",
}
RATE = 16_000
SPACE_MARGIN_MB = 200
# Phrases the models invent over music or silence, learnt from subtitles.
INVENTED = re.compile(
    r"sous-titr|amara\.org|merci d'avoir regard|abonnez-vous|thanks? (you )?for watching"
    r"|subscribe|transcribed by|www\.|\.com\b",
    re.IGNORECASE,
)


class TranscribeError(Exception):
    pass


def model_info(model_id: str) -> dict:
    return next(m for m in MODELS if m["id"] == model_id)


def engine_dir() -> Path:
    """whisper/ beside the program's modules in a build, vendor/whisper in a checkout."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "whisper"
    return Path(__file__).resolve().parents[2] / "vendor" / "whisper"


def engine_ready() -> bool:
    return (engine_dir() / "whisper-cli.exe").is_file()


def models_dir() -> Path:
    return library.data_dir() / "models" / "whisper"


def model_path(model_id: str) -> Path:
    return models_dir() / model_info(model_id)["file"]


def installed(model_id: str) -> bool:
    """The size is checked here; the content was checked by SHA-256 when it was downloaded."""
    path = model_path(model_id)
    return path.is_file() and path.stat().st_size == model_info(model_id)["size"]


def installed_models() -> list[str]:
    return [m["id"] for m in MODELS if installed(m["id"])]


def delete_model(model_id: str) -> None:
    """Only the model goes; transcriptions are kept in the projects."""
    for path in (model_path(model_id), model_path(model_id).with_suffix(".part")):
        path.unlink(missing_ok=True)


@dataclass
class Task:
    """Work done in a thread, read by the window's timer: progress in 0..1, then result or error."""

    status: str = ""
    progress: float = 0.0
    result: object = None
    error: str | None = None
    done: bool = False
    _cancel: threading.Event = field(default_factory=threading.Event)
    _process: subprocess.Popen | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        if self._process and self._process.poll() is None:
            with contextlib.suppress(OSError):
                self._process.kill()


def run(work: Callable[[Task], object]) -> Task:
    task = Task()

    def body():
        try:
            task.result = work(task)
        except TranscribeError as exc:
            task.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - the window shows it rather than crash
            task.error = f"Erreur inattendue : {exc}"
        finally:
            task.done = True

    threading.Thread(target=body, daemon=True).start()
    return task


# Downloading a model --------------------------------------------------------------------------


def download(model_id: str, task: Task, opener=urllib.request.urlopen) -> Path:
    info = model_info(model_id)
    return fetch(HF + info["file"], models_dir() / info["file"], info, task, opener)


def fetch(url: str, target: Path, info: dict, task: Task, opener=urllib.request.urlopen) -> Path:
    """Into a .part file, hashed as it comes, renamed only once its size and SHA-256 match `info`.
    Also downloads the separation models (stems.py)."""
    folder = target.parent
    folder.mkdir(parents=True, exist_ok=True)
    free = library.free_mb(folder)
    if free and free < info["size"] / 2**20 + SPACE_MARGIN_MB:
        raise TranscribeError(
            f"Pas assez de place dans {folder} : {free} Mo libres, "
            f"{info['size'] // 2**20 + SPACE_MARGIN_MB} Mo nécessaires."
        )
    part = target.with_suffix(".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    got = 0
    try:
        with opener(request, timeout=30) as response, part.open("wb") as f:
            while chunk := response.read(1 << 20):
                if task.cancelled:
                    raise TranscribeError("Téléchargement annulé.")
                f.write(chunk)
                digest.update(chunk)
                got += len(chunk)
                task.progress = got / info["size"]
                task.status = f"{got / 2**20:.0f} / {info['size'] / 2**20:.0f} Mo"
    except TranscribeError:
        part.unlink(missing_ok=True)
        raise
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise TranscribeError(f"Le téléchargement a échoué : {exc}") from exc
    if got != info["size"] or digest.hexdigest() != info["sha256"]:
        part.unlink(missing_ok=True)
        raise TranscribeError(
            "Le fichier reçu ne correspond pas au modèle attendu (SHA-256) : "
            "il a été supprimé. Réessayez."
        )
    os.replace(part, target)
    return target


# Transcribing ---------------------------------------------------------------------------------


def threads() -> int:
    """Leave two cores to the player and the window."""
    return max(1, min(8, (os.cpu_count() or 4) - 2))


def command(model: Path, wav: Path, out: Path, language: str) -> list[str]:
    folder = engine_dir()
    return [
        str(folder / "whisper-cli.exe"),
        "-m",
        str(model),
        "-f",
        str(wav),
        "-l",
        language,
        # -mc 0: no previous text as context, which is what makes the models loop on songs.
        # No voice detector: Silero, made for speech, finds no speech in most sung songs.
        "-t",
        str(threads()),
        "-ojf",
        "-of",
        str(out),
        "-pp",
        "-np",
        "-sns",
        "-mc",
        "0",
    ]


def transcribe(path: Path, model_id: str, language: str, task: Task) -> dict:
    """{lines, language}: the lines with their times and their words' times, a draft to check."""
    if not engine_ready():
        raise TranscribeError("Le moteur de transcription manque dans cette installation.")
    if not installed(model_id):
        raise TranscribeError("Téléchargez d'abord un modèle de transcription.")
    task.status = "Lecture de l'audio…"
    try:
        y = audio.decode(path, RATE, 1, should_cancel=lambda: task.cancelled)[:, 0]
    except audio.AudioError as exc:
        raise TranscribeError(str(exc)) from exc
    if task.cancelled:
        raise TranscribeError("Transcription annulée.")
    # whisper-cli opens files with ANSI names: a Cyrillic or CJK folder would not open. So it runs
    # in the models folder (the working directory is passed as Unicode) and gets ASCII names.
    home = models_dir()
    with tempfile.TemporaryDirectory(prefix="tmp-", dir=home) as tmp:
        rel = Path(Path(tmp).name)
        wav, out = Path(tmp) / "audio.wav", Path(tmp) / "result"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
        task.status = "Transcription…"
        cmd = command(
            Path(model_info(model_id)["file"]), rel / "audio.wav", rel / "result", language
        )
        _run_engine(cmd, task, home)
        raw = (out.with_suffix(".json")).read_bytes()
    data = json.loads(raw.decode("utf-8", "surrogateescape"))
    lines = lines_from(data, y)
    found = (data.get("result") or {}).get("language") or language
    return {"lines": lines, "language": found}


def _run_engine(cmd: list[str], task: Task, cwd: Path | None = None) -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    tail: list[str] = []
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            cwd=cwd,
        )
    except OSError as exc:
        raise TranscribeError(f"Le moteur de transcription n'a pas démarré : {exc}") from exc
    task._process = process
    if task.cancelled:  # cancelled while starting: cancel() saw no process yet
        process.kill()
    # stderr is read as it comes: a full pipe would stop the engine.
    for raw in iter(process.stderr.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        m = re.search(r"progress\s*=\s*(\d+)%", line)
        if m:
            task.progress = int(m.group(1)) / 100
        elif line:
            tail = (tail + [line])[-8:]
    process.wait()
    if task.cancelled:
        raise TranscribeError("Transcription annulée.")
    if process.returncode:
        raise TranscribeError(
            "La transcription a échoué : " + (" ".join(tail[-3:]) or f"code {process.returncode}")
        )


def lines_from(data: dict, y: np.ndarray) -> list[dict]:
    """Lines from the engine's segments, with the start of each word; what the models invent over
    music (loops, subtitle credits, words in silence) left out."""
    out: list[dict] = []
    for s in data.get("transcription", []):
        tokens = [t for t in s.get("tokens", []) if not t["text"].startswith("[_")]
        text, words = b"", []
        for t in tokens:
            piece = t["text"].encode("utf-8", "surrogateescape")
            if piece.startswith(b" ") or not text:
                start = t["offsets"]["from"] / 1000
                char = len(text.lstrip().decode("utf-8", "ignore"))
                char += 1 if piece.startswith(b" ") and text.strip() else 0
                words.append([char, round(start, 3)])
            text += piece
        line = text.decode("utf-8", "replace").strip()
        start = s["offsets"]["from"] / 1000
        end = s["offsets"]["to"] / 1000
        if not line or not plausible(line, start, end, y):
            continue
        words = [[c, t] for c, t in words if c < len(line)]
        if out and out[-1]["text"].lower() == line.lower() and _repeats(out, line) >= 3:
            continue  # a loop: the same line again and again
        out.append({"text": line, "start": round(start, 3), "end": round(end, 3), "words": words})
    return out


def _repeats(lines: list[dict], text: str) -> int:
    n = 0
    for x in reversed(lines):
        if x["text"].lower() != text.lower():
            break
        n += 1
    return n


def plausible(text: str, start: float, end: float, y: np.ndarray) -> bool:
    if INVENTED.search(text):
        return False
    data = text.encode("utf-8")
    if len(data) > 40 and len(data) / len(zlib.compress(data)) > 2.4:
        return False  # words looping inside the line (the threshold Whisper itself uses)
    a, b = int(start * RATE), max(int(end * RATE), int(start * RATE) + 1)
    piece = y[a:b]
    return piece.size == 0 or float(np.sqrt(np.mean(piece**2))) > 0.003  # not words in silence
