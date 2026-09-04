"""Screen 2 — analysis dashboard: run the pipeline with live progress."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer.app.state import AppState
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.core.models import ParticipantResult
from biomech_analyzer.core.pipeline import AnalysisPipeline


class _AnalysisWorker(QThread):
    """Runs the pipeline off the UI thread."""

    progressed = Signal(str)
    finished_ok = Signal(object)  # ParticipantResult
    failed = Signal(str)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state

    def run(self) -> None:  # noqa: D102
        try:
            pipeline = AnalysisPipeline(
                self.state.config, baseline_path=self.state.baseline_path
            )
            assert self.state.folder is not None
            result = pipeline.analyze(
                self.state.folder,
                self.state.participant_id or None,
                progress=lambda msg: self.progressed.emit(msg),
            )
            self.finished_ok.emit(result)
        except BiomechError as exc:
            self.failed.emit(exc.user_message)
        except Exception as exc:  # surfaced to the user, never swallowed
            self.failed.emit(f"Unexpected error: {exc!r}")


class AnalysisDashboardScreen(QWidget):
    """Progress display + Run Analysis button + error/warning area."""

    analysis_finished = Signal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._worker: _AnalysisWorker | None = None

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Validate a participant folder first.")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        layout.addWidget(self.progress_bar)

        self.run_btn = QPushButton("▶  Run Analysis")
        self.run_btn.setProperty("primary", True)
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self._run)
        layout.addWidget(self.run_btn)

        layout.addWidget(QLabel("Progress log / warnings:"))
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area, stretch=1)

    def refresh(self) -> None:
        """Called when validation state changes."""
        if self.state.validation is not None:
            self.status_label.setText(
                f"Ready to analyze participant {self.state.validation.participant_id} "
                f"({len(self.state.validation.trials)} trial(s) detected)."
            )
            self.log_area.setPlainText(
                "\n".join(self.state.validation.summary_lines())
            )

    # ------------------------------------------------------------------ slots

    def _run(self) -> None:
        if self.state.validation is None or self.state.folder is None:
            QMessageBox.warning(
                self, "Run Analysis", "Please validate a participant folder first."
            )
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self.state.rebuild_config()
        self.run_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)  # busy indicator
        self.log_area.appendPlainText("\n--- Analysis started ---")

        self._worker = _AnalysisWorker(self.state)
        self._worker.progressed.connect(self.log_area.appendPlainText)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_finished(self, result: ParticipantResult) -> None:
        self.state.result = result
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.run_btn.setEnabled(True)
        self.log_area.appendPlainText(
            f"Analyzed {len(result.trials)} trial(s). "
            f"Overall risk level: {result.overall_risk.value}."
        )
        for w in result.warnings:
            self.log_area.appendPlainText(f"WARNING: {w}")
        self._auto_save(result)
        self.status_label.setText("Analysis complete — see Results and Report.")
        self.analysis_finished.emit()

    def _auto_save(self, result: ParticipantResult) -> None:
        """Persist the analysis to the local database for the History screen."""
        try:
            from biomech_analyzer.storage.sqlite_repository import SqliteRepository

            with SqliteRepository(self.state.db_path) as repo:
                self.state.analysis_id = repo.save_participant_result(result)
            self.log_area.appendPlainText(
                f"Saved to local database (record #{self.state.analysis_id})."
            )
        except Exception as exc:  # saving must never block the workflow
            self.state.analysis_id = None
            self.log_area.appendPlainText(f"WARNING: could not save to database: {exc}")

    def _on_failed(self, message: str) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(True)
        self.log_area.appendPlainText(f"ERROR: {message}")
        QMessageBox.critical(self, "Analysis failed", message)
