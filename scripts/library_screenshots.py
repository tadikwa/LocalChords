"""Fill a throwaway library with original demo songs and photograph the home page.

Every song is synthesised here (tests/synth.py) and analysed by the real engine; titles and
artists are invented. Nothing touches the user's own data: a fresh temporary folder is used.

Usage: library_screenshots.py <out_dir>
"""

import os
import sys
import tempfile
import time
from pathlib import Path

DATA = Path(tempfile.mkdtemp(prefix="localchords-demo-"))
os.environ["LOCALCHORDS_DATA"] = str(DATA / "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import synth  # noqa: E402

from localchords.ui.main_window import MainWindow, app_instance  # noqa: E402

# (title, artist, genre, year, bpm, chords): all invented for the demonstration.
SONGS = [
    ("Le vent du nord", "Les Marées Basses", "Folk", 2019, 96, ["G:maj", "D:maj", "E:min", "C:maj"]),
    ("Café des étoiles", "Lina Ferrand", "Jazz", 2021, 110, ["D:min7", "G:7", "C:maj7", "A:7"]),
    ("Route 9", "Les Marées Basses", "Rock", 2018, 132, ["E:maj", "A:maj", "B:maj", "A:maj"]),
    ("Petite pluie", "Lina Ferrand", "Variété", 2022, 84, ["F:maj", "C:maj", "D:min", "A#:maj"]),
    ("Minuit au port", "Orchestre du Quai", "Jazz", 2016, 120, ["A:min7", "D:7", "G:maj7", "E:7"]),
    ("Danse des cerfs", "Orchestre du Quai", "Folk", 2020, 140, ["D:maj", "A:maj", "B:min", "G:maj"]),
    ("Lumière d'hiver", "Clément Aubry", "", None, 72, ["C:maj", "A:min", "F:maj", "G:maj"]),
    ("Sous le pont", "Clément Aubry", "Blues", 2017, 100, ["A:7", "D:7", "A:7", "E:7"]),
]


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = app_instance()
    w = MainWindow(muted=True)
    w.resize(1600, 900)
    w.show()

    def pump(seconds=0.3):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    def wait(cond, seconds=300):
        end = time.time() + seconds
        while time.time() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        assert cond(), "timed out"

    wait(lambda: not w.home.scanning)
    pump()
    w.grab().save(str(out / "library-welcome.png"))

    audio_dir = DATA / "Musique"
    audio_dir.mkdir()
    ids = {}
    for title, artist, genre, year, bpm, chords in SONGS:
        y, _ = synth.render([(c, 4) for c in chords] * 4, bpm)
        wav = synth.write_wav(audio_dir / f"{title}.wav", y)
        w.open_path(wav)
        wait(lambda: w.job is None and w.project is not None)
        w.project.audio.update(title=title, artist=artist, genre=genre, year=year)
        w.save()
        ids[title] = w.project_file.stem
        time.sleep(1.1)  # distinct "added" times, to the second
    w.go_home()
    c = w.catalog
    c.set_favorite([ids["Café des étoiles"], ids["Le vent du nord"], ids["Sous le pont"]], True)
    c.add_tag([ids["Route 9"], ids["Danse des cerfs"]], "à travailler")
    rehearsal = c.create_collection("Répétition du jeudi")
    c.add_to_collection(rehearsal, [ids[t] for t in ("Danse des cerfs", "Route 9", "Petite pluie")])
    c.create_collection("Mariage de Jeanne")
    home = w.home
    home.refresh()
    home.select_view(("all",))
    home.table.selectRow(1)
    pump(1)
    w.grab().save(str(out / "library-list.png"))
    home.set_mode("cards")
    pump()
    w.grab().save(str(out / "library-cards.png"))
    home.set_mode("list")
    home.select_view(("fav",))
    pump()
    w.grab().save(str(out / "library-favorites.png"))
    home.select_view(("all",))
    home.search.setText("ferrand")
    pump(0.6)
    w.grab().save(str(out / "library-search.png"))
    home.search.clear()
    home.select_view(("col", rehearsal))
    pump()
    w.grab().save(str(out / "library-collection.png"))
    home.select_view(("all",))
    w.resize(5120, 1440)
    pump()
    w.grab().save(str(out / "library-5120.png"))
    w.resize(900, 900)
    pump()
    w.grab().save(str(out / "library-900.png"))
    w.close()
    print("demo data in", DATA)


if __name__ == "__main__":
    main()
