"""Tempo and meter from a beat grid: no 4/4 is assumed, and how sure we are is measured."""

from __future__ import annotations

import numpy as np

METERS = (3, 4, 5, 6, 7)
# Sevens and fives are rare, and a four beats a three on equal evidence.
PRIOR = {3: 0.02, 4: 0.06, 5: -0.06, 6: 0.0, 7: -0.08}
# How far a chord change on a bar line counts next to Beat This!'s downbeat activation.
CHANGE_WEIGHT = 0.6
# Viterbi over bar positions: what it costs to break the count, in nats of downbeat evidence. High
# enough that one stray activation can't move a bar line; a missed beat shows for many bars, and
# pays. "Bar lines" in docs/BENCHMARKS.md has the sweep.
JUMP_COST = 6.0


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
    """The tracker's own beats: maxima of the 7-frame window around them, over the threshold,
    as Beat This!'s minimal postprocessing reads them. Adjacent equal maxima count once."""
    a = np.asarray(activation, dtype=float)
    if len(a) < 7:
        return np.zeros(0)
    window = np.lib.stride_tricks.sliding_window_view(np.pad(a, 3, mode="edge"), 7).max(axis=1)
    frames = np.flatnonzero((a == window) & (a > threshold))
    if len(frames) == 0:
        return np.zeros(0)
    keep = np.concatenate(([True], np.diff(frames) > 1))
    return frames[keep] / fps


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


def place_bar_lines(downbeat, changes, beats_per_bar: int, jump_cost: float = JUMP_COST) -> list[int]:
    """The beats that open a bar, for a song whose count can slip.

    A beat grid that follows the tempo can miss or add a beat, and then one count from the first
    downbeat would be wrong for the rest of the song. This finds the most likely position in the
    bar for every beat, the count advancing by one unless the evidence is worth breaking it.
    """
    d = np.clip(np.asarray(downbeat, dtype=float), 1e-3, 1 - 1e-3)
    c = np.asarray(changes, dtype=float)
    n, m = len(d), beats_per_bar
    if n == 0:
        return []
    # Position 0 is a bar line: downbeat evidence for it, and against it everywhere else.
    on = np.log(d) + CHANGE_WEIGHT * c
    off = np.log(1 - d)
    emit = np.tile(off[:, None], (1, m))
    emit[:, 0] = on
    score = emit[0].copy()
    back = np.zeros((n, m), dtype=np.int32)
    for t in range(1, n):
        follow = np.roll(score, 1)  # position p comes from p - 1
        best_jump = int(np.argmax(score))
        jump = score[best_jump] - jump_cost
        use_jump = jump > follow
        back[t] = np.where(use_jump, best_jump, (np.arange(m) - 1) % m)
        score = np.where(use_jump, jump, follow) + emit[t]
    positions = np.zeros(n, dtype=np.int32)
    positions[-1] = int(np.argmax(score))
    for t in range(n - 1, 0, -1):
        positions[t - 1] = back[t, positions[t]]
    return [int(i) for i in np.flatnonzero(positions == 0)]
