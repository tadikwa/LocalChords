"""The dialogs: correcting a chord, the rhythm, the keyboard shortcuts."""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..chords import (
    QUALITIES,
    SHARP_NAMES,
    make,
    name_to_pc,
    parse,
    parse_symbol,
    pretty_note,
    spell_root,
    symbol,
    transpose_key,
)
from ..i18n import translate
from ..project import Project


class ChordEditor(QDialog):
    """Correct a chord: type it, or pick it. What is shown and typed includes the transposition, so
    the result goes back through `to_sounding` before it reaches the project."""

    def __init__(self, project: Project, first: int, last: int, parent=None):
        super().__init__(parent)
        self.project = project
        self.first, self.last = first, last
        self.setWindowTitle(translate("Dialogs", "Corriger l'accord"))
        self.setMinimumWidth(560)
        self.shift = project.sounding_shift()
        self.latin = bool(project.view.get("latin"))
        key = project.key()
        self.key_label = key["label"] if key else None
        segment = project.segment_at_beat(first)
        self.segment = segment
        self.result_label: str | None = None
        self.result_bass: str | None = None
        self.result_span: tuple[int, int] = (first, last)
        self.pc = None
        self.quality = "maj"

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 18, 20, 18)

        self.input = QLineEdit()
        self.input.setPlaceholderText(translate("Dialogs", "Am7, D/F#, Bb, N.C.…"))
        self.input.setAccessibleName(translate("Dialogs", "Accord"))
        self.input.setObjectName("chordInput")
        self.input.textChanged.connect(self._typed)
        label = QLabel(translate("Dialogs", "Accord"))
        label.setObjectName("h2")
        root.addWidget(label)
        root.addWidget(self.input)
        self.message = QLabel(" ")
        self.message.setObjectName("caption")
        root.addWidget(self.message)

        # What the analysis also heard: usually the right answer is one of these.
        candidates = (segment.candidates if segment else [])[:6]
        if candidates:
            title = QLabel(translate("Dialogs", "Proposés par l'analyse"))
            title.setObjectName("caption")
            root.addWidget(title)
            row = QHBoxLayout()
            for label_text in candidates:
                text = symbol(
                    label_text, key=self.key_label, semitones=self.shift, latin=self.latin
                )
                b = QPushButton(text)
                b.clicked.connect(lambda _=False, t=text: self.input.setText(t))
                row.addWidget(b)
            row.addStretch()
            root.addLayout(row)

        title = QLabel(translate("Dialogs", "Note de base"))
        title.setObjectName("caption")
        root.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.root_buttons = QButtonGroup(self)
        self.root_buttons.setExclusive(True)
        moved_key = transpose_key(self.key_label, self.shift)
        for pc in range(12):
            b = QPushButton(
                pretty_note(
                    spell_root(pc, moved_key, project.view["accidentals"]), latin=self.latin
                )
            )
            b.setCheckable(True)
            self.root_buttons.addButton(b, pc)
            grid.addWidget(b, 0, pc)
        self.root_buttons.idClicked.connect(self._pick_root)
        root.addLayout(grid)

        title = QLabel(translate("Dialogs", "Type"))
        title.setObjectName("caption")
        root.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.quality_buttons = QButtonGroup(self)
        self.qualities = list(QUALITIES)
        for i, quality in enumerate(self.qualities):
            b = QPushButton(QUALITIES[quality][0] or "majeur")
            b.setCheckable(True)
            self.quality_buttons.addButton(b, i)
            grid.addWidget(b, i // 5, i % 5)
        self.quality_buttons.idClicked.connect(self._pick_quality)
        root.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Dialogs", "Basse")))
        self.bass = QComboBox()
        self.bass.setAccessibleName(translate("Dialogs", "Note de basse"))
        self.bass.addItem(translate("Dialogs", "Fondamentale"), None)
        for pc in range(12):
            name = spell_root(pc, moved_key, project.view["accidentals"])
            self.bass.addItem(pretty_note(name, latin=self.latin), pc)
        self.bass.currentIndexChanged.connect(self._pick_bass)
        row.addWidget(self.bass)
        none = QPushButton(translate("Dialogs", "Pas d'accord (N.C.)"))
        none.clicked.connect(lambda: self.input.setText("N.C."))
        row.addStretch()
        row.addWidget(none)
        root.addLayout(row)

        # The chord's whole span, or just the beats that were selected.
        span_row = QHBoxLayout()
        span_row.addWidget(QLabel(translate("Dialogs", "Appliquer à")))
        selected = last - first + 1
        self.scope_selection = QRadioButton(
            translate("Dialogs", "la sélection ({selected} temps)").format(selected=selected)
            if selected > 1
            else translate("Dialogs", "ce temps seulement")
        )
        seg_beats = (segment.end_beat - segment.start_beat) if segment else selected
        self.scope_chord = QRadioButton(
            translate("Dialogs", "tout cet accord ({seg_beats} temps)").format(seg_beats=seg_beats)
        )
        whole = segment is not None and (
            selected == 1 or (first, last + 1) == (segment.start_beat, segment.end_beat)
        )
        (self.scope_chord if whole else self.scope_selection).setChecked(True)
        span_row.addWidget(self.scope_selection)
        span_row.addWidget(self.scope_chord)
        span_row.addStretch()
        root.addLayout(span_row)

        buttons = QDialogButtonBox()
        self.apply_button = buttons.addButton(
            translate("Dialogs", "Appliquer"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.apply_button.setObjectName("primary")
        cancel = buttons.addButton(
            translate("Dialogs", "Annuler"), QDialogButtonBox.ButtonRole.RejectRole
        )
        cancel.setAutoDefault(False)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if segment:
            self.input.setText(
                symbol(
                    segment.chord,
                    segment.bass,
                    key=self.key_label,
                    semitones=self.shift,
                    latin=self.latin,
                )
            )
        self.input.selectAll()
        self.input.setFocus()

    def _parsed(self):
        return parse_symbol(self.input.text())

    def _typed(self, _text: str) -> None:
        parsed = self._parsed()
        self.apply_button.setEnabled(parsed is not None)
        if parsed is None:
            self.message.setText(
                translate(
                    "Dialogs",
                    "Accord non reconnu. Exemples : C, Am, G7, Fmaj7, Dm7, Bm7b5, Dsus4, C/E, N.C.",
                )
            )
            self.message.setObjectName("error")
        else:
            self.message.setText(" ")
            self.message.setObjectName("caption")
            label, bass = parsed
            info = parse(label)
            if info is not None:
                self.pc, self.quality = info
                self.root_buttons.button(info[0]).setChecked(True)
                self.quality_buttons.button(self.qualities.index(info[1])).setChecked(True)
            index = 0 if bass is None else name_to_pc(bass) + 1
            self.bass.blockSignals(True)
            self.bass.setCurrentIndex(index)
            self.bass.blockSignals(False)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def _write_input(self) -> None:
        if self.pc is None:
            return
        # The buttons name notes as shown, so this writes them back without moving them again.
        bass_pc = self.bass.currentData()
        bass = None if bass_pc is None else SHARP_NAMES[bass_pc]
        moved = transpose_key(self.key_label, self.shift)
        shown_key = f"{SHARP_NAMES[moved[0]]}:{moved[1]}" if moved else None
        accidentals = self.project.view["accidentals"]
        self.input.setText(
            symbol(
                make(self.pc, self.quality),
                bass,
                key=shown_key,
                accidentals=accidentals,
                latin=self.latin,
            )
        )

    def _pick_root(self, pc: int) -> None:
        self.pc = pc
        self._write_input()

    def _pick_quality(self, index: int) -> None:
        self.quality = self.qualities[index]
        if self.pc is None:
            self.pc = 0
            self.root_buttons.button(0).setChecked(True)
        self._write_input()

    def _pick_bass(self, _index: int) -> None:
        self._write_input()

    def _accept(self) -> None:
        parsed = self._parsed()
        if parsed is None:
            return
        label, bass = parsed
        info = parse(label)
        if info is not None:
            label = make(info[0] - self.shift, info[1])
        if bass is not None:
            bass = SHARP_NAMES[(name_to_pc(bass) - self.shift) % 12]
        self.result_label, self.result_bass = label, bass
        if self.scope_chord.isChecked() and self.segment:
            self.result_span = (self.segment.start_beat, self.segment.end_beat - 1)
        else:
            self.result_span = (self.first, self.last)
        self.accept()


class SheetDialog(QDialog):
    """What the printed chord sheet holds: which diagrams, and the grid or not."""

    MODES = (
        ("guitar", QT_TRANSLATE_NOOP("Dialogs", "Guitare")),
        ("piano", QT_TRANSLATE_NOOP("Dialogs", "Piano")),
        ("both", QT_TRANSLATE_NOOP("Dialogs", "Guitare et piano")),
    )

    def __init__(self, mode: str, grid: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Dialogs", "Fiche des accords"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(QLabel(translate("Dialogs", "Diagrammes à imprimer")))
        self.group = QButtonGroup(self)
        for value, text in self.MODES:
            button = QRadioButton(translate("Dialogs", text))
            button.setProperty("mode", value)
            button.setChecked(value == mode)
            self.group.addButton(button)
            layout.addWidget(button)
        if self.group.checkedButton() is None:
            self.group.buttons()[0].setChecked(True)
        self.grid = QCheckBox(translate("Dialogs", "Ajouter la grille sur une page à part"))
        self.grid.setChecked(grid)
        layout.addWidget(self.grid)
        note = QLabel(
            translate(
                "Dialogs",
                "Les positions sont celles choisies dans le programme, transposition et "
                "capodastre compris.",
            )
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            translate("Dialogs", "Exporter…")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            translate("Dialogs", "Annuler")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def mode(self) -> str:
        return self.group.checkedButton().property("mode")


class RhythmDialog(QDialog):
    """Correct what the rhythm analysis got wrong: every change shows at once in the grid."""

    changed = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle(translate("Dialogs", "Tempo et mesure"))
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)
        meter = project.meter()
        self.per_bar = QSpinBox()
        self.per_bar.setRange(2, 12)
        self.per_bar.setValue(int(meter["beats_per_bar"]))
        self.per_bar.setAccessibleName(translate("Dialogs", "Temps par mesure"))
        self.per_bar.valueChanged.connect(self._meter_changed)
        form.addRow(translate("Dialogs", "Temps par mesure"), self.per_bar)
        self.first = QSpinBox()
        self.first.setRange(1, 12)
        self.first.setValue(int(meter["first_downbeat"]) + 1)
        self.first.setAccessibleName(translate("Dialogs", "Premier temps de la première mesure"))
        self.first.setToolTip(
            translate(
                "Dialogs", "Le numéro du temps du morceau qui tombe sur le début d'une mesure."
            )
        )
        self.first.valueChanged.connect(self._meter_changed)
        form.addRow(translate("Dialogs", "Première mesure au temps n°"), self.first)

        tempo_row = QWidget()
        row = QHBoxLayout(tempo_row)
        row.setContentsMargins(0, 0, 0, 0)
        half = QPushButton("÷ 2")
        half.setToolTip(translate("Dialogs", "Le tempo détecté est deux fois trop rapide"))
        half.clicked.connect(lambda: self._scale(0.5))
        double = QPushButton("× 2")
        double.setToolTip(translate("Dialogs", "Le tempo détecté est deux fois trop lent"))
        double.clicked.connect(lambda: self._scale(2))
        normal = QPushButton(translate("Dialogs", "Détecté"))
        normal.clicked.connect(lambda: self._scale(1))
        for b in (half, double, normal):
            b.setAutoDefault(False)
            row.addWidget(b)
        row.addStretch()
        form.addRow(translate("Dialogs", "Grille de temps"), tempo_row)

        grid = project.edits["grid"] or {}
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(0, 300)
        self.bpm.setDecimals(1)
        self.bpm.setSpecialValueText(translate("Dialogs", "Automatique"))
        self.bpm.setValue(float(grid.get("bpm") or 0))
        self.bpm.setSuffix(" BPM")
        self.bpm.setAccessibleName(translate("Dialogs", "Tempo imposé"))
        self.bpm.setToolTip(
            translate(
                "Dialogs", "Pose une grille régulière à ce tempo. 0 revient à la grille détectée."
            )
        )
        self.bpm.editingFinished.connect(self._bpm_changed)
        form.addRow(translate("Dialogs", "Tempo imposé"), self.bpm)

        self.offset = QSpinBox()
        self.offset.setRange(-2000, 2000)
        self.offset.setSingleStep(10)
        self.offset.setSuffix(" ms")
        self.offset.setValue(int(float(grid.get("offset") or 0) * 1000))
        self.offset.setAccessibleName(
            translate("Dialogs", "Décalage de la grille en millisecondes")
        )
        self.offset.setToolTip(
            translate("Dialogs", "Décale tous les temps, si la grille tombe à côté de la musique.")
        )
        self.offset.editingFinished.connect(self._offset_changed)
        form.addRow(translate("Dialogs", "Décalage"), self.offset)

        note = QLabel(
            translate(
                "Dialogs",
                "Les corrections d'accords sont conservées : elles sont enregistrées en "
                "secondes, pas sur la grille.",
            )
        )
        note.setObjectName("caption")
        note.setWordWrap(True)
        form.addRow(note)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText(translate("Dialogs", "Fermer"))
        close.rejected.connect(self.reject)
        form.addRow(close)

    def _meter_changed(self) -> None:
        self.project.set_meter(self.per_bar.value(), self.first.value() - 1)
        self.changed.emit()

    def _scale(self, factor) -> None:
        self.project.set_grid(scale=factor)
        self.changed.emit()

    def _bpm_changed(self) -> None:
        value = self.bpm.value()
        current = (self.project.edits["grid"] or {}).get("bpm") or 0
        if value != current:
            self.project.set_grid(bpm=value)
            self.changed.emit()

    def _offset_changed(self) -> None:
        value = self.offset.value() / 1000
        current = (self.project.edits["grid"] or {}).get("offset") or 0
        if value != current:
            self.project.set_grid(offset=value)
            self.changed.emit()


SHORTCUTS = [
    (QT_TRANSLATE_NOOP("Shortcuts", "Espace"), QT_TRANSLATE_NOOP("Shortcuts", "Lecture / pause")),
    ("← / →", QT_TRANSLATE_NOOP("Shortcuts", "Temps précédent / suivant")),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + ← / →"),
        QT_TRANSLATE_NOOP("Shortcuts", "Mesure précédente / suivante"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Début / Fin"),
        QT_TRANSLATE_NOOP("Shortcuts", "Début / fin du morceau"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Entrée ou E"),
        QT_TRANSLATE_NOOP("Shortcuts", "Corriger l'accord sélectionné"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Maj + clic"),
        QT_TRANSLATE_NOOP("Shortcuts", "Étendre la sélection"),
    ),
    ("A / B", QT_TRANSLATE_NOOP("Shortcuts", "Début / fin de boucle")),
    ("L", QT_TRANSLATE_NOOP("Shortcuts", "Boucler la sélection, ou arrêter la boucle")),
    ("- / +", QT_TRANSLATE_NOOP("Shortcuts", "Ralentir / accélérer")),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + ↑ / ↓"),
        QT_TRANSLATE_NOOP("Shortcuts", "Transposer d'un demi-ton"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + Z / Y"),
        QT_TRANSLATE_NOOP("Shortcuts", "Annuler / rétablir"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + O"),
        QT_TRANSLATE_NOOP("Shortcuts", "Ouvrir un morceau"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + S"),
        QT_TRANSLATE_NOOP("Shortcuts", "Enregistrer une copie du projet"),
    ),
    (QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + E"), QT_TRANSLATE_NOOP("Shortcuts", "Exporter")),
    ("D", QT_TRANSLATE_NOOP("Shortcuts", "Afficher / masquer les diagrammes")),
    ("T", QT_TRANSLATE_NOOP("Shortcuts", "Afficher / masquer les accords du morceau")),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "G / Maj + G"),
        QT_TRANSLATE_NOOP("Shortcuts", "Position de guitare suivante / précédente"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "P / Maj + P"),
        QT_TRANSLATE_NOOP("Shortcuts", "Disposition de piano suivante / précédente"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Clic sur un accord, Maj + D"),
        QT_TRANSLATE_NOOP("Shortcuts", "Épingler ses diagrammes (← → le déplacent)"),
    ),
    ("K", QT_TRANSLATE_NOOP("Shortcuts", "Paroles : afficher / revenir à la grille seule")),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Entrée (synchronisation)"),
        QT_TRANSLATE_NOOP("Shortcuts", "Paroles : caler la ligne choisie sur la lecture"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Ctrl + molette"),
        QT_TRANSLATE_NOOP("Shortcuts", "Paroles : taille du texte"),
    ),
    ("M", QT_TRANSLATE_NOOP("Shortcuts", "Mixage : ouvrir / fermer le panneau")),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Maj + M"),
        QT_TRANSLATE_NOOP("Shortcuts", "Mixage : basculer entre l'original et le mix personnalisé"),
    ),
    (
        QT_TRANSLATE_NOOP("Shortcuts", "Échap"),
        QT_TRANSLATE_NOOP("Shortcuts", "Diagrammes : revenir à l'accord joué"),
    ),
    ("F1", QT_TRANSLATE_NOOP("Shortcuts", "Cette aide")),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Dialogs", "Raccourcis clavier"))
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setHorizontalSpacing(24)
        layout.setVerticalSpacing(8)
        for i, (keys, what) in enumerate(SHORTCUTS):
            keys, what = translate("Shortcuts", keys), translate("Shortcuts", what)
            k = QLabel(keys)
            k.setObjectName("key")
            layout.addWidget(k, i, 0, Qt.AlignmentFlag.AlignRight)
            layout.addWidget(QLabel(what), i, 1)
