"""The stem mixer in the player: gains that glide, Original/Mix, and nothing else disturbed."""

import numpy as np
import pytest

from localchords.player import BLOCK, Mix, Player

SR = 44100


def tone(freq, seconds=4.0, level=0.3):
    t = np.arange(int(seconds * SR)) / SR
    y = (level * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([y, y], axis=1)


def song():
    """Three 'stems' of distinct pitch and their exact sum as the recording."""
    stems = np.stack([tone(220), tone(550), tone(1330)])
    return stems.sum(axis=0), stems.astype(np.float16)


def level_at(y, freq):
    spectrum = np.abs(np.fft.rfft(y[:, 0] * np.hanning(len(y)))) / len(y) * 4
    k = int(round(freq * len(y) / SR))
    return spectrum[k - 2 : k + 3].max()


def playing(mix, rate=1.0, pitch=0):
    p = Player(SR)
    p.test_mode = True
    p.load(mix)
    p.set_rate(rate)
    p.set_pitch(pitch)
    p.play()
    return p


def render(p, seconds):
    return np.concatenate([p.render(BLOCK) for _ in range(int(seconds * SR / BLOCK))])


def test_starts_as_the_original_and_unity_stems_sound_the_same():
    original, stems = song()
    mix = Mix(original, stems, SR)
    p = playing(mix)
    first = render(p, 1.0)
    assert np.allclose(first, original[: len(first)], atol=1e-6)
    mix.set_gains(0.0, [1.0, 1.0, 1.0])
    render(p, 0.2)  # the crossfade
    after = render(p, 0.5)
    start = int(round(p.cursor)) - len(after)
    assert np.allclose(after, original[start : start + len(after)], atol=2e-3)  # float16 stems


def test_a_stem_at_zero_is_truly_silent_and_the_others_stay():
    original, stems = song()
    mix = Mix(original, stems, SR)
    mix.set_gains(0.0, [1.0, 0.0, 1.0])
    p = playing(mix)
    render(p, 0.3)
    out = render(p, 1.0)
    assert level_at(out, 550) < 1e-6
    assert level_at(out, 220) == pytest.approx(0.3, rel=0.15)
    assert level_at(out, 1330) == pytest.approx(0.3, rel=0.15)


def test_gain_changes_glide_without_a_click():
    original, stems = song()
    mix = Mix(original, stems, SR)
    p = playing(mix)
    render(p, 0.5)
    mix.set_gains(0.0, [0.0, 0.0, 0.0])  # the hardest case: everything off at once
    out = np.concatenate([render(p, 0.1), render(p, 0.1)])
    # A click is a jump between neighbouring samples far beyond what the tones themselves make.
    biggest_step = np.abs(np.diff(out[:, 0])).max()
    natural = np.abs(np.diff(original[:, 0])).max()
    assert biggest_step <= natural * 1.05
    assert not out[int(0.05 * SR) :].any()  # silent once the glide (30 ms) is over


def test_mix_is_heard_through_speed_and_pitch():
    original, stems = song()
    mix = Mix(original, stems, SR)
    mix.set_gains(0.0, [0.0, 1.0, 0.0])
    p = playing(mix, rate=0.75)
    render(p, 0.3)
    out = render(p, 1.0)
    assert level_at(out, 550) > 0.2
    assert level_at(out, 220) < 0.01 and level_at(out, 1330) < 0.01
    p.set_pitch(12)
    render(p, 0.3)
    out = render(p, 1.0)
    assert level_at(out, 1100) > 0.15  # an octave up, the speed unchanged


def test_switching_source_keeps_the_clock():
    original, stems = song()
    p = playing(original)
    render(p, 1.0)
    before = p.cursor
    p.use_mix(Mix(original, stems, SR))
    assert p.cursor == before and p.duration == len(original) / SR
    render(p, 0.5)
    p.use_mix(None)
    assert isinstance(p.y, np.ndarray) and p.y is original
    with pytest.raises(ValueError):
        p.use_mix(Mix(original[:-10], stems[:, :-10], SR))


def test_boosted_stems_are_rounded_off_not_clipped():
    loud = np.stack([tone(220, level=0.8), tone(330, level=0.8)])
    mix = Mix(loud.sum(axis=0), loud.astype(np.float16), SR)
    mix.set_gains(0.0, [1.8, 1.8])
    mix.gains = mix.target.copy()
    out = mix[0 : SR]
    assert np.abs(out).max() <= 1.0
    quiet = np.abs(out) < 0.9
    assert np.allclose(out[quiet], (loud[:, :SR] * 1.8).sum(axis=0)[quiet], atol=3e-3)


def test_loop_and_seek_read_the_mix():
    original, stems = song()
    mix = Mix(original, stems, SR)
    mix.set_gains(0.0, [1.0, 0.0, 0.0])
    mix.gains = mix.target.copy()
    p = playing(mix)
    p.set_loop(1.0, 1.5)
    p.seek(1.4)
    out = render(p, 0.5)
    assert p.cursor < 1.5 * SR  # wrapped
    assert level_at(out, 550) < 1e-3 and level_at(out, 220) > 0.2  # the wrap leaks a little


def test_mixing_a_block_stays_cheap_on_a_long_song():
    import time

    n = SR * 60 * 20  # twenty minutes, six stems
    original = np.zeros((n, 2), dtype=np.float32)
    mix = Mix(original, np.zeros((6, n, 2), dtype=np.float16), SR)
    mix.set_gains(0.0, [1.0] * 6)
    p = playing(mix, rate=0.8)
    p.seek(600)
    start = time.perf_counter()
    for _ in range(100):
        p.render(BLOCK)
    assert (time.perf_counter() - start) / 100 < BLOCK / SR / 4
