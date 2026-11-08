"""`LocalChords.exe --self-test <audio> <report folder>`: the whole scenario, inside the packaged
program, for the proof that the build works: open, analyze, play, correct, transpose, save, export,
reopen. Writes report.json, silently: playback goes through the real device at zero volume."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path


def run(audio_path: Path, out: Path) -> int:
    import os

    from . import library, lyrics, transcribe
    from .ui.main_window import MainWindow, app_instance
    from .ui.pdf import write_chord_sheet, write_lyrics_sheet, write_pdf

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
        step(
            "démarrage",
            True,
            seconds=round(time.perf_counter() - started, 2),
            data=str(library.data_dir()),
        )
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

        panel = window.song.panel
        mode, state = panel.mode, panel.state
        panel.set_state("full")
        panel.set_mode("both")
        window.seek(0)
        window.toggle_play()
        started = time.monotonic()
        beat_before = window.song.grid.current
        frames = out / "frames" if os.environ.get("LOCALCHORDS_SELFTEST_FRAMES") else None
        if frames:  # for the README animation: the real window, while it plays
            frames.mkdir(exist_ok=True)
            for i in range(90):
                wait(lambda: False, 0.1)
                window.grab().save(str(frames / f"{i:03}.png"))
        else:
            wait(lambda: False, 3.0)
        position, elapsed = window.player.position, time.monotonic() - started
        step(
            "lecture",
            window.player.playing and position > 2.0 and abs(position - elapsed) < 1.0,
            position=round(position, 3),
            device=window.player.stream is not None,
            latency=window.player.latency,
            highlight=(beat_before, window.song.grid.current),
        )
        expected = project.beat_at(window.player.position)
        step("synchronisation", abs(window.song.grid.current - expected) <= 1)
        step(
            "diagrammes pendant la lecture",
            panel.isVisible() and panel.title.text() == window.song.now.text(),
            chord=panel.title.text(),
            guitar=[f.text for f in panel.guitar_positions],
            piano=[list(v.notes) for v in panel.piano_voicings][:2],
        )
        times = []
        for beat in range(len(project.grid())):
            started = time.perf_counter()
            window._update_now(beat)
            panel.guitar.diagram.grab()
            panel.piano.diagram.grab()
            times.append(time.perf_counter() - started)
        step(
            "diagrammes : rapidité",
            max(times) < 0.05,
            mean_ms=round(1000 * sum(times) / len(times), 2),
            max_ms=round(1000 * max(times), 2),
        )
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
        window.seek(project.grid()[first.start_beat])
        app.processEvents()
        step(
            "diagrammes transposés",
            panel.title.text() == window.song.now.text()
            and bool(panel.guitar_positions)
            and {n % 12 for n in panel.piano_voicings[0].notes} == {6, 9, 1, 4},
            chord=panel.title.text(),
            guitar=panel.guitar_positions[0].text if panel.guitar_positions else None,
        )
        for name, shown in (("4_guitare", "guitar"), ("5_piano", "piano"), ("6_les_deux", "both")):
            panel.set_mode(shown)
            wait(lambda: False, 0.3)
            window.grab().save(str(out / f"{name}.png"))
        panel.set_mode(mode)
        panel.set_state(state)
        before = [s.chord for s in project.segments()]

        window.export_to(out / "grille.txt", "txt")
        window.export_to(out / "grille.cho", "cho")
        write_pdf(project, out / "grille.pdf")
        sizes = {p.name: p.stat().st_size for p in out.glob("grille.*")}
        step("export", len(sizes) == 3 and all(sizes.values()), sizes=sizes)

        chords = window.song.chords
        chords.set_state("compact")
        chords.set_view("all")
        cards = chords.cards()
        at = window.player.position
        if cards:
            cards[-1].chosen.emit()
            app.processEvents()
        step(
            "accords du morceau",
            len(cards) == len(chords.all_items) > 0
            and window.player.position == at
            and panel.title.text() == cards[-1].item.shown.shape.title,
            count=len(cards),
            chords=[c.item.shown.shape.title for c in cards],
        )
        chords.set_mode("both")
        wait(lambda: False, 0.3)
        window.grab().save(str(out / "7_accords_du_morceau.png"))
        pages = write_chord_sheet(
            project, out / "fiche.pdf", chords.all_items, "both", True, window.song.positions
        )
        data = (out / "fiche.pdf").read_bytes()
        step(
            "fiche des accords",
            data.startswith(b"%PDF") and data.count(b"/Type /Page\n") == pages >= 2,
            pages=pages,
            size=len(data),
        )

        # Made-up lyrics, never a real song's: the sheet, its PDF and the bundled engine.
        made_up = "[00:01.00]Une ligne pour essayer\n[00:05.00]Puis une autre pour finir\n"
        source = {"kind": "user", "name": "", "exportable": True}
        project.set_lyrics(lyrics.new(lyrics.parse(made_up), source))
        window._content_changed()
        window.lyrics.set_mode("sheet")
        wait(lambda: False, 0.3)
        window.grab().save(str(out / "8_paroles_et_accords.png"))
        lyric_pages = write_lyrics_sheet(
            project, out / "paroles.pdf", {}, chords.all_items, window.song.positions
        )
        step(
            "paroles et accords",
            sum(1 for r in window.lyrics.rows if r["kind"] == "line") == 2
            and any(r["chords"] for r in window.lyrics.rows)
            and (out / "paroles.pdf").read_bytes().startswith(b"%PDF")
            and lyric_pages >= 1,
            pages=lyric_pages,
            engine=transcribe.engine_ready(),
            models=transcribe.installed_models(),
        )
        window.lyrics.set_mode("grid")
        project.set_lyrics(None)
        window._content_changed()

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


def run_pitch(audio_path: Path, out: Path) -> int:
    """Play scripts/measure_pitch.py's reference through the real window and the speakers, at a
    low volume, under each transposition, speed and loop; the recorder outside judges the sound.
    Writes schedule.json: when each condition played, by the wall clock both sides share."""
    from .ui.main_window import SPEEDS, MainWindow, app_instance

    out.mkdir(parents=True, exist_ok=True)
    app = app_instance()
    window = MainWindow()
    window.show()
    window.open_path(audio_path)
    s = window.song
    schedule: dict = {"audio": str(audio_path), "conditions": []}

    def wait(seconds, condition=lambda: False):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end and not condition():
            app.processEvents()
            time.sleep(0.003)
        return condition()

    def play(name, seconds, semitones, audio, rate, region, start=None, loop=None, **extra):
        s.transpose.step(semitones - s.transpose.value)
        if s.audio_button.isChecked() != audio:
            s.audio_button.click()
        s.speed.step(SPEEDS.index(rate) - s.speed.value)
        if loop:
            window._set_loop(loop)
        if start is not None:
            window.seek(start)
        if not window.player.playing:
            window.toggle_play()
        t0, p0 = time.time(), window.player.position
        wait(seconds)
        schedule["conditions"].append(
            dict(
                name=name,
                semitones=semitones,
                audio=audio,
                rate=rate,
                region=region,
                t0=t0,
                t1=time.time(),
                position=(p0, window.player.position),
                **extra,
            )
        )
        (out / "schedule.json").write_text(json.dumps(schedule, indent=1), "utf-8")

    try:
        if not wait(60, lambda: window.audio_ready):
            raise AssertionError("audio not loaded")
        s.volume.setValue(15)
        play("son d'origine, grille +5", 3, 5, False, 1.0, "sine", start=0.5)
        for n in (0, 1, -1, 5, -5, 12, -12):
            play(f"{n:+d}", 3, n, True, 1.0, "sine", start=0.5)
        play("+12 à 50 %", 3.5, 12, True, 0.5, "sine", start=1)
        play("-12 à 150 %", 3, -12, True, 1.5, "sine", start=1)
        play("+5 à 75 %", 3, 5, True, 0.75, "sine", start=1)
        play("échelle +12", 4, 12, True, 1.0, "ladder", start=20.0)
        play("échelle -12", 4, -12, True, 1.0, "ladder", start=20.0)
        play("échelle +5 à 75 %", 5, 5, True, 0.75, "ladder", start=20.0)
        play("échelle -5 à 50 %", 6, -5, True, 0.5, "ladder", start=20.0)
        play("échelle +1 à 150 %", 4, 1, True, 1.5, "ladder", start=20.0)
        cycle = dict(expect_notes=[4, 5, 6, 7])
        play("boucle A/B +5 à 75 %", 8, 5, True, 0.75, "ladder", 22.0, (22.0, 24.0), **cycle)
        play("boucle, passage à -12", 6, -12, True, 0.75, "ladder", **cycle)
        play("boucle, son d'origine", 5, -12, False, 0.75, "ladder", **cycle)
        play(
            "boucle +12 à 100 %",
            5,
            12,
            True,
            1.0,
            "ladder",
            26.0,
            (26.0, 27.5),
            expect_notes=[0, 1, 2],
        )
        window.toggle_play()
        schedule["ok"] = True
    except Exception:  # noqa: BLE001 - the schedule must say what broke
        schedule["error"] = traceback.format_exc()
    (out / "schedule.json").write_text(json.dumps(schedule, indent=1), "utf-8")
    window._stop_job()
    window.close()
    return 0 if schedule.get("ok") else 1


def run_link(url: str, out: Path) -> int:
    """The link import, in the packaged program: its job, then the decoder on what came back."""
    from . import audio, worker

    out.mkdir(parents=True, exist_ok=True)
    job = worker.start_download(url, out)
    end = time.perf_counter() + 300
    messages: list[tuple] = []
    while time.perf_counter() < end and not any(m[0] in worker.FINAL for m in messages):
        messages += job.poll()
        time.sleep(0.1)
    job.cancel()
    final = messages[-1] if messages else ("error", "rien reçu", "")
    report = {"url": url, "final": final[:2]}
    if final[0] == "downloaded":
        report["seconds"] = round(len(audio.decode(Path(final[1]), 22050, channels=1)) / 22050, 1)
    (out / "link_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    return 0 if final[0] == "downloaded" else 1
