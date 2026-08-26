"""Screen 3 — results overview and PDF report generation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer import DISCLAIMER
from biomech_analyzer.app.state import AppState
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.reporting import plots


def _fill_table(table: QTableWidget, headers: list[str], rows: list[list[str]]) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            item = QTableWidgetItem(cell)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()


class ResultsReportScreen(QWidget):
    """Trial summary, features, risk indicators, plot preview, report export."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._plot_dir = Path(tempfile.mkdtemp(prefix="biomech_gui_plots_"))

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.summary_table = QTableWidget()
        self.tabs.addTab(self.summary_table, "Trial summary")

        self.features_table = QTableWidget()
        self.tabs.addTab(self.features_table, "Features")

        self.risk_table = QTableWidget()
        self.tabs.addTab(self.risk_table, "Risk indicators")

        self.plot_label = QLabel("Select a trial row in 'Trial summary' to preview its plot.")
        self.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidget(self.plot_label)
        scroll.setWidgetResizable(True)
        self.tabs.addTab(scroll, "Feature plots")

        layout.addWidget(self.tabs, stretch=1)
        self.summary_table.itemSelectionChanged.connect(self._preview_plot)

        actions = QHBoxLayout()
        self.save_db_check = QCheckBox("Also save results to local SQLite database")
        actions.addWidget(self.save_db_check)
        actions.addStretch(1)
        self.report_btn = QPushButton("Generate PDF Report")
        self.report_btn.clicked.connect(self._generate_report)
        actions.addWidget(self.report_btn)
        layout.addLayout(actions)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #8a5a00; font-size: 10px;")
        layout.addWidget(disclaimer)

    # ------------------------------------------------------------------ data

    def refresh(self) -> None:
        result = self.state.result
        if result is None:
            return
        summary_rows = []
        feature_rows = []
        risk_rows = []
        for trial in result.trials:
            triggered = [r for r in trial.risk_indicators if r.triggered]
            summary_rows.append(
                [
                    trial.trial_id,
                    str(len(trial.features.features)),
                    str(len(triggered)),
                    trial.sync.strategy if trial.sync else "-",
                    str(len(trial.warnings)),
                ]
            )
            for fv in trial.features.features.values():
                comparison = next(
                    (c for c in trial.baseline_comparisons if c.feature == fv.name), None
                )
                z = (
                    f"{comparison.z_score:+.2f}"
                    if comparison and comparison.z_score is not None
                    else "-"
                )
                feature_rows.append(
                    [trial.trial_id, fv.name, f"{fv.value:.4g}", fv.unit, z,
                     fv.validation_status]
                )
            for r in triggered:
                risk_rows.append(
                    [trial.trial_id, r.name, r.feature, f"{r.observed_value:.4g}"
                     if r.observed_value is not None else "-",
                     r.reference, r.risk_level.value]
                )
        _fill_table(
            self.summary_table,
            ["Trial", "Features", "Triggered indicators", "Sync", "Warnings"],
            summary_rows,
        )
        _fill_table(
            self.features_table,
            ["Trial", "Feature", "Value", "Unit", "z-score", "Validation"],
            feature_rows,
        )
        _fill_table(
            self.risk_table,
            ["Trial", "Indicator", "Feature", "Observed", "Reference", "Level"],
            risk_rows if risk_rows else [["—", "No indicator triggered", "", "", "", ""]],
        )

    def _preview_plot(self) -> None:
        result = self.state.result
        if result is None:
            return
        row = self.summary_table.currentRow()
        if row < 0 or row >= len(result.trials):
            return
        trial = result.trials[row]
        if trial.data is None:
            return
        path = plots.plot_fz_with_events(trial.data, trial, self._plot_dir)
        if path is not None:
            self.plot_label.setPixmap(QPixmap(str(path)))
            self.tabs.setCurrentIndex(3)

    # ---------------------------------------------------------------- report

    def _generate_report(self) -> None:
        result = self.state.result
        if result is None:
            QMessageBox.warning(self, "Report", "Run an analysis first.")
            return
        from biomech_analyzer.reporting.pdf_report import generate_pdf_report

        try:
            if self.state.model_path is not None:
                from biomech_analyzer.ml.inference import predict_participant

                result.ml_output = predict_participant(result, self.state.model_path)
            out_dir = Path(self.state.config.get("report.output_dir", "output/reports"))
            include_plots = bool(self.state.config.get("report.include_plots", True))
            report_path = generate_pdf_report(result, out_dir, include_plots=include_plots)
            result.report_path = report_path
            if self.save_db_check.isChecked():
                from biomech_analyzer.storage.sqlite_repository import SqliteRepository

                db_path = Path(
                    self.state.config.get("storage.sqlite_path", "output/results.sqlite3")
                )
                with SqliteRepository(db_path) as repo:
                    repo.save_participant_result(result)
        except BiomechError as exc:
            QMessageBox.critical(self, "Report failed", exc.user_message)
            return
        answer = QMessageBox.question(
            self,
            "Report generated",
            f"PDF report written to:\n{report_path}\n\nOpen it now?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_path)))
