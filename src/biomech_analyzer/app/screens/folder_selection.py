"""Screen 1 — participant folder selection and file validation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer.app.state import AppState
from biomech_analyzer.core.constants import Modality
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.io.folder_scanner import scan_participant_folder


class FolderSelectionScreen(QWidget):
    """Anonymous ID + folder picker + validation result tree."""

    validated = Signal()  # emitted after a successful validation

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

        layout = QVBoxLayout(self)

        form_box = QGroupBox("Participant input")
        form = QFormLayout(form_box)
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g. P001 (defaults to folder name)")
        form.addRow("Anonymous participant ID:", self.id_edit)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Path to the participant folder")
        browse_btn = QPushButton("Select Folder…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse_btn)
        form.addRow("Input folder:", folder_row)

        baseline_row = QHBoxLayout()
        self.baseline_edit = QLineEdit()
        self.baseline_edit.setPlaceholderText("Optional normative baseline CSV/XLSX")
        baseline_btn = QPushButton("Browse…")
        baseline_btn.clicked.connect(self._browse_baseline)
        baseline_row.addWidget(self.baseline_edit)
        baseline_row.addWidget(baseline_btn)
        form.addRow("Baseline file:", baseline_row)
        layout.addWidget(form_box)

        self.validate_btn = QPushButton("Validate Files")
        self.validate_btn.clicked.connect(self._validate)
        layout.addWidget(self.validate_btn)

        layout.addWidget(QLabel("Detected trial packages:"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Trial / file", "Status"])
        self.tree.setColumnWidth(0, 380)
        layout.addWidget(self.tree, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

    # ------------------------------------------------------------------ slots

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select participant folder")
        if path:
            self.folder_edit.setText(path)

    def _browse_baseline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select baseline dataset", "", "Baseline files (*.csv *.xlsx *.xls)"
        )
        if path:
            self.baseline_edit.setText(path)

    def _validate(self) -> None:
        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            QMessageBox.warning(self, "Validation", "Please select a participant folder first.")
            return
        try:
            report = scan_participant_folder(
                Path(folder_text), self.id_edit.text().strip() or None
            )
        except BiomechError as exc:
            QMessageBox.critical(self, "Validation failed", exc.user_message)
            return

        self.state.folder = Path(folder_text)
        self.state.participant_id = report.participant_id
        self.state.validation = report
        baseline_text = self.baseline_edit.text().strip()
        self.state.baseline_path = Path(baseline_text) if baseline_text else None

        self.tree.clear()
        for pkg in sorted(report.trials, key=lambda p: p.trial_id):
            top = QTreeWidgetItem(
                [pkg.trial_id, "complete" if pkg.is_complete else "incomplete"]
            )
            for modality in Modality:
                tf = pkg.files.get(modality)
                child = QTreeWidgetItem(
                    [
                        f"{modality.value}: {tf.path.name if tf else '—'}",
                        "OK" if tf else "MISSING",
                    ]
                )
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(not pkg.is_complete)
        if report.unmatched_files:
            top = QTreeWidgetItem(["Unassigned files", f"{len(report.unmatched_files)}"])
            for p in report.unmatched_files:
                top.addChild(QTreeWidgetItem([p.name, "not matched to a trial"]))
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)

        n_complete = len(report.complete_trials)
        parts = [f"{len(report.trials)} trial(s) found, {n_complete} complete."]
        if report.errors:
            parts.append("ERRORS: " + " ".join(report.errors))
        if report.warnings:
            parts.append(f"{len(report.warnings)} warning(s) — see Analysis Dashboard.")
        self.summary_label.setText(" ".join(parts))

        if report.errors:
            QMessageBox.critical(self, "Validation", "\n".join(report.errors))
        else:
            self.validated.emit()
