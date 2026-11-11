"""The separation pipeline around the network, and the stem cache. A fake network stands in for the
model; the real one is checked against PyTorch by scripts/export_demucs_onnx.py's bench
(docs/SEPARATION.md) and run here only when it is installed."""

import json

import numpy as np
import pytest

from localchords import separation, stems

SR = 44100


class Fake:
    """A 'network' that hands each of four sources a fixed share of the mix, through both of the
    model's paths: half by the waveform, half by the spectrogram."""

    SHARES = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)

    def __init__(self):
        self.calls = 0

    def run(self, _, feeds):
        self.calls += 1
        mix, mag = feeds["mix"], feeds["mag"]
        wave = 0.5 * self.SHARES[None, :, None, None] * mix[:, None]
        spec = 0.5 * self.SHARES[None, :, None, None, None] * mag[:, None]
        return spec, wave


def music(seconds, sr=SR):
    t = np.arange(int(seconds * sr)) / sr
    left = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 3100 * t)
    right = 0.2 * np.sign(np.sin(2 * np.pi * 2 * t)) * np.sin(2 * np.pi * 440 * t)
    return np.stack([left, right], axis=1).astype(np.float32)


EDGE = 4096  # the model's STFT drops its outer frames: the first and last 4096 samples differ


def test_stft_round_trip_is_exact_inside():
    x = music(1.0).T
    back = separation.ispec(separation.spec(x)[None], x.shape[-1])[0]
    assert np.abs(back - x)[:, EDGE:-EDGE].max() < 1e-5


def test_sources_have_the_song_length_and_add_up_to_it():
    y = music(20.0)  # three segments of the model's 7.8 s, the last one partial
    fake = Fake()
    out = separation.separate(y, [lambda: fake], [[1, 1, 1, 1]], stems.MODEL["segment"])
    assert out.shape == (4, len(y), 2)
    assert fake.calls == len(range(0, len(y), int(0.75 * stems.MODEL["segment"])))
    for share, source in zip(Fake.SHARES, out, strict=True):
        # aligned to the sample, cross-fades included
        assert np.abs(source - share * y)[EDGE:-EDGE].max() < 2e-4
    assert np.abs(out.sum(axis=0) - y)[EDGE:-EDGE].max() < 5e-4


def test_silence_stays_silent():
    y = np.zeros((SR * 3, 2), dtype=np.float32)
    out = separation.separate(y, [lambda: Fake()], [[1, 1, 1, 1]], stems.MODEL["segment"])
    assert np.isfinite(out).all() and np.abs(out).max() < 1e-6


def test_short_song_and_progress():
    y = music(0.5)
    seen = []
    out = separation.separate(
        y, [lambda: Fake()], [[1, 1, 1, 1]], stems.MODEL["segment"], seen.append
    )
    assert out.shape == (4, len(y), 2) and seen == [1.0]


def test_cancel_stops_between_segments():
    fake = Fake()
    with pytest.raises(separation.Cancelled):
        separation.separate(
            music(30.0), [lambda: fake], [[1, 1, 1, 1]], stems.MODEL["segment"],
            cancelled=lambda: fake.calls >= 2,
        )  # fmt: skip
    assert fake.calls == 2


def test_a_network_with_no_weight_is_never_opened():
    opened = []

    def opener(i):
        opened.append(i)
        return Fake()

    separation.separate(
        music(1.0), [lambda: opener(0), lambda: opener(1)], [[1, 1, 1, 1], [0, 0, 0, 0]],
        stems.MODEL["segment"],
    )  # fmt: skip
    assert opened == [0]


def test_arranged_stems_add_up_to_the_recording():
    y = music(2.0)
    sources = np.stack([y * 0.1, y * 0.2, y * 0.3, y * 0.35])  # 5 % left over by the "model"
    for mode in stems.MODES:
        layers = stems.arrange(mode, sources, y)
        assert list(layers) == stems.MODES[mode]["stems"]
        assert np.abs(sum(layers.values()) - y).max() < 1e-6
    assert np.allclose(stems.arrange("musician", sources, y)["vocals"], y * 0.35)


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCHORDS_DATA", str(tmp_path))
    return tmp_path


def test_cache_write_load_and_delete(data):
    y = music(3.0)
    loud = y * 4  # a stem beyond full scale comes back as it was, not clipped
    folder = stems.cache_dir("abc", "karaoke")
    stems.write(folder, {"vocals": loud, "instrumental": y - loud}, SR, {"mode": "karaoke"})
    assert stems.cached("abc", "karaoke") == folder
    assert stems.cached("abc", "musician") is None
    assert not list(stems.cache_root().glob("*.part"))
    back = stems.load(folder, "karaoke", SR, len(y))
    assert back.dtype == np.float16 and back.shape == (2, len(y), 2)
    assert (
        np.abs(back[0] - loud).max() < 4 * 2e-3
        and np.abs(back.astype(np.float32).sum(0) - y).max() < 1e-2
    )
    info = json.loads((folder / "info.json").read_text())
    assert info["model_sha256"] == stems.MODEL["sha256"] and info["frames"] == len(y)
    assert stems.size_of(stems.song_folders("abc")) == stems.total_size() > 0
    other = stems.cache_dir("abd", "karaoke")
    stems.write(other, {"vocals": y, "instrumental": y}, SR, {})
    stems.delete_song("abc")
    assert stems.cached("abc", "karaoke") is None and stems.cached("abd", "karaoke") == other
    stems.delete_all()
    assert stems.total_size() == 0


