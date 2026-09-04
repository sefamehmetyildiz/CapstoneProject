"""History screen — stored analyses, past reports, and ML retraining.

Lists every analysis saved to the local SQLite database (analyses are
auto-saved after each run), colour-codes the overall risk level, lets the
user reopen past PDF reports and inspect stored features, and offers a
"Retrain ML" button that retrains the condition classifier on the full
accumulated history (labels come from the trial conditions, so no external
ground truth is needed).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer.app.state import AppState
from biomech_analyzer.core.constants import RISK_BG_COLORS, RISK_COLORS, RiskLevel
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.storage.sqlite_repository import SqliteRepository


class _RetrainWorker(QThread):
    """Retrains the condition classifier off the UI thread."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def run(self) -> None:  # noqa: D102
        try:
            from biomech_analyzer.ml.retrain import retrain_condition_model

            result = retrain_condition_model(self.state.db_path, self.state.config)
            lines = [
                f"Condition classifier retrained on {result.n_trials} trials "
                f"from {result.n_participants} participants.",
                *result.output.evaluation.summary_lines(),
                f"Model exported to {result.model_path}",
            ]
            self.finished_ok.emit("\n".join(lines))
        except BiomechError as exc:
            self.failed.emit(exc.user_message)
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc!r}")


class HistoryScreen(QWidget):
    """Past analyses browser + self-retraining entry point."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._rows: list[dict] = []
        self._worker: _RetrainWorker | None = None

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(
            "Analyses saved to the local database (auto-saved after each run):"
        ))
        header.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._show_details)
        splitter.addWidget(self.table)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Select an analysis to see its stored features."
        )
        splitter.addWidget(self.details)
        splitter.setSizes([300, 200])
        layout.addWidget(splitter, stretch=1)

        actions = QHBoxLayout()
        self.open_btn = QPushButton("Open PDF Report")
        self.open_btn.clicked.connect(self._open_report)
        actions.addWidget(self.open_btn)
        self.delete_btn = QPushButton("Delete Entry")
        self.delete_btn.clicked.connect(self._delete_entry)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        self.retrain_btn = QPushButton("Retrain ML from History")
        self.retrain_btn.setProperty("primary", True)
        self.retrain_btn.setToolTip(
            "Retrains the condition classifier (baseline / upright / "
            "cognitive) on every stored analysis using leave-one-subject-out "
            "validation. Research-oriented output; risk assessment stays "
            "with the interpretable rule-based layer."
        )
        self.retrain_btn.clicked.connect(self._retrain)
        actions.addWidget(self.retrain_btn)
        layout.addLayout(actions)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    # ------------------------------------------------------------------ data

    def refresh(self) -> None:
        self._rows = []
        self.table.clear()
        if not self.state.db_path.is_file():
            self.table.setRowCount(0)
            self.status_label.setText(
                "No database yet — run an analysis first; it will be saved "
                "automatically."
            )
            return
        try:
            with SqliteRepository(self.state.db_path) as repo:
                self._rows = repo.list_analyses()
        except BiomechError as exc:
            QMessageBox.critical(self, "History", exc.user_message)
            return
        headers = ["ID", "Participant", "Analyzed at", "Overall risk", "Report"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self._rows))
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for r, row in enumerate(self._rows):
            try:
                level = RiskLevel(str(row.get("overall_risk") or "LOW"))
            except ValueError:
                level = RiskLevel.LOW
            report = row.get("report_path")
            report_text = Path(report).name if report else "—"
            cells = [
                str(row["id"]),
                str(row["participant_id"]),
                str(row["analysis_timestamp"]),
                level.value,
                report_text,
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 3:
                    item.setForeground(QColor(RISK_COLORS[level]))
                    item.setBackground(QColor(RISK_BG_COLORS[level]))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.status_label.setText(f"{len(self._rows)} stored analysis record(s).")

    def _selected_row(self) -> dict | None:
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self._rows):
            return None
        return self._rows[idx]

    def _show_details(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        try:
            with SqliteRepository(self.state.db_path) as repo:
                feats = repo.features_for_analysis(int(row["id"]))
        except BiomechError as exc:
            self.details.setPlainText(exc.user_message)
            return
        lines = [
            f"Participant {row['participant_id']} — {row['analysis_timestamp']}",
            f"Folder: {row['folder']}",
            "",
        ]
        current_trial = None
        for f in feats:
            if f["trial_id"] != current_trial:
                current_trial = f["trial_id"]
                lines.append(f"[{current_trial}]")
            lines.append(f"  {f['name']} = {f['value']:.4g} {f['unit']}")
        self.details.setPlainText("\n".join(lines))

    # ---------------------------------------------------------------- actions

    def _open_report(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "History", "Select an analysis first.")
            return
        report = row.get("report_path")
        if not report or not Path(report).is_file():
            QMessageBox.information(
                self, "History",
                "No PDF report is stored for this analysis (or the file was "
                "moved). Generate one from the Results screen.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    def _delete_entry(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "History", "Select an analysis first.")
            return
        answer = QMessageBox.question(
            self, "Delete entry",
            f"Delete stored analysis #{row['id']} of participant "
            f"{row['participant_id']}? The PDF file (if any) is not deleted.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with SqliteRepository(self.state.db_path) as repo:
                repo.delete_analysis(int(row["id"]))
        except BiomechError as exc:
            QMessageBox.critical(self, "History", exc.user_message)
            return
        self.refresh()

    def _retrain(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if not self.state.db_path.is_file():
            QMessageBox.information(
                self, "Retrain ML",
                "No stored analyses yet — run and save analyses first.",
            )
            return
        self.retrain_btn.setEnabled(False)
        self.status_label.setText("Retraining condition classifier from history…")
        self._worker = _RetrainWorker(self.state)
        self._worker.finished_ok.connect(self._on_retrained)
        self._worker.failed.connect(self._on_retrain_failed)
        self._worker.start()

    def _on_retrained(self, summary: str) -> None:
        self.retrain_btn.setEnabled(True)
        self.status_label.setText("Retraining finished — see details below.")
        self.details.setPlainText(summary)
        QMessageBox.information(self, "Retrain ML", "Retraining finished.")

    def _on_retrain_failed(self, message: str) -> None:
        self.retrain_btn.setEnabled(True)
        self.status_label.setText("")
        QMessageBox.critical(self, "Retrain ML", message)
