"""Playback: decoded samples in memory, a time-stretcher, and PortAudio.

The audio callback only reads what `render` produces, so everything but the device can be tested
without one. See docs/DECISIONS.md for why this is not QMediaPlayer: a seek there took about 450 ms
on the test machine, too much for an A/B loop.
"""

from __future__ import annotations

import threading
import time

import numpy as np

BLOCK = 1024  # frames per callback
RATE_MIN, RATE_MAX = 0.25, 2.0


class Wsola:
    """Waveform-similarity overlap-add: changes speed, keeps pitch.

    Windows overlap by half on the output side. Each next window is taken near where the speed
    says it should be, at the offset that best continues what was just written.
    """

    SIZE = 2048  # about 46 ms at 44.1 kHz: long enough for bass, short enough for attacks
    SEARCH = 512

    def __init__(self, channels: int):
        self.hop = self.SIZE // 2
        self.window = np.hanning(self.SIZE + 1)[:-1].astype(np.float32)[:, None]
        self.channels = channels
        self.reset()

    def reset(self) -> None:
        self.tail = np.zeros((self.hop, self.channels), dtype=np.float32)
        self.continuation: np.ndarray | None = None
        self.pending = np.zeros((0, self.channels), dtype=np.float32)
        self.last = np.zeros((1, self.channels), dtype=np.float32)
        self.phase = 0.0

    def resample(self, block: np.ndarray, ratio: float) -> np.ndarray:
        """Play a block `ratio` times faster, which raises its pitch; continuous across blocks.

        shortcut: linear interpolation dulls the top end a little and aliases slightly when going
        up, acceptable for practice; a polyphase filter would do better if it ever matters.
        """
        if ratio == 1.0:
            return block
        points = np.arange(self.phase, len(block), ratio)
        joined = np.concatenate((self.last, block))
        grid = np.arange(len(joined))
        out = np.stack(
            [np.interp(points, grid, joined[:, c]) for c in range(self.channels)], axis=1
        ).astype(np.float32)
        self.last = block[-1:]
        self.phase = (
            float(points[-1] + ratio - len(block)) if len(points) else self.phase - len(block)
        )
        return out

    def next_hop(self, y: np.ndarray, position: float) -> np.ndarray:
        """Write one hop from around `position`; the caller advances position by hop × rate."""
        center = int(position)
        lo = max(0, center - self.SEARCH)
        hi = min(len(y) - self.SIZE, center + self.SEARCH)
        if hi < lo:  # the last window of the song, padded with silence
            frame = np.zeros((self.SIZE, self.channels), dtype=np.float32)
            part = y[center : center + self.SIZE]
            frame[: len(part)] = part
        else:
            start = min(max(center, lo), hi)
            if self.continuation is not None and hi > lo:
                # What comes after the previous window is what the new one should start like.
                region = y[lo : hi + self.hop].mean(axis=1)
                target = self.continuation.mean(axis=1)
                size = len(region) + len(target)
                score = np.fft.irfft(
                    np.fft.rfft(region, size) * np.conj(np.fft.rfft(target, size)), size
                )
                start = lo + int(np.argmax(score[: hi - lo + 1]))
            frame = y[start : start + self.SIZE]
        self.continuation = frame[self.hop :]
        shaped = frame * self.window
        out = self.tail + shaped[: self.hop]
        self.tail = shaped[self.hop :]
        return out


