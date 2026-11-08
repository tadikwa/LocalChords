"""Compare local transcription of sung lyrics: whisper.cpp and faster-whisper, several models.

Data: JamendoLyrics (https://github.com/f90/jamendolyrics), songs under Creative Commons licences,
with reference lyrics and word timings. Nothing of it is copied into the repository: point --data
at a local clone. Reports, per song and configuration: WER, word-start error against the
annotations, wall time, peak RAM. Run with a Python that has av and psutil (faster-whisper's venv):

  python scripts/bench_lyrics.py --data work/lyrics-bench/jl --engine work/lyrics-bench/engine/Release
      --models work/lyrics-bench/models --out work/lyrics-bench/results
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np
import psutil

SONGS = {
    "en": [
        "HILA_-_Give_Me_the_Same",
        "Avercage_-_Embers",
        "Color_Out_-_Falling_Star",
        "Lower_Loveday_-_Is_It_Right_",
        "Moon_I_Mean_-_Wrong_Concept",
        "Wordsmith_-_The_Statement",
    ],
    "fr": [
        "Capotes_à_un_Franc_-_elmanu",
        "de_bonne_humeur_-_Le_Nez_Tordu",
        "Le_musée_d'air_contemporain_-_KPTN",
        "Mère_nature_-_Law'",
        "Pluie_d'entre_deux_saisons_-_Midnight_Prefou",
        "POIGNEE_DE_MAIN_-_Cabbac",
    ],
}


def words_of(text: str) -> list[str]:
    """Lower case, no accents kept apart, apostrophes split ("l'abandon" -> "l", "abandon")."""
    text = unicodedata.normalize("NFC", text.lower()).replace("’", "'")
    return re.findall(r"[\w]+", text.replace("'", " "))


def align(ref: list[str], hyp: list[str]) -> tuple[int, list[tuple[int, int]]]:
    """Levenshtein distance and the matched (ref index, hyp index) pairs."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(
                d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1])
            )
    pairs, i, j = [], n, m
    while i and j:
        if d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] == hyp[j - 1]:
                pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif d[i, j] == d[i - 1, j] + 1:
            i -= 1
        else:
            j -= 1
    return int(d[n, m]), pairs[::-1]


def to_wav(mp3: Path, wav: Path) -> float:
    import av

    if not wav.exists():
        parts = []
        with av.open(str(mp3)) as c:
            r = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in c.decode(c.streams.audio[0]):
                parts += [o.to_ndarray().reshape(-1) for o in r.resample(frame)]
            parts += [o.to_ndarray().reshape(-1) for o in r.resample(None)]
        y = np.concatenate(parts).astype(np.int16)
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(y.tobytes())
    with wave.open(str(wav)) as w:
        return w.getnframes() / 16000


def run(cmd: list[str]) -> tuple[float, int, str]:
    """Wall time, peak resident memory of the process tree, stderr."""
    start = time.perf_counter()
    log = tempfile.TemporaryFile()  # a pipe nobody reads would fill and block the engine
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log)
    proc = psutil.Process(p.pid)
    peak = 0
    while p.poll() is None:
        try:
            rss = proc.memory_info().rss + sum(c.memory_info().rss for c in proc.children(True))
            peak = max(peak, rss)
        except psutil.Error:
            pass
        time.sleep(0.2)
    log.seek(0)
    err = log.read().decode("utf-8", "replace")
    if p.returncode:
        raise RuntimeError(err[-2000:])
    return time.perf_counter() - start, peak, err


def whisper_cpp(
    engine: Path,
    model: Path,
    wav: Path,
    lang: str,
    out: Path,
    vad: Path | None,
    threads: int,
    dtw: str | None,
    flags: set[str] = frozenset(),
):
    """flags: "fb" keeps the temperature fallback, "mc0" drops the previous text as context."""
    cmd = [
        str(engine / "whisper-cli.exe"),
        "-m",
        str(model),
        "-f",
        str(wav),
        "-l",
        lang,
        "-t",
        str(threads),
        "-ojf",
        "-of",
        str(out),
        "-np",
        "-sns",
    ]
    if "fb" not in flags:
        cmd.append("-nf")
    if "mc0" in flags:
        cmd += ["-mc", "0"]
    if vad:
        cmd += ["--vad", "-vm", str(vad)]
    if dtw:
        cmd += ["--dtw", dtw]
    seconds, peak, _ = run(cmd)
    data = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8", errors="replace"))
    segments = []
    for s in data["transcription"]:
        words, cur = [], None
        for t in s.get("tokens", []):
            text = t["text"]
            if text.startswith("[_") or not text.strip():
                if text.startswith(" ") and cur:
                    cur = None
                continue
            start = (
                t.get("t_dtw", -1) * 10 if dtw and t.get("t_dtw", -1) >= 0 else t["offsets"]["from"]
            ) / 1000
            if cur is None or text.startswith(" "):
                cur = {"w": text.strip(), "start": start}
                words.append(cur)
            else:
                cur["w"] += text
        segments.append(
            {
                "start": s["offsets"]["from"] / 1000,
                "end": s["offsets"]["to"] / 1000,
                "text": s["text"],
                "words": words,
            }
        )
    return seconds, peak, segments


