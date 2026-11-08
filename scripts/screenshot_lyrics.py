"""Screenshots of the lyrics views (v1.3) on the synthetic demo piece, with lyrics written for it:
no recording and no words from a real song.

Usage: screenshot_lyrics.py <demo.wav from demo_audio.py> <out_dir>
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("LOCALCHORDS_DATA", str(Path("work/data-lyrics").resolve()))

from localchords import lyrics as L  # noqa: E402
from localchords.ui.main_window import MainWindow, app_instance  # noqa: E402
from localchords.ui.pdf import write_lyrics_sheet  # noqa: E402

# Two bars (8 beats) per line; None is a section heading. Written for this demo.
WORDS = [
    "[Couplet]",
    "Je pars au matin le long du canal",
    "Les volets s'ouvrent un à un",
    "Le pain chaud, le café, le journal",
    "Et la ville se lève avec moi",
    "[Refrain]",
    "On marche sans but jusqu'au pont",
    "Le soleil glisse sur les toits",
    "On fredonne un air sans façon",
    "Qui revient toujours comme une voix",
    "[Fin]",
    "Et le soir tombe doucement",
    "On rentre à pas lents, à pas lents",
]


def timed(beats: list[float]) -> list[dict]:
    lines, b = [], 0
    for text in WORDS:
        if text.startswith("["):
            lines.append({"text": text[1:-1], "start": None, "section": True})
            continue
        words = [i for i, ch in enumerate(text) if ch != " " and (i == 0 or text[i - 1] == " ")]
        span = beats[b : b + 9] if b + 8 < len(beats) else beats[b:]
        start, end = span[0], span[-1]
        step = (end - start) / len(words)
        lines.append({
            "text": text,
            "start": start,
            "end": end - 0.2,
            "words": [[c, start + i * step] for i, c in enumerate(words)],  # char, time
        })  # fmt: skip
        b += 8
    return lines


def main():
    audio, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    app = app_instance()
    w = MainWindow(muted=True)
    w.show()

    def settle(n=40):
        for _ in range(n):
            app.processEvents()
            time.sleep(0.01)

    def wait(cond, seconds=180):
        end = time.time() + seconds
        while time.time() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        return cond()

    w.open_path(audio)
    assert wait(lambda: w.job is None and w.audio_ready), "analysis or audio timed out"
    source = {"kind": "user", "name": "", "exportable": True}
    w.project.set_lyrics(L.new(timed(w.project.grid()), source))
    w._content_changed()
    lines = w.project.lyrics["lines"]
    w.seek(lines[2]["words"][3][1] + 0.05)
    for mode, size, name in (
        ("sheet", (1600, 900), "lyrics_sheet_1600"),
        ("sheet", (1360, 820), "lyrics_sheet_1360"),
        ("sheet", (5120, 1440), "lyrics_sheet_5120"),
        ("sheet", (560, 900), "lyrics_sheet_560"),
        ("lyrics", (1360, 820), "lyrics_only_1360"),
        ("strip", (1360, 820), "lyrics_strip_1360"),
    ):
        w.resize(*size)
        w.lyrics.set_mode(mode)
        settle()
        w.lyrics.tick(w.player.position, w.project.beat_at(w.player.position))
        settle()
        w.grab().save(str(out / f"{name}.png"))
    w.toggle_chords()  # T: the song's chords hidden, the lyrics get the room
    for mode, name in (("sheet", "lyrics_sheet_readme"), ("strip", "lyrics_strip_readme")):
        w.resize(1600, 900)
        w.lyrics.set_mode(mode)
        settle()
        w.lyrics.tick(w.player.position, w.project.beat_at(w.player.position))
        settle()
        w.grab().save(str(out / f"{name}.png"))
    w.toggle_chords()
    items, positions = w.song.chords.all_items, w.song.positions
    write_lyrics_sheet(w.project, out / "paroles_et_accords.pdf", {}, items, positions)
    w.lyrics.set_mode("grid")
    w.project.set_lyrics(None)
    w.flush()
    w.close()


if __name__ == "__main__":
    main()
