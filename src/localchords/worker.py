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
        from . import audio, engines, project

        file = Path(path)
        conn.send(("progress", 0.01, "Décodage de l'audio…"))
        y = audio.decode(file, engines.ANALYSIS_SR, channels=1)[:, 0]
        duration = round(len(y) / engines.ANALYSIS_SR, 3)
        conn.send(("waveform", project.encode_waveform(audio.peaks(y)), duration))
        conn.send(("progress", 0.03, "Chargement du moteur d'analyse…"))
        result = engines.analyze(y, engine, lambda f, text: conn.send(("progress", f, text)))
        conn.send(("progress", 1.0, "Terminé"))
        conn.send(("done", result))
    except (audio.AudioError, engines.AnalysisError) as exc:
        conn.send(("error", str(exc), ""))
    except MemoryError:
        conn.send(("error", "Mémoire insuffisante pour analyser ce morceau.", ""))
    except Exception as exc:  # noqa: BLE001 - the interface must hear of any failure
        conn.send(("error", f"L'analyse a échoué : {exc}", traceback.format_exc()))
    finally:
        conn.close()


@dataclass
class Job:
    process: mp.process.BaseProcess
    conn: object

    def poll(self) -> list[tuple]:
        """Messages that have arrived; ("error", …) is added if the process dies without a word."""
        messages = []
        try:
            while self.conn.poll():
                messages.append(self.conn.recv())
        except (EOFError, OSError):
            if not any(m[0] in ("done", "error") for m in messages):
                messages.append(("error", "Le processus d'analyse s'est arrêté brutalement.", ""))
        return messages

    def cancel(self) -> None:
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=3)
        self.conn.close()


def start(path: Path, engine: str) -> Job:
    ctx = mp.get_context("spawn")
    ours, theirs = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_job, args=(str(path), engine, theirs), daemon=True)
    process.start()
    theirs.close()
    return Job(process, ours)
