"""The two nets on ONNX Runtime instead of torch: same weights, same inputs, same outputs.

scripts/export_onnx.py writes the models from the torch checkpoints; the packaged program ships
those files and no torch, which is most of its size. docs/BENCHMARKS.md compares the two on Tiny
AAM and GuitarSet. `LOCALCHORDS_BACKEND=torch` brings the original back where torch is installed.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import sys
import types
from pathlib import Path

import numpy as np

CHORD_NETS = 5
SHIFT = 18  # ChordNet.inference: SHIFT_HIGH * SHIFT_STEP, the unshifted 252 of the 288 CQT bins


def models_dir() -> Path:
    root = getattr(sys, "_MEIPASS", None)
    if root:
        return Path(root) / "models"
    return Path(__file__).resolve().parents[2] / "models"


def available() -> bool:
    if os.environ.get("LOCALCHORDS_BACKEND") == "torch":
        return False
    folder = models_dir()
    files = [folder / "beat_this.onnx"] + [folder / f"chordnet_{i}.onnx" for i in range(CHORD_NETS)]
    return all(f.is_file() for f in files) and importlib.util.find_spec("onnxruntime") is not None


@functools.cache
def _session(name: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3  # its warnings about unused initializers mean nothing here
    return ort.InferenceSession(
        str(models_dir() / name), options, providers=["CPUExecutionProvider"]
    )


def log_mel(y: np.ndarray) -> np.ndarray:
    """chordotomy.beats._log_mel without torch: torch.stft(center, reflect, normalized), the same
    Slaney bank, log1p(1000 x). Computed in blocks so an hour of audio stays within memory."""
    import librosa
    from chordotomy import beats

    n_fft, hop = beats.N_FFT, beats.MEL_HOP
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)
    window /= np.float32(np.sqrt(n_fft))  # normalized=True: frame_length ** -0.5
    padded = np.pad(np.asarray(y, dtype=np.float32), n_fft // 2, mode="reflect")
    bank = librosa.filters.mel(
        sr=beats.SR, n_fft=n_fft, n_mels=beats.N_MELS, fmin=beats.FMIN, fmax=beats.FMAX,
        htk=False, norm=None,
    ).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft)[::hop]
    out = np.empty((len(frames), beats.N_MELS), dtype=np.float32)
    for start in range(0, len(frames), 4096):
        block = frames[start : start + 4096] * window
        magnitude = np.abs(np.fft.rfft(block, axis=1)).astype(np.float32)
        out[start : start + 4096] = magnitude @ bank.T
    return np.log1p(np.float32(beats.LOG_MULTIPLIER) * out)


def both_heads(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """engines._both_heads on ONNX Runtime: beat and downbeat logits per frame, one pass."""
    from chordotomy import beats

    session = _session("beat_this.onnx")
    spect = log_mel(y)
    downbeat_chunks: list[np.ndarray] = []

    def run(chunk: np.ndarray) -> np.ndarray:
        beat, downbeat = session.run(None, {"spect": chunk[None].astype(np.float32)})
        downbeat_chunks.append(downbeat[0])
        return beat[0]

    beat = beats._chunked(spect, run)
    replay = iter(downbeat_chunks)
    downbeat = beats._chunked(spect, lambda _chunk: next(replay))
    return beat, downbeat


class ChordSession:
    """What chordotomy.model._probabilities needs of a lv_chordia NetworkInterface."""

    def __init__(self, index: int):
        self.session = _session(f"chordnet_{index}.onnx")

    def inference(self, cqt: np.ndarray) -> tuple[np.ndarray, ...]:
        x = np.ascontiguousarray(cqt[:, SHIFT : SHIFT + 252], dtype=np.float32)[None]
        return tuple(self.session.run(None, {"cqt": x}))


@functools.cache
def chord_session(index: int) -> ChordSession:
    return ChordSession(index)


def _decoder_without_torch() -> None:
    """lv_chordia's package __init__ imports its nets, hence torch; its HMM decoder needs neither.
    The package and its extractors are registered empty, so only the decoder's own files load."""
    for name in ("lv_chordia", "lv_chordia.extractors"):
        if name in sys.modules:
            continue
        spec = importlib.util.find_spec(name)
        package = types.ModuleType(name)
        package.__path__ = list(spec.submodule_search_locations)
        package.__spec__ = spec
        sys.modules[name] = package


def install() -> None:
    """Route chordotomy's two nets through ONNX Runtime. Idempotent."""
    from chordotomy import model

    _decoder_without_torch()
    model._networks = lambda: tuple(chord_session(i) for i in range(CHORD_NETS))