class Player:
    """Thread-safe transport over a stereo float buffer.

    `position` is in seconds of the recording and already accounts for the output latency, so the
    interface shows the chord that is being heard rather than the one being written.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sr = sample_rate
        self.y = np.zeros((0, 2), dtype=np.float32)
        self.lock = threading.RLock()
        self.cursor = 0.0  # next frame to read, in frames of the recording
        self.rate = 1.0
        self.pitch = 1.0  # as a frequency ratio
        self.volume = 1.0
        self.playing = False
        self.loop: tuple[float, float] | None = None  # in frames
        self.stream = None
        self.latency = 0.0
        self.stretch = Wsola(2)
        self.last_error: str | None = None
        # The clock: the frame that reaches the speakers at _anchor_time.
        self._anchor_cursor = 0.0
        self._anchor_time = 0.0
        self._floor = 0.0

    # Content -----------------------------------------------------------------------------------
    def load(self, y: np.ndarray) -> None:
        with self.lock:
            self.y = np.asarray(y, dtype=np.float32)
            self.cursor = 0.0
            self.loop = None
            self.playing = False
            self.stretch.reset()
            self._mark()

    @property
    def duration(self) -> float:
        return len(self.y) / self.sr

    # Transport ---------------------------------------------------------------------------------
    def _mark(self) -> None:
        """Restart the clock here; the display holds at this frame until the audio catches up."""
        self._anchor_cursor = self.cursor
        self._anchor_time = time.perf_counter() + self.latency
        self._floor = self.cursor

    def play(self) -> None:
        with self.lock:
            if len(self.y) == 0:
                return
            if self.stream is not None and not self.stream.active:
                self.close_device()  # the device went away; try again with the default one
            if self.stream is None and not self.test_mode:
                self.open_device()
            if self.cursor >= len(self.y):
                self.cursor = 0.0
            self.playing = True
            self._mark()

    def pause(self) -> None:
        with self.lock:
            self.cursor = self.position * self.sr
            self.playing = False
            self.stretch.reset()
            self._mark()

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def seek(self, seconds: float) -> None:
        with self.lock:
            self.cursor = float(np.clip(seconds * self.sr, 0, max(len(self.y) - 1, 0)))
            self.stretch.reset()
            self._mark()

    def set_rate(self, rate: float) -> None:
        with self.lock:
            self.cursor = self.position * self.sr
            self.rate = float(np.clip(rate, RATE_MIN, RATE_MAX))
            self.stretch.reset()
            self._mark()

    def set_pitch(self, semitones: int) -> None:
        """Move what is heard by whole semitones, without changing the speed."""
        with self.lock:
            self.cursor = self.position * self.sr
            self.pitch = 2.0 ** (semitones / 12)
            self.stretch.reset()
            self._mark()

    def set_loop(self, start: float | None, end: float | None = None) -> None:
        """Loop [start, end) in seconds; None removes the loop."""
        with self.lock:
            if start is None or end is None or end <= start:
                self.loop = None
            else:
                self.loop = (start * self.sr, end * self.sr)

    @property
    def position(self) -> float:
        with self.lock:
            if not self.playing:
                return self.cursor / self.sr
            # Before the anchor's time that frame hasn't reached the speakers yet, so a negative
            # elapsed is right: it takes off the output latency.
            elapsed = time.perf_counter() - self._anchor_time
            frames = self._anchor_cursor + elapsed * self.sr * self.rate
            if self.loop:
                start, end = self.loop
                if self._anchor_cursor < end <= frames:
                    frames = start + (frames - end)
                elif self._anchor_cursor >= start and frames < start:
                    frames = end - (start - frames)  # just wrapped; the end is still sounding
            return float(np.clip(max(frames, self._floor), 0, len(self.y))) / self.sr

    # Rendering: no device needed ----------------------------------------------------------------
    def render(self, frames: int) -> np.ndarray:
        """The next `frames` stereo frames. Silence when paused; stops at the end of the song."""
        out = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            if not self.playing or len(self.y) == 0:
                return out
            done = 0
            while done < frames:
                if self.rate == 1.0 and self.pitch == 1.0:
                    done += self._copy_plain(out[done:])
                else:
                    done += self._copy_stretched(out[done:])
                if self.cursor >= len(self.y):
                    self.playing = False
                    self.cursor = float(len(self.y))
                    break
            if self.volume != 1.0:
                out *= self.volume
        return out

    def _wrap(self, before: float) -> None:
        """Back to the loop's start on crossing its end; a cursor past it just plays on."""
        if self.loop and before < self.loop[1] <= self.cursor:
            self.cursor = self.loop[0] + (self.cursor - self.loop[1])

    def _copy_plain(self, out: np.ndarray) -> int:
        before = self.cursor
        limit = self.loop[1] if self.loop and before < self.loop[1] else len(self.y)
        start = int(before)
        count = min(len(out), int(limit) - start)
        if count <= 0:
            self.cursor = float(limit)
            self._wrap(before)
            return 0
        out[:count] = self.y[start : start + count]
        self.cursor += count
        self._wrap(before)
        return count

    def _copy_stretched(self, out: np.ndarray) -> int:
        stretch = self.stretch
        if len(stretch.pending) == 0:
            # Resampling shortens the block by `pitch`, so the stretcher makes up for it.
            block = stretch.next_hop(self.y, self.cursor)
            stretch.pending = stretch.resample(block, self.pitch)
            before = self.cursor
            self.cursor += stretch.hop * self.rate / self.pitch
            self._wrap(before)
        count = min(len(out), len(stretch.pending))
        out[:count] = stretch.pending[:count]
        stretch.pending = stretch.pending[count:]
        return count

    # The device --------------------------------------------------------------------------------
    test_mode = False  # tests render by hand and must not open the speakers

    def _callback(self, outdata, frames, time_info, status) -> None:
        with self.lock:
            if self.playing:
                self._anchor_cursor = self.cursor
                self._anchor_time = time.perf_counter() + self.latency
            outdata[:] = self.render(frames)

    def open_device(self) -> bool:
        """Open the default output. Returns False with `last_error` set when there is none."""
        import sounddevice as sd

        try:
            self.stream = sd.OutputStream(
                device=output_device(),
                samplerate=self.sr,
                channels=2,
                dtype="float32",
                blocksize=BLOCK,
                latency="low",
                callback=self._callback,
            )
            self.stream.start()
            self.latency = float(self.stream.latency)
            self.last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - PortAudio has many ways to fail, all alike here
            self.stream = None
            self.last_error = f"Sortie audio indisponible : {exc}"
            return False

    def close_device(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:  # noqa: BLE001, S110 - a vanished device is already closed
                pass
            self.stream = None


def output_device() -> int | None:
    """WASAPI's default output: lower latency than the MME device PortAudio picks by default."""
    import sounddevice as sd

    try:
        for api in sd.query_hostapis():
            if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
                return api["default_output_device"]
    except Exception:  # noqa: BLE001, S110 - PortAudio's own default is the fallback
        pass
    return None


def device_sample_rate() -> int:
    """The output's rate, which the recording gets resampled to; 44100 without a device."""
    import sounddevice as sd

    try:
        return int(sd.query_devices(output_device(), kind="output")["default_samplerate"])
    except Exception:  # noqa: BLE001 - no device: the interface reports it when one is opened
        return 44100
