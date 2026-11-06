import time

import numpy as np
import pytest

from localchords.player import BLOCK, Player, device_sample_rate

SR = 44100


def sine(freq=440.0, seconds=10.0):
    t = np.arange(int(seconds * SR)) / SR
    y = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([y, y], axis=1)


def ramp(seconds=10.0):
    """Every sample holds its own time, so what comes out says where it came from."""
    t = (np.arange(int(seconds * SR)) / SR).astype(np.float32)
    return np.stack([t, t], axis=1)


def peak_hz(y):
    spectrum = np.abs(np.fft.rfft(y[:, 0] * np.hanning(len(y))))
    return np.argmax(spectrum) * SR / len(y)


def render_seconds(p, seconds):
    return np.concatenate([p.render(BLOCK) for _ in range(int(seconds * SR / BLOCK))])


def test_paused_is_silent_and_does_not_move():
    p = Player(SR)
    p.test_mode = True
    p.load(sine())
    assert not p.render(BLOCK).any()
    assert p.position == 0


def test_plain_playback_is_the_recording():
    p = Player(SR)
    p.test_mode = True
    p.load(ramp())
    p.play()
    out = render_seconds(p, 1.0)
    assert np.allclose(out[:, 0], np.arange(len(out), dtype=np.float32) / SR, atol=1e-4)


def test_seek_is_exact_and_clamped():
    p = Player(SR)
    p.test_mode = True
    p.load(ramp())
    p.seek(3.0)
    p.play()
    assert p.render(BLOCK)[0, 0] == pytest.approx(3.0, abs=1e-4)
    p.seek(-5)
    assert p.cursor == 0
    p.seek(999)
    assert p.cursor == len(p.y) - 1


def test_end_of_song_stops_and_play_restarts():
    p = Player(SR)
    p.test_mode = True
    p.load(sine(seconds=0.1))
    p.play()
    out = render_seconds(p, 0.5)
    assert not p.playing
    assert not out[-BLOCK:].any()
    p.play()
    assert p.playing and p.cursor == 0


def test_loop_is_gapless_at_normal_speed():
    p = Player(SR)
    p.test_mode = True
    p.load(ramp())
    p.set_loop(1.0, 2.0)
    p.seek(1.0)
    p.play()
    out = render_seconds(p, 3.5)[:, 0]
    assert out.min() >= 1.0 - 1e-3 and out.max() < 2.0
    jumps = np.flatnonzero(np.diff(out) < 0)
    assert len(jumps) == 3
    # No sample is lost at the seam: the next sample is exactly the loop's first.
    assert out[jumps[0] + 1] == pytest.approx(1.0, abs=1e-3)


def test_seek_into_loop_after_its_end_plays_on_from_there():
    p = Player(SR)
    p.test_mode = True
    p.load(ramp())
    p.set_loop(1.0, 2.0)
    p.seek(5.0)
    p.play()
    assert p.render(BLOCK)[0, 0] > 1.9


@pytest.mark.parametrize("rate", [0.5, 0.75, 1.25, 1.5])
def test_stretch_keeps_pitch_and_takes_the_right_time(rate):
    p = Player(SR)
    p.test_mode = True
    p.load(sine(440.0, seconds=8.0))
    p.set_rate(rate)
    p.play()
    out = render_seconds(p, 2.0)
    assert peak_hz(out[SR // 4 :]) == pytest.approx(440.0, abs=3)
    assert p.cursor / SR == pytest.approx(2.0 * rate, abs=0.08)


@pytest.mark.parametrize("rate", [0.5, 0.75])
def test_stretch_of_a_pure_tone_has_no_gaps_or_jumps(rate):
    p = Player(SR)
    p.test_mode = True
    p.load(sine(220.0, seconds=6.0))
    p.set_rate(rate)
    p.play()
    out = render_seconds(p, 2.0)[SR // 4 :, 0]
    envelope = np.abs(out[: len(out) // 512 * 512]).reshape(-1, 512).max(axis=1)
    # The overlap keeps the level steady: no block falls near silence, none overshoots.
    assert envelope.min() > 0.3 and envelope.max() < 0.75


def test_stretch_loop_stays_inside():
    p = Player(SR)
    p.test_mode = True
    p.load(ramp())
    p.set_loop(1.0, 1.5)
    p.seek(1.0)
    p.set_rate(0.5)
    p.play()
    render_seconds(p, 3.0)
    assert 1.0 * SR - 1 <= p.cursor <= 1.5 * SR


def test_position_tracks_rate_while_playing():
    p = Player(SR)
    p.test_mode = True
    p.load(sine())
    p.set_rate(0.5)
    p.play()
    p._mark()
    time.sleep(0.2)
    assert p.position == pytest.approx(0.1, abs=0.04)


def test_pause_keeps_position():
    p = Player(SR)
    p.test_mode = True
    p.load(sine())
    p.seek(4.0)
    p.play()
    p._mark()
    p.pause()
    assert p.position == pytest.approx(4.0, abs=0.02)


def test_long_track_render_stays_fast():
    # One hour of stereo at 44.1 kHz: rendering must not scale with the length of the song.
    p = Player(SR)
    p.test_mode = True
    p.load(np.zeros((SR * 3600, 2), dtype=np.float32))
    p.set_rate(0.75)
    p.seek(1800)
    p.play()
    start = time.perf_counter()
    for _ in range(100):
        p.render(BLOCK)
    per_block = (time.perf_counter() - start) / 100
    assert per_block < BLOCK / SR / 2


@pytest.mark.device
def test_real_device_plays_and_position_follows():
    p = Player(device_sample_rate())
    p.load(sine(seconds=5.0))
    p.volume = 0.0  # silent: this is a test, not a concert
    if not p.open_device():
        pytest.skip(p.last_error)
    try:
        p.seek(1.0)
        p.play()
        time.sleep(1.0)
        heard = p.position
        written = p.cursor / SR
        assert heard == pytest.approx(2.0, abs=0.25)
        assert written >= heard
        p.pause()
        stopped = p.position
        time.sleep(0.2)
        assert p.position == stopped
    finally:
        p.close_device()
