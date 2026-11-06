"""Run the program's real download job on one URL and print what comes back."""

import sys
import time
from pathlib import Path

from localchords import audio, worker


def main():
    folder = Path("work/downloads3")
    folder.mkdir(parents=True, exist_ok=True)
    job = worker.start_download(sys.argv[1], folder)
    end = time.time() + 240
    messages = []
    while time.time() < end and not any(m[0] in ("downloaded", "error") for m in messages):
        messages += job.poll()
        time.sleep(0.1)
    job.cancel()
    last = messages[-1] if messages else None
    print(last)
    if last and last[0] == "downloaded":
        y = audio.decode(Path(last[1]), 22050, channels=1)
        print("decoded seconds:", round(len(y) / 22050, 1), audio.metadata(Path(last[1])))


if __name__ == "__main__":
    main()
