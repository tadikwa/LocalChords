"""The entry point. The analysis worker is this same program started again: multiprocessing's
freeze_support catches that first, before anything heavy gets imported."""

from __future__ import annotations

import multiprocessing


def _data_location() -> str | None:
    """Portable mode, when its marker is there: Data next to the program, or, when that cannot be
    written, this PC's folder for this run. Returns the reason for falling back, if any."""
    import os

    from . import library

    portable = library.portable_dir()
    if portable is None or os.environ.get("LOCALCHORDS_DATA"):
        return None
    problem = library.unwritable(portable)
    library.use(library.classic_dir() if problem else portable)
    return problem


def main() -> int:
    import sys
    import traceback
    from pathlib import Path

    fallback = _data_location()

    if len(sys.argv) >= 4 and sys.argv[1] == "--self-test":
        from .selftest import run

        return run(Path(sys.argv[2]), Path(sys.argv[3]))

    if len(sys.argv) >= 4 and sys.argv[1] == "--self-test-pitch":
        from .selftest import run_pitch

        return run_pitch(Path(sys.argv[2]), Path(sys.argv[3]))

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
    if fallback is not None:
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "LocalChords — mode portable",
            f"Le dossier Data à côté du programme ne peut pas être écrit ({fallback}) : support en "
            "lecture seule, protégé ou plein.\n\nContinuer avec les données de ce PC "
            f"({library.classic_dir()}) pendant cette session ? Rien n'est copié ni supprimé.",
        )
        go = box.addButton("Continuer avec ce PC", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Quitter", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return 1
    elif library.free_mb(library.data_dir()) < library.LOW_SPACE_MB:
        QMessageBox.warning(
            None,
            "LocalChords",
            f"Il reste {library.free_mb(library.data_dir())} Mo sur le support de "
            f"{library.data_dir()}. Les analyses déjà faites s'ouvrent, mais une sauvegarde ou "
            "l'import d'un lien peut échouer faute de place.",
        )
    window = MainWindow()
    window.show()
    arguments = [a for a in sys.argv[1:] if not a.startswith("-")]
    if arguments:
        window.open_path(Path(arguments[0]))
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
