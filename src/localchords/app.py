"""The entry point. The analysis worker is this same program started again: multiprocessing's
freeze_support catches that first, before anything heavy gets imported."""

from __future__ import annotations

import multiprocessing


def main() -> int:
    import sys
    import traceback
    from pathlib import Path

    if len(sys.argv) >= 4 and sys.argv[1] == "--self-test":
        from .selftest import run

        return run(Path(sys.argv[2]), Path(sys.argv[3]))

    if len(sys.argv) >= 4 and sys.argv[1] == "--self-test-link":
        from .selftest import run_link

        return run_link(sys.argv[2], Path(sys.argv[3]))

    from PySide6.QtWidgets import QMessageBox

    from . import library
    from .ui.main_window import MainWindow, app_instance

    app = app_instance()

    def report(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            with (library.data_dir() / "log.txt").open("a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        QMessageBox.critical(
            None,
            "LocalChords",
            f"Une erreur inattendue est survenue :\n{value}\n\n"
            f"Détails dans {library.data_dir() / 'log.txt'}",
        )

    sys.excepthook = report
    window = MainWindow()
    window.show()
    arguments = [a for a in sys.argv[1:] if not a.startswith("-")]
    if arguments:
        window.open_path(Path(arguments[0]))
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