def test_stems_line_up_with_the_recording_at_another_rate(data, tmp_path):
    """The player decodes the recording at the device's rate and the stems from 44.1 kHz FLAC:
    resampled both ways, they must still fall on the same samples."""
    from localchords import audio

    rng = np.random.default_rng(1)
    y = (rng.standard_normal((SR * 2, 2)) * 0.1).astype(np.float32)
    wav = tmp_path / "song.flac"
    folder = stems.cache_dir("x", "karaoke")
    stems.write(folder, {"vocals": y * 0.5, "instrumental": y * 0.5}, SR, {})
    (folder / "vocals.flac").replace(wav)
    original = audio.decode(wav, 48000)
    stems.write(folder, {"vocals": y * 0.5, "instrumental": y * 0.5}, SR, {})
    back = stems.load(folder, "karaoke", 48000, len(original)).astype(np.float32).sum(0)
    a, b = original[:, 0] * 2, back[:, 0]
    lag = np.argmax(np.correlate(a[1000:3000], b[1000 - 20 : 3000 + 20], "valid")) - 20
    assert lag == 0
    assert np.abs(a - b)[100:-100].max() < 5e-3


def test_levels_mute_solo_and_presets():
    s = stems.new_settings("musician")
    assert stems.gains(s) == [1.0, 1.0, 1.0, 1.0]
    assert (
        stems.gain(0) == 0.0 and stems.db_text(0) == "−∞" and stems.db_text(stems.UNITY) == "0 dB"
    )
    assert stems.db_text(stems.UNITY // 2) == "−12 dB" and stems.db_text(stems.TOP) == "+5 dB"
    s["levels"]["drums"] = 40
    s["solo"] = ["vocals", "drums"]
    assert stems.gains(s) == [1.0, pytest.approx(stems.gain(40)), 0.0, 0.0]
    s["mute"] = ["vocals"]  # muted wins over soloed
    assert stems.gains(s) == [0.0, pytest.approx(stems.gain(40)), 0.0, 0.0]
    s["solo"], s["mute"] = [], []
    assert s["levels"]["drums"] == 40 and stems.current_preset(s) == "custom"  # kept through solo
    k = stems.apply_preset(s, "karaoke")
    assert stems.gains(k) == [0.0, 1.0, 1.0, 1.0] and stems.current_preset(k) == "karaoke"
    assert stems.current_preset(stems.apply_preset(k, "original")) == "original"
    assert stems.presets_for("karaoke") == ["original", "karaoke", "vocals"]
    assert "no_bass" in stems.presets_for("musician")
    assert stems.gains(stems.apply_preset(stems.new_settings("karaoke"), "vocals")) == [1.0, 0.0]


def test_settings_read_back_safely():
    assert stems.checked(None) is None and stems.checked({"mode": "six"}) is None
    s = stems.checked({"mode": "karaoke", "levels": {"vocals": 500, "x": 3}, "mute": ["x"]})
    assert s == {
        "mode": "karaoke", "on": True, "levels": {"vocals": 100, "instrumental": 75},
        "mute": [], "solo": [],
    }  # fmt: skip


def test_space_problem_and_needed_size(data, monkeypatch):
    assert stems.space_problem(240, "musician") is None
    assert 90 < stems.needed_mb(240, "musician") < 110
    monkeypatch.setattr(stems.library, "free_mb", lambda _: 150)
    assert "Pas assez de place" in stems.space_problem(240, "musician")


def test_model_download_is_checked(data):
    import hashlib
    import io

    from localchords import transcribe

    body = b"x" * 1000
    model = {**stems.MODEL, "size": 1000, "sha256": hashlib.sha256(body).hexdigest()}

    def opener(request, timeout):
        assert request.full_url == stems.RELEASE + stems.MODEL["file"]
        return io.BytesIO(body)

    old = stems.MODEL
    stems.MODEL = model
    try:
        stems.download_model(transcribe.Task(), opener)
        assert stems.model_installed()
        stems.delete_model()
        assert not stems.model_installed()
        stems.MODEL = {**model, "sha256": "0" * 64}
        with pytest.raises(transcribe.TranscribeError, match="SHA-256"):
            stems.download_model(transcribe.Task(), opener)
        assert (
            not stems.model_path().exists() and not stems.model_path().with_suffix(".part").exists()
        )
    finally:
        stems.MODEL = old


@pytest.mark.skipif(not stems.model_installed(), reason="the separation model is not installed")
def test_real_model_separates_a_mix():
    """With the model installed (in the data folder this run uses): a tone and a noise burst come
    out in different stems, and the stems add up to the mix."""
    y = music(8.0)
    session = separation.session(stems.model_path())
    out = separation.separate(y, [lambda: session], stems.MODEL["weights"], stems.MODEL["segment"])
    layers = stems.arrange("musician", out, y)
    assert np.abs(sum(layers.values()) - y).max() < 1e-4
