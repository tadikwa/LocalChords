"""Open a song in the real window and save screenshots: for looking at the interface.

Usage: screenshot.py <audio> <out_dir>
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("LOCALCHORDS_DATA", str(Path("work/data").resolve()))

from localchords.ui import dialogs  # noqa: E402
from localchords.ui.main_window import MainWindow, app_instance  # noqa: E402


def main():
    audio, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    app = app_instance()
    w = MainWindow(muted=True)
    w.show()
    app.processEvents()
    w.grab().save(str(out / "home.png"))

    def wait(cond, seconds=180):
        end = time.time() + seconds
        while time.time() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        return cond()

    w.open_path(audio)
    for _ in range(50):
        app.processEvents()
        time.sleep(0.02)
    w.grab().save(str(out / "analyzing.png"))
    assert wait(lambda: w.job is None), "analysis timed out"
    assert wait(lambda: w.audio_ready), "audio not loaded"
    t = time.time()
    w.seek(w.project.grid()[len(w.project.grid()) // 3])
    for size, name in (
        ((640, 1400), "song_640_narrow"),
        ((1000, 1400), "song_1000_narrow"),
        ((1360, 820), "song_1360"),
        ((1920, 1080), "song_1920"),
        ((5120, 1440), "song_5120"),
    ):
        w.resize(*size)
        for _ in range(20):
            app.processEvents()
        w._follow(w.project.beat_at(w.player.position))
        for _ in range(40):
            app.processEvents()
            time.sleep(0.01)
        w.grab().save(str(out / f"{name}.png"))
    w.resize(1360, 820)
    s = w.song
    s.audio_button.click()  # the audio follows the transposition: the button says so
    s.transpose.step(3)
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / "song_audio_transposed.png"))
    w.resize(640, 1400)
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / "song_audio_transposed_640.png"))
    w.resize(1360, 820)
    next(a for a in s.detail_actions.actions() if a.data() == "analysis").trigger()
    grid = w.project.grid()
    s.grid.set_selection(len(grid) // 3, len(grid) // 3 + 3)
    w._set_loop((grid[len(grid) // 3], grid[len(grid) // 3 + 8]))
    app.processEvents()
    w.grab().save(str(out / "song_analysis_loop.png"))
    editor = dialogs.ChordEditor(w.project, len(grid) // 3, len(grid) // 3, w)
    editor.show()
    app.processEvents()
    editor.grab().save(str(out / "editor.png"))
    editor.close()
    dialog = dialogs.RhythmDialog(w.project, w)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(out / "rhythm.png"))
    dialog.close()
    print(
        "key",
        w.project.key(),
        "tempo",
        w.project.tempo(),
        "meter",
        w.project.meter(),
        "fit",
        w.project.analysis.get("grid_fit"),
    )
    print([s.chord for s in w.project.segments()][:20])
    w.close()


if __name__ == "__main__":
    main()
