"""The dialogs: correcting a chord, the rhythm, the keyboard shortcuts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
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
from ..project import Project
from . import theme


class ChordEditor(QDialog):
    """Correct a chord: type it, or pick it. What is shown and typed includes the transposition, so
    the result goes back through `to_sounding` before it reaches the project."""

    def __init__(self, project: Project, first: int, last: int, parent=None):
        super().__init__(parent)
        self.project = project
        self.first, self.last = first, last
        self.setWindowTitle("Corriger l'accord")
        self.setMinimumWidth(560)
        self.shift = project.sounding_shift()
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
        self.input.setPlaceholderText("Am7, D/F#, Bb, N.C.…")
        self.input.setAccessibleName("Accord")
        self.input.setStyleSheet("font-size: 22px; font-weight: 600; padding: 8px 12px;")
        self.input.textChanged.connect(self._typed)
        label = QLabel("Accord")
        label.setObjectName("h2")
        root.addWidget(label)
        root.addWidget(self.input)
        self.message = QLabel(" ")
        self.message.setObjectName("caption")
        root.addWidget(self.message)

        # What the analysis also heard: usually the right answer is one of these.
        candidates = (segment.candidates if segment else [])[:6]
        if candidates:
            title = QLabel("Proposés par l'analyse")
            title.setObjectName("caption")
            root.addWidget(title)
            row = QHBoxLayout()
            for label_text in candidates:
                text = symbol(label_text, key=self.key_label, semitones=self.shift)
                b = QPushButton(text)
                b.clicked.connect(lambda _=False, t=text: self.input.setText(t))
                row.addWidget(b)
            row.addStretch()
            root.addLayout(row)

        title = QLabel("Note de base")
        title.setObjectName("caption")
        root.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.root_buttons = QButtonGroup(self)
        self.root_buttons.setExclusive(True)
        moved_key = transpose_key(self.key_label, self.shift)
        for pc in range(12):
            b = QPushButton(pretty_note(spell_root(pc, moved_key, project.view["accidentals"])))
            b.setCheckable(True)
            self.root_buttons.addButton(b, pc)
            grid.addWidget(b, 0, pc)
        self.root_buttons.idClicked.connect(self._pick_root)
        root.addLayout(grid)

        title = QLabel("Type")
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
        row.addWidget(QLabel("Basse"))
        self.bass = QComboBox()
        self.bass.setAccessibleName("Note de basse")
        self.bass.addItem("Fondamentale", None)
        for pc in range(12):
            name = spell_root(pc, moved_key, project.view["accidentals"])
            self.bass.addItem(pretty_note(name), pc)
        self.bass.currentIndexChanged.connect(self._pick_bass)
        row.addWidget(self.bass)
        none = QPushButton("Pas d'accord (N.C.)")
        none.clicked.connect(lambda: self.input.setText("N.C."))
        row.addStretch()
        row.addWidget(none)
        root.addLayout(row)

        # The chord's whole span, or just the beats that were selected.
        span_row = QHBoxLayout()
        span_row.addWidget(QLabel("Appliquer à"))
        selected = last - first + 1
        self.scope_selection = QRadioButton(
            f"la sélection ({selected} temps)" if selected > 1 else "ce temps seulement"
        )
        seg_beats = (segment.end_beat - segment.start_beat) if segment else selected
        self.scope_chord = QRadioButton(f"tout cet accord ({seg_beats} temps)")
        whole = segment is not None and (
            selected == 1 or (first, last + 1) == (segment.start_beat, segment.end_beat)
        )
        (self.scope_chord if whole else self.scope_selection).setChecked(True)
        span_row.addWidget(self.scope_selection)
        span_row.addWidget(self.scope_chord)
        span_row.addStretch()
        root.addLayout(span_row)

        buttons = QDialogButtonBox()
        self.apply_button = buttons.addButton("Appliquer", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_button.setObjectName("primary")
        cancel = buttons.addButton("Annuler", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setAutoDefault(False)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if segment:
            self.input.setText(
                symbol(segment.chord, segment.bass, key=self.key_label, semitones=self.shift)
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
                "Accord non reconnu. Exemples : C, Am, G7, Fmaj7, Dm7, Bm7b5, Dsus4, C/E, N.C."
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
            symbol(make(self.pc, self.quality), bass, key=shown_key, accidentals=accidentals)
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


class RhythmDialog(QDialog):
    """Correct what the rhythm analysis got wrong: every change shows at once in the grid."""

    changed = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Tempo et mesure")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)
        meter = project.meter()
        self.per_bar = QSpinBox()
        self.per_bar.setRange(2, 12)
        self.per_bar.setValue(int(meter["beats_per_bar"]))
        self.per_bar.setAccessibleName("Temps par mesure")
        self.per_bar.valueChanged.connect(self._meter_changed)
        form.addRow("Temps par mesure", self.per_bar)
        self.first = QSpinBox()
        self.first.setRange(1, 12)
        self.first.setValue(int(meter["first_downbeat"]) + 1)
        self.first.setAccessibleName("Premier temps de la première mesure")
        self.first.setToolTip("Le numéro du temps du morceau qui tombe sur le début d'une mesure.")
        self.first.valueChanged.connect(self._meter_changed)
        form.addRow("Première mesure au temps n°", self.first)

        tempo_row = QWidget()
        row = QHBoxLayout(tempo_row)
        row.setContentsMargins(0, 0, 0, 0)
        half = QPushButton("÷ 2")
        half.setToolTip("Le tempo détecté est deux fois trop rapide")
        half.clicked.connect(lambda: self._scale(0.5))
        double = QPushButton("× 2")
        double.setToolTip("Le tempo détecté est deux fois trop lent")
        double.clicked.connect(lambda: self._scale(2))
        normal = QPushButton("Détecté")
        normal.clicked.connect(lambda: self._scale(1))
        for b in (half, double, normal):
            b.setAutoDefault(False)
            row.addWidget(b)
        row.addStretch()
        form.addRow("Grille de temps", tempo_row)

        grid = project.edits["grid"] or {}
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(0, 300)
        self.bpm.setDecimals(1)
        self.bpm.setSpecialValueText("Automatique")
        self.bpm.setValue(float(grid.get("bpm") or 0))
        self.bpm.setSuffix(" BPM")
        self.bpm.setAccessibleName("Tempo imposé")
        self.bpm.setToolTip("Pose une grille régulière à ce tempo. 0 revient à la grille détectée.")
        self.bpm.editingFinished.connect(self._bpm_changed)
        form.addRow("Tempo imposé", self.bpm)

        self.offset = QSpinBox()
        self.offset.setRange(-2000, 2000)
        self.offset.setSingleStep(10)
        self.offset.setSuffix(" ms")
        self.offset.setValue(int(float(grid.get("offset") or 0) * 1000))
        self.offset.setAccessibleName("Décalage de la grille en millisecondes")
        self.offset.setToolTip("Décale tous les temps, si la grille tombe à côté de la musique.")
        self.offset.editingFinished.connect(self._offset_changed)
        form.addRow("Décalage", self.offset)

        note = QLabel(
            "Les corrections d'accords sont conservées : elles sont enregistrées en secondes, "
            "pas sur la grille."
        )
        note.setObjectName("caption")
        note.setWordWrap(True)
        form.addRow(note)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Fermer")
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
    ("Espace", "Lecture / pause"),
    ("← / →", "Temps précédent / suivant"),
    ("Ctrl + ← / →", "Mesure précédente / suivante"),
    ("Début / Fin", "Début / fin du morceau"),
    ("Entrée ou E", "Corriger l'accord sélectionné"),
    ("Maj + clic", "Étendre la sélection"),
    ("A / B", "Début / fin de boucle"),
    ("L", "Boucler la sélection, ou arrêter la boucle"),
    ("- / +", "Ralentir / accélérer"),
    ("Ctrl + ↑ / ↓", "Transposer d'un demi-ton"),
    ("Ctrl + Z / Y", "Annuler / rétablir"),
    ("Ctrl + O", "Ouvrir un morceau"),
    ("Ctrl + S", "Enregistrer une copie du projet"),
    ("Ctrl + E", "Exporter"),
    ("F1", "Cette aide"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raccourcis clavier")
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setHorizontalSpacing(24)
        layout.setVerticalSpacing(8)
        for i, (keys, what) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
            layout.addWidget(k, i, 0, Qt.AlignmentFlag.AlignRight)
            layout.addWidget(QLabel(what), i, 1)
