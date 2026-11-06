"""The real analysis worker, again and again in new processes: does it ever die?

Usage: soak_worker.py <audio> <runs>   The interface's process has Qt loaded, as in the program.
"""

import sys
import time
from pathlib import Path

from localchords import worker
from PySide6.QtWidgets import QApplication


def main():
    QApplication([])
    path, runs = Path(sys.argv[1]), int(sys.argv[2])
    ok = 0
    for run in range(runs):
        job = worker.start(path, "model")
        start = time.perf_counter()
        final = None
        while final is None and time.perf_counter() - start < 300:
            for message in job.poll():
                if message[0] in worker.FINAL:
                    final = message
            time.sleep(0.05)
        job.process.join(10)
        code = job.process.exitcode
        job.cancel()
        good = bool(final) and final[0] == "done" and code == 0
        ok += good
        print(run + 1, final[0] if final else "timeout", "exit", code, f"{time.perf_counter() - start:.1f}s", flush=True)
        if not good and final:
            print(str(final[1:])[:300], flush=True)
    print(f"{ok}/{runs} clean")


if __name__ == "__main__":
    main()
