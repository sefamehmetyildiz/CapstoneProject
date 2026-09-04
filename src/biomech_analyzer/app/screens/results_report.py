"""Screen 3 — results overview and PDF report generation.

Shows the colour-coded overall risk level, per-trial summaries, features
with z-scores, triggered risk indicators (risk-coloured rows) and a plot
preview; generates the PDF report in English or Turkish and updates the
auto-saved database record with the report path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
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
from biomech_analyzer.core.constants import RISK_BG_COLORS, RISK_COLORS, RiskLevel
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.reporting import plots


def _fill_table(
    table: QTableWidget,
    headers: list[str],
    rows: list[list[str]],
    risk_col: int | None = None,
    risk_levels: list[RiskLevel] | None = None,
) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    table.setAlternatingRowColors(True)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            item = QTableWidgetItem(cell)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if risk_col is not None and risk_levels is not None and c == risk_col:
                level = risk_levels[r]
                item.setForeground(QColor(RISK_COLORS[level]))
                item.setBackground(QColor(RISK_BG_COLORS[level]))
            table.setItem(r, c, item)
    table.resizeColumnsToContents()


class ResultsReportScreen(QWidget):
    """Risk overview, feature tables, plot preview, bilingual report export."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._plot_dir = Path(tempfile.mkdtemp(prefix="biomech_gui_plots_"))

        layout = QVBoxLayout(self)

        self.risk_badge = QLabel("Overall risk: —")
        self.risk_badge.setProperty("riskBadge", True)
        self.risk_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.risk_badge)

        self.tabs = QTabWidget()
        self.summary_table = QTableWidget()
        self.tabs.addTab(self.summary_table, "Trial summary")
        self.features_table = QTableWidget()
        self.tabs.addTab(self.features_table, "Features")
        self.risk_table = QTableWidget()
        self.tabs.addTab(self.risk_table, "Risk indicators")
        self.profile_table = QTableWidget()
        self.tabs.addTab(self.profile_table, "Literature profiles")

        self.plot_label = QLabel("Select a trial row in 'Trial summary' to preview its plot.")
        self.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidget(self.plot_label)
        scroll.setWidgetResizable(True)
        self.tabs.addTab(scroll, "Feature plots")

        layout.addWidget(self.tabs, stretch=1)
        self.summary_table.itemSelectionChanged.connect(self._preview_plot)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Report language / Rapor dili:"))
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Türkçe", "tr")
        actions.addWidget(self.language_combo)
        actions.addStretch(1)
        self.report_btn = QPushButton("Generate PDF Report")
        self.report_btn.setProperty("primary", True)
        self.report_btn.clicked.connect(self._generate_report)
        actions.addWidget(self.report_btn)
        layout.addLayout(actions)

        note = QLabel(
            "Results are saved to the local database automatically; past "
            "analyses and reports are available on the History tab. " + DISCLAIMER
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a5a00; font-size: 9px;")
        layout.addWidget(note)

    # ------------------------------------------------------------------ data

    def refresh(self) -> None:
        result = self.state.result
        if result is None:
            return
        level = result.overall_risk
        self.risk_badge.setText(f"Overall biomechanical risk level: {level.value}")
        self.risk_badge.setStyleSheet(
            f"QLabel {{ background: {RISK_BG_COLORS[level]}; "
            f"color: {RISK_COLORS[level]}; border: 1px solid {RISK_COLORS[level]}; "
            "font-weight: 700; padding: 8px; border-radius: 5px; font-size: 12pt; }}"
        )

        summary_rows, summary_levels = [], []
        feature_rows = []
        risk_rows, risk_levels = [], []
        profile_rows, profile_levels = [], []
        for trial in result.trials:
            triggered = [r for r in trial.risk_indicators if r.triggered]
            summary_rows.append(
                [
                    trial.trial_id,
                    trial.overall_risk.value,
                    str(len(trial.features.features)),
                    str(len(triggered)),
                    trial.features.ssc_category or "-",
                    trial.sync.strategy if trial.sync else "-",
                    str(len(trial.warnings)),
                ]
            )
            summary_levels.append(trial.overall_risk)
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
                    [trial.trial_id, r.name, r.feature,
                     f"{r.observed_value:.4g}" if r.observed_value is not None else "-",
                     r.reference, r.risk_level.value]
                )
                risk_levels.append(r.risk_level)
            for pc in trial.profile_comparisons:
                profile_rows.append(
                    [
                        trial.trial_id, pc.feature, pc.region,
                        f"{pc.value:.4g} {pc.unit}",
                        f"{pc.control_mean:g} ± {pc.control_sd:g}",
                        f"{pc.aclr_mean:g} ± {pc.aclr_sd:g}",
                        pc.closer_to,
                    ]
                )
                profile_levels.append(
                    RiskLevel.LOW if pc.closer_to == "control"
                    else (RiskLevel.MODERATE if pc.closer_to == "between"
                          else RiskLevel.HIGH)
                )

        _fill_table(
            self.summary_table,
            ["Trial", "Risk", "Features", "Triggered", "SSC", "Sync", "Warnings"],
            summary_rows, risk_col=1, risk_levels=summary_levels,
        )
        _fill_table(
            self.features_table,
            ["Trial", "Feature", "Value", "Unit", "z-score", "Validation"],
            feature_rows,
        )
        if risk_rows:
            _fill_table(
                self.risk_table,
                ["Trial", "Indicator", "Feature", "Observed", "Reference", "Level"],
                risk_rows, risk_col=5, risk_levels=risk_levels,
            )
        else:
            _fill_table(
                self.risk_table,
                ["Trial", "Indicator", "Feature", "Observed", "Reference", "Level"],
                [["—", "No indicator triggered", "", "", "", ""]],
            )
        _fill_table(
            self.profile_table,
            ["Trial", "Feature", "Region", "Value", "Control μ±σ", "ACLR μ±σ",
             "Closer to"],
            profile_rows, risk_col=6, risk_levels=profile_levels,
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
            self.tabs.setCurrentIndex(4)

    # ---------------------------------------------------------------- report

    def _generate_report(self) -> None:
        result = self.state.result
        if result is None:
            QMessageBox.warning(self, "Report", "Run an analysis first.")
            return
        from biomech_analyzer.reporting.pdf_report import generate_pdf_report

        language = str(self.language_combo.currentData() or "en")
        self.state.report_language = language
        try:
            if self.state.model_path is not None:
                from biomech_analyzer.ml.inference import predict_participant

                result.ml_output = predict_participant(result, self.state.model_path)
            out_dir = Path(self.state.config.get("report.output_dir", "output/reports"))
            include_plots = bool(self.state.config.get("report.include_plots", True))
            report_path = generate_pdf_report(
                result, out_dir, include_plots=include_plots, language=language
            )
            result.report_path = report_path
            if self.state.analysis_id is not None:
                from biomech_analyzer.storage.sqlite_repository import SqliteRepository

                with SqliteRepository(self.state.db_path) as repo:
                    repo.update_report_path(
                        self.state.analysis_id, report_path,
                        overall_risk=result.overall_risk.value,
                    )
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
