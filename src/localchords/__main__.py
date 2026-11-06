"""Start here, in development and in the packaged program alike."""

import multiprocessing

if __name__ == "__main__":
    # First of all: in the analysis worker this runs the job and exits before the interface loads.
    multiprocessing.freeze_support()
    from localchords.app import main

    raise SystemExit(main())
