"""Screen 4 — advanced analysis settings and Research Mode (ML).

Separated from the standard three-step workflow, per the proposal: intended
for the project team, not routine clinical use.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer.app.state import AppState
from biomech_analyzer.core.exceptions import BiomechError


class _TrainWorker(QThread):
    """Research-mode training off the UI thread."""

    progressed = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, state: AppState, dataset_dir: Path, labels_path: Path,
                 model_out: Path) -> None:
        super().__init__()
        self.state = state
        self.dataset_dir = dataset_dir
        self.labels_path = labels_path
        self.model_out = model_out

    def run(self) -> None:  # noqa: D102
        try:
            from biomech_analyzer.core.pipeline import AnalysisPipeline
            from biomech_analyzer.ml.dataset_builder import (
                build_feature_table,
                load_labels,
                split_xy,
            )
            from biomech_analyzer.ml.train import export_model, train_and_evaluate

            participant_dirs = sorted(
                p for p in self.dataset_dir.iterdir()
                if p.is_dir() and p.name.lower() != "baseline"
            )
            if not participant_dirs:
                raise BiomechError("No participant subfolders found in the dataset folder.")
            pipeline = AnalysisPipeline(
                self.state.config, baseline_path=self.state.baseline_path
            )
            results = []
            for pdir in participant_dirs:
                self.progressed.emit(f"Analyzing {pdir.name}…")
                results.append(pipeline.analyze(pdir))
            labels = load_labels(self.labels_path)
            table = build_feature_table(results, labels)
            x, y, groups = split_xy(table)
            self.progressed.emit("Running leave-one-subject-out cross-validation…")
            output = train_and_evaluate(x, y, groups, self.state.config)
            export_model(output, self.model_out)
            lines = output.evaluation.summary_lines()
            lines.append(f"Model exported to {self.model_out}")
            lines.append("Top feature importances:")
            lines += [
                f"  {name}: {imp:.3f}"
                for name, imp in list(output.feature_importances.items())[:10]
            ]
            self.finished_ok.emit("\n".join(lines))
        except BiomechError as exc:
            self.failed.emit(exc.user_message)
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc!r}")


class AdvancedSettingsScreen(QWidget):
    """Analysis parameter overrides + Research Mode."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._worker: _TrainWorker | None = None

        layout = QVBoxLayout(self)

        params_box = QGroupBox("Analysis parameters (require BME validation)")
        form = QFormLayout(params_box)

        self.cutoff_spin = QDoubleSpinBox()
        self.cutoff_spin.setRange(1.0, 500.0)
        self.cutoff_spin.setValue(float(state.config.get("force_plate.lowpass_cutoff_hz", 50.0)))
        form.addRow("Force plate low-pass cutoff (Hz):", self.cutoff_spin)

        self.fz_threshold_spin = QDoubleSpinBox()
        self.fz_threshold_spin.setRange(1.0, 200.0)
        self.fz_threshold_spin.setValue(float(state.config.get("force_plate.contact_threshold_n", 20.0)))
        form.addRow("Contact threshold Fz (N):", self.fz_threshold_spin)

        self.rms_spin = QDoubleSpinBox()
        self.rms_spin.setRange(0.005, 0.5)
        self.rms_spin.setSingleStep(0.005)
        self.rms_spin.setDecimals(3)
        self.rms_spin.setValue(float(state.config.get("emg.rms_window_s", 0.05)))
        form.addRow("EMG RMS window (s):", self.rms_spin)

        apply_btn = QPushButton("Apply settings")
        apply_btn.clicked.connect(self._apply)
        form.addRow(apply_btn)
        layout.addWidget(params_box)

        model_box = QGroupBox("Trained model for report inference (optional)")
        model_row = QHBoxLayout(model_box)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("Path to exported .joblib model")
        model_btn = QPushButton("Browse…")
        model_btn.clicked.connect(self._browse_model)
        model_row.addWidget(self.model_edit)
        model_row.addWidget(model_btn)
        layout.addWidget(model_box)

        research_box = QGroupBox("Research Mode — exploratory ML (project team only)")
        research_layout = QVBoxLayout(research_box)
        research_layout.addWidget(
            QLabel(
                "Trains a Random Forest with leave-one-subject-out validation on a "
                "folder of participant subfolders plus a labels CSV. Exploratory "
                "only — not the primary diagnostic output."
            )
        )
        row = QHBoxLayout()
        self.dataset_edit = QLineEdit()
        self.dataset_edit.setPlaceholderText("Dataset folder (participant subfolders)")
        ds_btn = QPushButton("Browse…")
        ds_btn.clicked.connect(self._browse_dataset)
        row.addWidget(self.dataset_edit)
        row.addWidget(ds_btn)
        research_layout.addLayout(row)
        row2 = QHBoxLayout()
        self.labels_edit = QLineEdit()
        self.labels_edit.setPlaceholderText("Labels CSV (participant_id,label)")
        lb_btn = QPushButton("Browse…")
        lb_btn.clicked.connect(self._browse_labels)
        row2.addWidget(self.labels_edit)
        row2.addWidget(lb_btn)
        research_layout.addLayout(row2)
        self.train_btn = QPushButton("Train / evaluate / export model")
        self.train_btn.clicked.connect(self._train)
        research_layout.addWidget(self.train_btn)
        self.research_output = QPlainTextEdit()
        self.research_output.setReadOnly(True)
        research_layout.addWidget(self.research_output, stretch=1)
        layout.addWidget(research_box, stretch=1)

    # ------------------------------------------------------------------ slots

    def _apply(self) -> None:
        self.state.config_overrides = {
            "force_plate": {
                "lowpass_cutoff_hz": self.cutoff_spin.value(),
                "contact_threshold_n": self.fz_threshold_spin.value(),
            },
            "emg": {"rms_window_s": self.rms_spin.value()},
        }
        self.state.rebuild_config()
        model_text = self.model_edit.text().strip()
        self.state.model_path = Path(model_text) if model_text else None
        QMessageBox.information(
            self, "Settings", "Settings applied to the next analysis run."
        )

    def _browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select trained model", "", "Model files (*.joblib *.pkl)"
        )
        if path:
            self.model_edit.setText(path)
            self.state.model_path = Path(path)

    def _browse_dataset(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select dataset folder")
        if path:
            self.dataset_edit.setText(path)

    def _browse_labels(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select labels CSV", "", "CSV files (*.csv)"
        )
        if path:
            self.labels_edit.setText(path)

    def _train(self) -> None:
        dataset = self.dataset_edit.text().strip()
        labels = self.labels_edit.text().strip()
        if not dataset or not labels:
            QMessageBox.warning(
                self, "Research Mode", "Select both a dataset folder and a labels CSV."
            )
            return
        if self._worker is not None and self._worker.isRunning():
            return
        model_dir = Path(self.state.config.get("ml.model_dir", "output/models"))
        self.train_btn.setEnabled(False)
        self.research_output.appendPlainText("--- Training started ---")
        self._worker = _TrainWorker(
            self.state, Path(dataset), Path(labels), model_dir / "random_forest.joblib"
        )
        self._worker.progressed.connect(self.research_output.appendPlainText)
        self._worker.finished_ok.connect(self._on_trained)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_trained(self, summary: str) -> None:
        self.train_btn.setEnabled(True)
        self.research_output.appendPlainText(summary)

    def _on_failed(self, message: str) -> None:
        self.train_btn.setEnabled(True)
        self.research_output.appendPlainText(f"ERROR: {message}")
        QMessageBox.critical(self, "Research Mode", message)
