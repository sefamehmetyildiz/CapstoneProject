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
    assert win.stack.count() == 5  # workflow (3) + History + Advanced
    assert len(win._nav_buttons) == 5  # sidebar navigation entries
    assert win._nav_buttons[0].isChecked()  # starts on Folder Selection
    assert "decision-support" in win.windowTitle()
    # report language selector offers English and Turkish
    combo = win.results_screen.language_combo
    values = {combo.itemData(i) for i in range(combo.count())}
    assert values == {"en", "tr"}


def test_sidebar_navigation_switches_pages(qapp):
    from biomech_analyzer.app.gui_main import MainWindow

    win = MainWindow()
    win._go(3)
    assert win.current_screen() is win.history_screen
    assert win.page_title.text() == "History"
    win._go(0)
    assert win.current_screen() is win.folder_screen


def test_folder_validation_flow(qapp, p001: Path):
    from biomech_analyzer.app.gui_main import MainWindow

    win = MainWindow()
    screen = win.folder_screen
    screen.folder_edit.setText(str(p001))
    screen._validate()
    assert win.state.validation is not None
    assert win.state.validation.participant_id == "P001"
    assert screen.tree.topLevelItemCount() == 6
    # dashboard was refreshed and became the active page
    assert win.current_screen() is win.dashboard_screen
    assert "P001" in win.dashboard_screen.status_label.text()
    assert "P001" in win.header_chip.text()


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
    assert win.results_screen.profile_table.rowCount() > 0
    assert "risk level" in win.results_screen.risk_badge.text()


def test_history_screen_with_populated_db(qapp, p001: Path, config, tmp_path: Path):
    from biomech_analyzer.app.gui_main import MainWindow
    from biomech_analyzer.core.config import Config
    from biomech_analyzer.core.pipeline import AnalysisPipeline
    from biomech_analyzer.storage.sqlite_repository import SqliteRepository

    win = MainWindow()
    db = tmp_path / "hist.sqlite3"
    win.state.config = Config(
        {**config.as_dict(), "storage": {"sqlite_path": str(db)}}
    )
    # empty database path -> friendly message, no crash
    win.history_screen.refresh()
    assert win.history_screen.table.rowCount() == 0

    result = AnalysisPipeline(config).analyze(p001)
    with SqliteRepository(db) as repo:
        repo.save_participant_result(result)
    win.history_screen.refresh()
    assert win.history_screen.table.rowCount() == 1
    assert win.history_screen.table.item(0, 1).text() == "P001"
