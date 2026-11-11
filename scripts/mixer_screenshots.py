"""The Mixage panel for real, offscreen: open a free song, separate it with the real model (or find
its stems again), mix, and grab the window at 1920 x 1080 and 1360 x 820. Set LOCALCHORDS_DATA to a
test data folder first: the model and the stems go there.

    python scripts/mixer_screenshots.py <song> <output folder>
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
from pathlib import Path


def main():
    if not os.environ.get("LOCALCHORDS_DATA"):
        sys.exit("Set LOCALCHORDS_DATA to a test data folder: this must not touch your own library.")
    from localchords.ui.main_window import MainWindow, app_instance
    app = app_instance()
    song, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    w = MainWindow(muted=True)
    w.resize(1920, 1080)
    w.show()

    def wait(cond, s=600):
        end = time.time() + s
        while time.time() < end:
            app.processEvents()
            if cond():
                return True
            time.sleep(0.01)
        return False

    t = time.time()
    w.open_audio(song)
    assert wait(lambda: w.project is not None and w.job is None and w.audio_ready), "analysis"
    print("analysed in", round(time.time() - t, 1), "s; segments", len(w.project.segments()))
    c = w.mixer
    c.button.setChecked(True)
    app.processEvents()
    w.grab().save(str(out / "1-intro.png"))
    if w.player.mix is None and c.folder is None:
        c.panel.mode_buttons["musician"].click()
        t = time.time()
        c.panel.separate.click()
        wait(lambda: c.panel.progress.value() > 300, 120)
        w.grab().save(str(out / "2-work.png"))
        assert wait(lambda: w.player.mix is not None, 600), (c.error, c.panel.warn.text())
        print("separated + loaded in", round(time.time() - t, 1), "s")
    else:
        assert wait(lambda: w.player.mix is not None, 60)
        print("found in cache")
    rows = {r.name: r for r in c.panel.stem_rows}
    rows["bass"].slider.setValue(0)
    rows["drums"].slider.setValue(45)
    w.player.play()
    t0 = time.time()
    wait(lambda: time.time() - t0 > 3, 5)
    print("position after 3 s:", round(w.player.position, 2), "target", list(w.player.mix.target))
    w.grab().save(str(out / "3-console.png"))
    w.resize(1360, 820)
    wait(lambda: False, 0.2)
    w.grab().save(str(out / "4-console-1360.png"))
    w.player.pause()
    w.flush()
    w.close()


if __name__ == "__main__":
    main()
