"""chordotomy's own scorer on GuitarSet (CC BY 4.0), with LocalChords' grid in the analysis path.

A check that the tempo-following threshold, chosen on Tiny AAM, holds on music it never saw.
Downloads 696 MB on first use. Usage: bench_guitarset.py <limit> <threshold>
"""

import sys

from chordotomy import evaluate, timeline
from localchords import engines


def main():
    limit = int(sys.argv[1])
    engines.FOLLOW_TEMPO_BELOW = float(sys.argv[2])
    engines._configure_weights()
    original = timeline.analyze

    def analyze(path, key=None, engine="dsp", *, source_url=None, cache=None):
        return original(
            path, key, engine, source_url=source_url, cache=engines._Stages(lambda f, t: None)
        )

    timeline.analyze = analyze
    rows = evaluate.evaluate("guitarset", limit=limit, engine="model")
    print(evaluate.format_table(rows) if hasattr(evaluate, "format_table") else rows)


if __name__ == "__main__":
    main()
