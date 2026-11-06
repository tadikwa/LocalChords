"""Time and peak memory of one analysis, in a fresh process like the program's worker.

Usage: bench_speed.py <audio> <engine>   Prints one JSON line. Run from the repository root.
"""

import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
from pathlib import Path


class Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]  # fmt: skip


def peak_gb() -> float:
    c = Counters()
    c.cb = ctypes.sizeof(c)
    kernel = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(Counters), wt.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return round(c.PeakWorkingSetSize / 2**30, 2)


def main():
    start = time.perf_counter()
    from localchords import audio, engines

    path, engine = Path(sys.argv[1]), sys.argv[2]
    y = audio.decode(path, engines.ANALYSIS_SR, channels=1)[:, 0]
    decoded = time.perf_counter() - start
    marks = {}
    result = engines.analyze(
        y, engine, lambda f, t: marks.setdefault(t, round(time.perf_counter() - start, 1))
    )
    total = time.perf_counter() - start
    duration = len(y) / engines.ANALYSIS_SR
    print(
        json.dumps(
            {
                "file": path.name,
                "engine": engine,
                "audio_min": round(duration / 60, 2),
                "total_s": round(total, 1),
                "decode_s": round(decoded, 1),
                "s_per_min": round(total / (duration / 60), 1),
                "peak_gb": peak_gb(),
                "segments": len(result["segments"]),
                "marks": marks,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
