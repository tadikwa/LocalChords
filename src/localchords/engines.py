"""The engine seam: an engine turns a decoded recording into an analysis dict (docs/FORMAT.md).

To add an engine, write a function `run(wav_path, y, progress) -> dict` returning at least `beats`,
`segments` (each with start_time, end_time, chord, bass, candidates), `global_key` and `meter`, and
register it in ENGINES. Nothing outside this file knows what produced the analysis.

Both current engines are chordotomy's (MIT): the lv-chordia model on Beat This!'s grid, and a DSP
front end on librosa's. Four private names of chordotomy.beats are used so that Beat This!'s
downbeat head, which chordotomy throws away, comes out of the same pass of the net.
"""

from __future__ import annotations

import os
import sys
import tempfile
import wave
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import rhythm

Progress = Callable[[float, str], None]
ANALYSIS_SR = 22050
SILENCE_RMS = 1e-4
# Under this agreement between the one-tempo grid and Beat This!'s own beats, the song's tempo moves
# and the grid follows those beats instead. docs/BENCHMARKS.md has the measure behind this value.
FOLLOW_TEMPO_BELOW = 0.9


class AnalysisError(Exception):
    """An analysis that cannot finish; the message is written for the user."""


@dataclass(frozen=True)
class Engine:
    name: str
    label: str
    description: str
    run: Callable


# The share of an analysis each stage takes, measured on a 4-minute song (docs/BENCHMARKS.md).
STAGE_SHARE = {"activation": (0.05, 0.25), "beat_features": (0.25, 0.60), "recognize": (0.60, 0.97)}
STAGE_TEXT = {
    "activation": "Recherche des temps et des mesures…",
    "beat_features": "Lecture de la structure harmonique…",
    "recognize": "Reconnaissance des accords…",
}


def _configure_weights() -> None:
    """Use the Beat This! weights shipped with the program, when it is the packaged build."""
    from chordotomy import beats

    root = getattr(sys, "_MEIPASS", None)
    if root and (Path(root) / "models" / "beat_this-final0.ckpt").exists():
        beats.CACHE_DIR = Path(root) / "models"


