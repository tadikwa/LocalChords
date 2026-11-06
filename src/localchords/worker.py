"""An analysis in its own process, so that cancelling kills it outright and torch loads apart from
the interface. Top-level imports stay light: the interface imports this module."""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path


def _job(path: str, engine: str, conn) -> None:
    # The windowed program has no console: libraries that write to one must not crash on it.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
    try:
        from . import audio, library

        # librosa's beat tracker is compiled at first use. Kept for later runs in development; the
        # packaged program writes nothing here (measured) and compiles it on every analysis.
        os.environ.setdefault("NUMBA_CACHE_DIR", str(library.data_dir() / "cache"))
        from . import engines, project

        file = Path(path)
        conn.send(("progress", 0.01, "Décodage de l'audio…"))
        y = audio.decode(file, engines.ANALYSIS_SR, channels=1)[:, 0]
        duration = round(len(y) / engines.ANALYSIS_SR, 3)
        conn.send(("waveform", project.encode_waveform(audio.peaks(y)), duration))
        conn.send(("progress", 0.03, "Chargement du moteur d'analyse…"))
        result = engines.analyze(y, engine, lambda f, text: conn.send(("progress", f, text)))
        conn.send(("progress", 1.0, "Terminé"))
        conn.send(("done", result))
    except MemoryError:
        conn.send(("error", "Mémoire insuffisante pour analyser ce morceau.", ""))
    except Exception as exc:  # noqa: BLE001 - the interface must hear of any failure
        # Failures written for the user pass as they are; anything else also goes to the log.
        expected = type(exc).__name__ in ("AudioError", "AnalysisError")
        text = str(exc) if expected else f"L'analyse a échoué : {exc}"
        conn.send(("error", text, "" if expected else traceback.format_exc()))
    finally:
        conn.close()


FINAL = ("done", "downloaded", "error")


@dataclass
class Job:
    process: mp.process.BaseProcess
    conn: object
    ended: bool = False
    answered: bool = False

    def poll(self) -> list[tuple]:
        """Messages that have arrived; ("error", …) is added if the process dies without a word."""
        messages = []
        try:
            while self.conn.poll():
                messages.append(self.conn.recv())
        except (EOFError, OSError):
            self.ended = True
        self.answered = self.answered or any(m[0] in FINAL for m in messages)
        if self.ended and not self.answered:
            self.answered = True
            messages.append(("error", "Le processus s'est arrêté brutalement.", ""))
        return messages

    def cancel(self) -> None:
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=3)
        self.conn.close()


def _download_job(url: str, folder: str, conn) -> None:
    """Fetch one recording's audio, as it is on the site: decoding needs no conversion."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
    try:
        import yt_dlp

        def hook(status):
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if status.get("status") == "downloading" and total:
                done = status.get("downloaded_bytes", 0) / total
                conn.send(("progress", done, "Téléchargement de l'audio…"))

        options = {
            # AAC or Opus first: some sites' "best" is a surround codec the decoder doesn't know.
            "format": "bestaudio[acodec^=mp4a]/bestaudio[acodec=opus]/bestaudio/best",
            "outtmpl": str(Path(folder) / "%(title).100B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "playlist_items": "1",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "windowsfilenames": True,
            "progress_hooks": [hook],
            "js_runtimes": {"deno": {}, "node": {}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("entries"):
                info = info["entries"][0]
            path = ydl.prepare_filename(info)
        conn.send(("downloaded", path, info.get("webpage_url") or url))
    except Exception as exc:  # noqa: BLE001 - whatever the site says goes to the user as it is
        text = str(exc).replace("ERROR: ", "")
        conn.send(("error", f"Le téléchargement a échoué : {text}", ""))
    finally:
        conn.close()


def _start(target, *args) -> Job:
    ctx = mp.get_context("spawn")
    ours, theirs = ctx.Pipe(duplex=False)
    process = ctx.Process(target=target, args=(*args, theirs), daemon=True)
    process.start()
    theirs.close()
    return Job(process, ours)


def start(path: Path, engine: str) -> Job:
    return _start(_job, str(path), engine)


def start_download(url: str, folder: Path) -> Job:
    return _start(_download_job, url, str(folder))
