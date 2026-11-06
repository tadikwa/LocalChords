"""`LocalChords.exe --self-test <audio> <report folder>`: the whole scenario, run inside the packaged
program, for the proof that the build works: open, analyze, play, correct, transpose, save, export,
reopen. Writes report.json, silently: playback goes through the real device at zero volume."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path


def run(audio_path: Path, out: Path) -> int:
    from . import library
    from .ui.main_window import MainWindow, app_instance
    from .ui.pdf import write_pdf

    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"audio": str(audio_path), "steps": [], "ok": False}
    app = app_instance()

    def wait(condition, seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            if condition():
                return True
            time.sleep(0.003)
        return False

    def step(name, ok, **details):
        report["steps"].append({"step": name, "ok": bool(ok), **details})
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
        if not ok:
            raise AssertionError(name)

    try:
        started = time.perf_counter()
        window = MainWindow(muted=True)
        window.show()
        app.processEvents()
        step("démarrage", True, seconds=round(time.perf_counter() - started, 2))
        window.grab().save(str(out / "1_accueil.png"))

        started = time.perf_counter()
        window.open_path(audio_path)
        done = wait(lambda: window.job is None, 600)
        seconds = time.perf_counter() - started
        project = window.project
        segments = project.segments() if done else []
        step(
            "analyse",
            done and segments,
            seconds=round(seconds, 1),
            audio_seconds=project.duration,
            engine=project.analysis.get("engine"),
            key=project.key(),
            tempo=project.tempo(),
            meter=project.meter(),
            chords=[s.chord for s in segments][:24],
            status=window.song.status_detail.text() if not segments else "",
        )
        step("audio chargé", wait(lambda: window.audio_ready, 60))
        window.resize(1600, 900)
        wait(lambda: False, 0.2)
        window.grab().save(str(out / "2_grille.png"))

        window.seek(0)
        window.toggle_play()
        beat_before = window.song.grid.current
        wait(lambda: False, 3.0)
        position = window.player.position
        step(
            "lecture",
            window.player.playing and 2.0 < position < 4.0,
            position=round(position, 3),
            device=window.player.stream is not None,
            latency=window.player.latency,
            highlight=(beat_before, window.song.grid.current),
        )
        expected = project.beat_at(window.player.position)
        step("synchronisation", abs(window.song.grid.current - expected) <= 1)
        grid = project.grid()
        window.seek(grid[len(grid) // 2])
        window.song.speed.step(-3)
        window._set_loop((grid[len(grid) // 2], grid[len(grid) // 2 + 4]))
        wait(lambda: False, 1.5)
        loop_end = grid[len(grid) // 2 + 4]
        step(
            "ralenti et boucle",
            window.player.rate < 1 and window.player.position <= loop_end + 0.2,
            rate=window.player.rate,
        )
        window.toggle_play()
        window._set_loop(None)

        first = project.segments()[len(project.segments()) // 2]
        window.apply_chord(first.start_beat, first.end_beat - 1, "E:min7", None)
        corrected = window.song.grid.symbols[first.start_beat]
        step("correction", corrected[2].chord == "E:min7" and corrected[2].edited)
        window.song.transpose.step(2)
        step("transposition", "F" in window.song.grid.symbols[first.start_beat][0])
        window.grab().save(str(out / "3_corrigee_transposee.png"))
        before = [s.chord for s in project.segments()]

        window.export_to(out / "grille.txt", "txt")
        window.export_to(out / "grille.cho", "cho")
        write_pdf(project, out / "grille.pdf")
        sizes = {p.name: p.stat().st_size for p in out.glob("grille.*")}
        step("export", len(sizes) == 3 and all(sizes.values()), sizes=sizes)

        window.flush()
        saved = window.project_file
        window.close()

        started = time.perf_counter()
        window = MainWindow(muted=True)
        window.show()
        window.open_path(audio_path)
        reopened = time.perf_counter() - started
        step(
            "réouverture sans recalcul",
            window.job is None
            and [s.chord for s in window.project.segments()] == before
            and window.project.view["transpose"] == 2,
            seconds=round(reopened, 2),
            file=str(saved),
            recent=len(library.recent()),
        )
        window.close()
        report["ok"] = True
    except Exception:  # noqa: BLE001 - the report must say what broke
        report["error"] = traceback.format_exc()
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    return 0 if report["ok"] else 1
