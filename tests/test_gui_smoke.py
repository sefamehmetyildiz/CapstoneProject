"""GUI smoke tests using the offscreen Qt platform (no display needed)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds(qapp):
    from biomech_analyzer.app.gui_main import MainWindow

    win = MainWindow()
    assert win.tabs.count() == 4
    assert "decision-support" in win.windowTitle()


def test_folder_validation_flow(qapp, p001: Path):
    from biomech_analyzer.app.gui_main import MainWindow

    win = MainWindow()
    screen = win.folder_screen
    screen.folder_edit.setText(str(p001))
    screen._validate()
    assert win.state.validation is not None
    assert win.state.validation.participant_id == "P001"
    assert screen.tree.topLevelItemCount() == 6
    # dashboard was refreshed and became the active tab
    assert win.tabs.currentWidget() is win.dashboard_screen
    assert "P001" in win.dashboard_screen.status_label.text()


def test_results_refresh_with_result(qapp, p001: Path, config, mock_data_dir: Path):
    from biomech_analyzer.app.gui_main import MainWindow
    from biomech_analyzer.core.pipeline import AnalysisPipeline

    win = MainWindow()
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    win.state.result = pipeline.analyze(p001)
    win.results_screen.refresh()
    assert win.results_screen.summary_table.rowCount() == 6
    assert win.results_screen.features_table.rowCount() > 0