def _both_heads(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Beat This!'s beat and downbeat logits per frame, from one pass of the net."""
    import torch
    from chordotomy import beats

    net = beats._tracker(beats.CHECKPOINT)
    spect = beats._log_mel(y)
    downbeat_chunks: list[np.ndarray] = []

    def run(chunk: np.ndarray) -> np.ndarray:
        out = net(torch.as_tensor(chunk, dtype=torch.float32)[None])
        downbeat_chunks.append(out["downbeat"][0].numpy())
        return out["beat"][0].numpy()

    with torch.inference_mode():
        beat = beats._chunked(spect, run)
    # _chunked walks the same chunks in the same order, so the second pass only replays them.
    replay = iter(downbeat_chunks)
    downbeat = beats._chunked(spect, lambda _chunk: next(replay))
    return beat, downbeat


class _Stages:
    """chordotomy's `cache` seam: every slow stage passes through run(), which reports progress
    and catches Beat This!'s output on its way through."""

    def __init__(self, progress: Progress):
        self.progress = progress
        self.beat_logits: np.ndarray | None = None
        self.downbeat_logits: np.ndarray | None = None
        self.followed_tempo = False
        self.fit_before: float | None = None

    def run(self, fn, *args, **kwargs):
        name = fn.__name__
        share = STAGE_SHARE.get(name)
        if share:
            self.progress(share[0], STAGE_TEXT[name])
        if name == "activation":
            result = self._activation(args[0])
        elif name == "beat_features":
            with self._tracker_that_follows_tempo():
                result = fn(*args, **kwargs)
        else:
            result = fn(*args, **kwargs)
        if share:
            self.progress(share[1], STAGE_TEXT[name])
        return result

    @contextmanager
    def _tracker_that_follows_tempo(self):
        """chordotomy's grid has one tempo per file, which drifts off a song whose tempo moves.

        Its tracker is librosa's, called once inside beat_features; this wraps that one call. All
        that reads the grid afterwards (chords, bass, harmony) stays as it is.
        """
        import librosa
        from chordotomy.beats import FPS
        from chordotomy.features import HOP, SR
        from scipy.special import expit

        original = librosa.beat.beat_track

        def track(**kwargs):
            tempo, frames = original(**kwargs)
            if self.beat_logits is None or len(frames) == 0:
                return tempo, frames  # the DSP engine: nothing better to follow
            peaks = rhythm.peak_times(expit(self.beat_logits), FPS)
            grid = librosa.frames_to_time(frames, sr=SR, hop_length=HOP)
            self.fit_before = rhythm.grid_fit(grid, peaks)
            if self.fit_before >= FOLLOW_TEMPO_BELOW or len(peaks) < 8:
                return tempo, frames
            self.followed_tempo = True
            followed = librosa.time_to_frames(peaks, sr=SR, hop_length=HOP)
            return np.array([60.0 / float(np.median(np.diff(peaks)))]), followed

        librosa.beat.beat_track = track
        try:
            yield
        finally:
            librosa.beat.beat_track = original

    def _activation(self, y: np.ndarray) -> np.ndarray:
        import librosa
        from chordotomy import beats
        from chordotomy.features import HOP, SR
        from scipy.special import expit

        self.beat_logits, self.downbeat_logits = _both_heads(y)
        if not beats.has_peaks(self.beat_logits):
            # Rubato or no pulse at all, yet there are notes: chords without a reliable grid beat
            # no chords, and the grid gets flagged as unsure.
            return librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        return beats.resample(expit(self.beat_logits), 1 + len(y) // HOP)


def _write_wav(path: Path, y: np.ndarray) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(ANALYSIS_SR)
        f.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def _rhythm_of(result: dict, stages: _Stages, y: np.ndarray) -> dict:
    """The meter and how much to trust the grid, from Beat This!'s activations."""
    from chordotomy import beats
    from scipy.special import expit

    if stages.downbeat_logits is None:
        stages.beat_logits, stages.downbeat_logits = _both_heads(y)
    grid = np.asarray(result["beats"], dtype=float)
    fps = beats.FPS
    down = expit(stages.downbeat_logits)
    frames = np.clip((grid * fps).round().astype(int), 0, len(down) - 1)
    # A beat's downbeat evidence is the peak within 70 ms, for grids that sit a frame or two off.
    window = int(0.07 * fps)
    evidence = np.array([down[max(0, f - window) : f + window + 1].max() for f in frames])
    changes = np.zeros(len(grid))
    for s in result["segments"]:
        if s["start_beat"] < len(changes):
            changes[s["start_beat"]] = 1
    peaks = rhythm.peak_times(expit(stages.beat_logits), fps)
    meter = rhythm.infer_meter(evidence, changes)
    meter["bar_lines"] = rhythm.place_bar_lines(evidence, changes, meter["beats_per_bar"])
    if meter["bar_lines"]:
        meter["first_downbeat"] = meter["bar_lines"][0] % meter["beats_per_bar"]
    return {
        "meter": meter,
        "tempo": rhythm.tempo(grid),
        "grid_fit": round(rhythm.grid_fit(grid, peaks), 3),
    }


def _chordotomy(engine: str, y: np.ndarray, progress: Progress) -> dict:
    from chordotomy import timeline
    from chordotomy.features import NoBeatsError
    from chordotomy.model import EngineError

    _configure_weights()
    stages = _Stages(progress)
    # chordotomy reads a path; the audio has already gone through our decoder and resampler, which
    # also handles what its own reader cannot (m4a, for one).
    fd, name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    wav = Path(name)
    try:
        _write_wav(wav, y)
        result = timeline.analyze(wav, engine=engine, cache=stages)
    except NoBeatsError as exc:
        raise AnalysisError("Aucun temps n'a été détecté dans ce morceau.") from exc
    except EngineError as exc:
        raise AnalysisError(f"Le moteur d'analyse n'a pas pu démarrer : {exc}") from exc
    finally:
        wav.unlink(missing_ok=True)
    progress(0.97, "Détection de la mesure et de la tonalité…")
    rhythm_info = _rhythm_of(result, stages, y)
    return {
        "engine": {
            "name": engine,
            "generator": result["generator"],
        },
        "followed_tempo": stages.followed_tempo,
        "beats": result["beats"],
        "segments": result["segments"],
        "global_key": result["global_key"],
        "key_regions": result["key_regions"],
        **rhythm_info,
    }


ENGINES = {
    "model": Engine(
        "model",
        "Précis (neuronal)",
        "lv-chordia et Beat This! : le meilleur résultat mesuré, tous types d'accords.",
        lambda y, progress: _chordotomy("model", y, progress),
    ),
    "dsp": Engine(
        "dsp",
        "Classique (chroma)",
        "Modèles d'accords sur chroma, sans réseau de neurones : un second avis.",
        lambda y, progress: _chordotomy("dsp", y, progress),
    ),
}
DEFAULT_ENGINE = "model"


def analyze(y: np.ndarray, engine: str, progress: Progress) -> dict:
    """Analyze mono float audio at ANALYSIS_SR."""
    if engine not in ENGINES:
        raise AnalysisError(f"Moteur inconnu : {engine}")
    if len(y) < ANALYSIS_SR or float(np.sqrt(np.mean(np.square(y)))) < SILENCE_RMS:
        raise AnalysisError("Ce morceau est silencieux ou trop court pour être analysé.")
    return ENGINES[engine].run(y, progress)