FW = r"""
import json, sys
from faster_whisper import WhisperModel
model, wav, lang, threads, vad = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5] == "1"
m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
segs, info = m.transcribe(wav, language=lang, vad_filter=vad, word_timestamps=True, beam_size=5,
                          condition_on_previous_text=False)
out = [{"start": s.start, "end": s.end, "text": s.text,
        "words": [{"w": w.word.strip(), "start": w.start} for w in (s.words or [])]} for s in segs]
print(json.dumps(out))
"""


def faster_whisper(model: str, wav: Path, lang: str, threads: int, vad: bool):
    cmd = [sys.executable, "-c", FW, model, str(wav), lang, str(threads), "1" if vad else "0"]
    start = time.perf_counter()
    out, log = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=out, stderr=log)
    proc, peak = psutil.Process(p.pid), 0
    while p.poll() is None:
        try:
            peak = max(peak, proc.memory_info().rss)
        except psutil.Error:
            pass
        time.sleep(0.2)
    out.seek(0)
    log.seek(0)
    if p.returncode:
        raise RuntimeError(log.read().decode("utf-8", "replace")[-2000:])
    return time.perf_counter() - start, peak, json.loads(out.read())


def score(data: Path, song: str, segments: list[dict]) -> dict:
    ref_text = (data / "lyrics" / f"{song}.txt").read_text(encoding="utf-8")
    ref = words_of(ref_text)
    with (data / "annotations" / "words" / f"{song}.csv").open(encoding="utf-8") as f:
        starts = [float(r["word_start"]) for r in csv.DictReader(f)]
    words_file = (data / "lyrics" / f"{song}.words.txt").read_text(encoding="utf-8").split()
    hyp_words = []  # (normalized word, start)
    for s in segments:
        for w in s["words"]:
            for part in words_of(w["w"]):
                hyp_words.append((part, w["start"]))
    hyp_text = " ".join(s["text"] for s in segments)
    hyp = words_of(hyp_text)
    dist, _ = align(ref, hyp)
    # Timing: the annotated word list, aligned with the hypothesis words that carry a time.
    ann = []
    for w, t in zip(words_file, starts, strict=False):
        ann += [(p, t) for p in words_of(w)[:1]]
    _, pairs = align([a for a, _ in ann], [h for h, _ in hyp_words])
    errors = np.array([hyp_words[j][1] - ann[i][1] for i, j in pairs]) if pairs else np.zeros(0)
    # Line starts: each hypothesis segment's first matched word against the annotation.
    seg_err = []
    first = {}
    k = 0
    for si, s in enumerate(segments):
        for w in s["words"]:
            for _ in words_of(w["w"]):
                first.setdefault(si, k)
                k += 1
    matched = dict((j, i) for i, j in pairs)
    for si, j in first.items():
        if j in matched:
            seg_err.append(segments[si]["start"] - ann[matched[j]][1])
    seg_err = np.array(seg_err)
    return {
        "wer": dist / max(len(ref), 1),
        "ref_words": len(ref),
        "hyp_words": len(hyp),
        "word_median_abs": float(np.median(np.abs(errors))) if len(errors) else None,
        "word_within_0.5": float(np.mean(np.abs(errors) < 0.5)) if len(errors) else None,
        "seg_median_abs": float(np.median(np.abs(seg_err))) if len(seg_err) else None,
        "seg_within_1": float(np.mean(np.abs(seg_err) < 1.0)) if len(seg_err) else None,
        "segments": len(segments),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--configs", default="cpp:base,cpp:small-q5_1,cpp:large-v3-turbo-q5_0")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--songs", default="")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    wavs = args.out / "wav"
    wavs.mkdir(exist_ok=True)
    vad_model = args.models / "ggml-silero-v6.2.0.bin"
    results_file = args.out / "results.jsonl"
    done = set()
    if results_file.exists():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["config"], r["song"]))
    for config in args.configs.split(","):
        kind, name = config.split(":", 1)
        for lang, songs in SONGS.items():
            for song in songs:
                if args.songs and song not in args.songs.split(","):
                    continue
                if (config, song) in done:
                    continue
                duration = to_wav(args.data / "mp3" / f"{song}.mp3", wavs / f"{song}.wav")
                wav = wavs / f"{song}.wav"
                base, *opts = name.split("+")
                vad = "vad" in opts
                dtw = "large.v3.turbo" if "dtw" in opts else None
                if kind == "cpp":
                    out = args.out / "raw" / config.replace(":", "_").replace("+", "_") / song
                    out.parent.mkdir(parents=True, exist_ok=True)
                    seconds, peak, segments = whisper_cpp(
                        args.engine,
                        args.models / f"ggml-{base}.bin",
                        wav,
                        lang,
                        out,
                        vad_model if vad else None,
                        args.threads,
                        dtw,
                        set(opts),
                    )
                else:
                    seconds, peak, segments = faster_whisper(base, wav, lang, args.threads, vad)
                r = {
                    "config": config,
                    "song": song,
                    "lang": lang,
                    "duration": duration,
                    "seconds": seconds,
                    "rtf": seconds / duration,
                    "peak_mb": peak / 2**20,
                    **score(args.data, song, segments),
                }
                print(json.dumps(r), flush=True)
                with results_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
