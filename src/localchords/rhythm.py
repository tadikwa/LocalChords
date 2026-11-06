"""Tempo and meter from a beat grid: no 4/4 is assumed, and how sure we are is measured."""

from __future__ import annotations

import numpy as np

METERS = (3, 4, 5, 6, 7)
# Sevens and fives are rare, and a four beats a three on equal evidence.
PRIOR = {3: 0.02, 4: 0.06, 5: -0.06, 6: 0.0, 7: -0.08}
# How far a chord change on a bar line counts next to Beat This!'s downbeat activation.
CHANGE_WEIGHT = 0.6


def tempo(beats) -> dict:
    """The median tempo and how steady the grid is, from the spread of its beat periods."""
    times = np.asarray(beats, dtype=float)
    if len(times) < 2:
        return {"bpm": None, "steadiness": None}
    gaps = np.diff(times)
    median = float(np.median(gaps))
    if median <= 0:
        return {"bpm": None, "steadiness": None}
    spread = float(np.percentile(gaps, 90) - np.percentile(gaps, 10)) / median
    return {"bpm": round(60.0 / median, 1), "steadiness": round(max(0.0, 1.0 - spread), 3)}


def peak_times(activation: np.ndarray, fps: float, threshold: float = 0.5) -> np.ndarray:
    """Local maxima of an activation over the threshold, in seconds."""
    a = np.asarray(activation, dtype=float)
    if len(a) < 3:
        return np.zeros(0)
    is_peak = (a[1:-1] >= a[:-2]) & (a[1:-1] > a[2:]) & (a[1:-1] > threshold)
    return (np.flatnonzero(is_peak) + 1) / fps


def grid_fit(grid, peaks, tol: float = 0.07) -> float:
    """F-measure between the grid and the tracker's own peaks: low when the tempo drifts."""
    grid, peaks = np.asarray(grid, dtype=float), np.asarray(peaks, dtype=float)
    if len(grid) < 2 or len(peaks) == 0:
        return 0.0
    index = np.clip(np.searchsorted(grid, peaks), 1, len(grid) - 1)
    near = np.minimum(np.abs(peaks - grid[index - 1]), np.abs(peaks - grid[index])) <= tol
    precision = near.mean()
    recall = min(near.sum(), len(grid)) / len(grid)
    return float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0


def infer_meter(downbeat, changes) -> dict:
    """Beats per bar and the first downbeat from per-beat evidence.

    downbeat: the probability of a downbeat at each beat. changes: 1 where a chord starts on the
    beat. A candidate scores what its bar lines catch over what falls between them. Confidence is
    the margin to the best reading with another bar length: it says whether the bar length is
    settled, not whether the phase is.
    """
    downbeat, changes = np.asarray(downbeat, dtype=float), np.asarray(changes, dtype=float)
    n = len(downbeat)
    if n < 8:
        return {"beats_per_bar": 4, "first_downbeat": 0, "confidence": 0.0, "candidates": [4]}
    best: dict[int, tuple[float, int]] = {}
    for meter in METERS:
        for phase in range(meter):
            on = np.zeros(n, dtype=bool)
            on[phase::meter] = True
            score = downbeat[on].mean() - downbeat[~on].mean()
            score += CHANGE_WEIGHT * (changes[on].mean() - changes[~on].mean())
            score += PRIOR[meter]
            if meter not in best or score > best[meter][0]:
                best[meter] = (float(score), phase)
    ranked = sorted(best, key=lambda m: best[m][0], reverse=True)
    top = ranked[0]
    margin = best[top][0] - best[ranked[1]][0]
    return {
        "beats_per_bar": top,
        "first_downbeat": best[top][1],
        "confidence": round(float(np.clip(margin / 0.25, 0.0, 1.0)), 3),
        "candidates": ranked[:3],
    }
