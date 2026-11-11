"""Separating a song's instruments with Demucs v4 (Meta, MIT), run by onnxruntime.

The networks were exported without their STFT (scripts/export_demucs_onnx.py): this module does the
STFT, the segmenting and the cross-fades exactly as demucs.apply.apply_model does (shifts=0), so the
result matches PyTorch's to rounding (tests/test_separation.py, docs/SEPARATION.md). No torch in the
program: onnxruntime is already there for the chord models.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

NFFT = 4096
HOP = NFFT // 4
OVERLAP = 0.25


class SeparationError(Exception):
    """Written for the user."""


class Cancelled(Exception):
    pass


def _window() -> np.ndarray:
    return np.hanning(NFFT + 1)[:-1].astype(np.float32)  # periodic, as torch.hann_window


def spec(x: np.ndarray) -> np.ndarray:
    """HTDemucs._spec then _magnitude: (C, L) → (2C, 2048, ceil(L/HOP)), real and imaginary parts
    as channels. torch.stft's centring plus the model's own padding put the frames it keeps at
    k·HOP of the signal padded by 3·HOP/2 on the left."""
    channels, length = x.shape
    frames = -(-length // HOP)
    pad = HOP // 2 * 3
    padded = np.pad(x, ((0, 0), (pad, pad + frames * HOP - length)), mode="reflect")
    idx = np.arange(frames)[:, None] * HOP + np.arange(NFFT)[None, :]
    z = np.fft.rfft(padded[:, idx] * _window(), axis=-1)[..., :-1] / np.sqrt(NFFT)
    z = z.transpose(0, 2, 1)  # (C, F, T)
    return (
        np.stack((z.real, z.imag), axis=1)
        .reshape(channels * 2, NFFT // 2, frames)
        .astype(np.float32)
    )


def ispec(m: np.ndarray, length: int) -> np.ndarray:
    """The inverse: (S, 2C, 2048, T) → (S, C, length), as HTDemucs._mask then _ispec."""
    sources, cc, freqs, frames = m.shape
    z = m.reshape(sources, cc // 2, 2, freqs, frames)
    z = z[:, :, 0] + 1j * z[:, :, 1]  # (S, C, F, T)
    z = np.concatenate((z, np.zeros_like(z[:, :, :1])), axis=2)  # the Nyquist bin back
    w = _window()
    seg = np.fft.irfft(z.transpose(0, 1, 3, 2), n=NFFT, axis=-1) * np.sqrt(NFFT) * w
    # Two silent frames on each side, then torch.istft's centring and the model's padding.
    total = frames + 4
    out = np.zeros((sources, cc // 2, NFFT + HOP * (total - 1)), dtype=np.float64)
    env = np.zeros(out.shape[-1])
    for t in range(total):
        env[t * HOP : t * HOP + NFFT] += w * w
    for k in range(frames):
        start = (k + 2) * HOP
        out[..., start : start + NFFT] += seg[:, :, k]
    begin = NFFT // 2 + HOP // 2 * 3
    return (out[..., begin : begin + length] / env[begin : begin + length]).astype(np.float32)


def _triangle(n: int) -> np.ndarray:
    w = np.concatenate((np.arange(1, n // 2 + 1), np.arange(n - n // 2, 0, -1))).astype(np.float32)
    return w / w.max()


def _padded(mix: np.ndarray, offset: int, chunk: int, target: int) -> np.ndarray:
    """demucs' TensorChunk.padded: the chunk centred in `target` samples, real audio around it
    where there is some, zeros past the ends."""
    start = offset - (target - chunk) // 2
    end = start + target
    lo, hi = max(0, start), min(mix.shape[-1], end)
    return np.pad(mix[:, lo:hi], ((0, 0), (lo - start, end - hi)))


def run_net(session, mix: np.ndarray) -> np.ndarray:
    """One network over one segment of `segment` samples: (C, L) → (S, C, L)."""
    m = spec(mix)
    out_spec, out_wave = session.run(None, {"mix": mix[None], "mag": m[None]})
    return out_wave[0] + ispec(out_spec[0], mix.shape[-1])


def apply(
    sessions: list[Callable[[], object]],
    weights: list[list[float]],
    mix: np.ndarray,
    segment: int,
    progress: Callable[[float], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> np.ndarray:
    """apply_model with split=True, overlap 0.25, shifts 0: (C, L) normalised → (S, C, L).
    `sessions` open the networks one at a time, so that only one is in memory; a network whose
    weights are all zero is not opened."""
    channels, length = mix.shape
    stride = int((1 - OVERLAP) * segment)
    offsets = range(0, length, stride)
    weight = _triangle(segment)
    used = [(s, w) for s, w in zip(sessions, weights, strict=True) if any(w)]
    steps, done = len(used) * len(offsets), 0
    total = None
    for opener, net_weights in used:
        session = opener()
        out = None
        sum_weight = np.zeros(length, dtype=np.float32)
        for offset in offsets:
            if cancelled and cancelled():
                raise Cancelled
            chunk = min(segment, length - offset)
            res = run_net(session, _padded(mix, offset, chunk, segment))
            trim = (segment - chunk) // 2
            res = res[..., trim : trim + chunk]
            if out is None:
                out = np.zeros((res.shape[0], channels, length), dtype=np.float32)
            out[..., offset : offset + chunk] += weight[:chunk] * res
            sum_weight[offset : offset + chunk] += weight[:chunk]
            done += 1
            if progress:
                progress(done / steps)
        del session
        out /= sum_weight
        out *= np.asarray(net_weights, dtype=np.float32)[:, None, None]
        total = out if total is None else total + out
    totals = np.sum([w for _, w in used], axis=0).astype(np.float32)
    return total / np.maximum(totals, 1e-9)[:, None, None]


def separate(
    y: np.ndarray,
    sessions: list[Callable[[], object]],
    weights: list[list[float]],
    segment: int,
    progress: Callable[[float], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> np.ndarray:
    """A whole song (L, 2) at the model's rate → its sources (S, L, 2), as demucs.api does: the
    song is normalised by its own level, separated, then scaled back."""
    mix = np.ascontiguousarray(y.T, dtype=np.float32)
    ref = mix.mean(axis=0)
    mean, std = float(ref.mean()), float(ref.std(ddof=1)) + 1e-8
    out = apply(sessions, weights, (mix - mean) / std, segment, progress, cancelled)
    return (out * std + mean).transpose(0, 2, 1)


def session(path: Path, providers: list[str] | None = None, threads: int = 0):
    import onnxruntime as ort

    options = ort.SessionOptions()
    # The arena keeps what a segment needed and more: 8 GB per network on the CPU (measured),
    # 0.7 GB without it, for the same speed.
    options.enable_cpu_mem_arena = False
    if threads:
        options.intra_op_num_threads = threads
    if providers and "DmlExecutionProvider" in providers:
        options.enable_mem_pattern = False  # DirectML requires it
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), options, providers=providers or ["CPUExecutionProvider"])
