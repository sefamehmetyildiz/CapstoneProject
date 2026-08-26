"""Main window of the desktop application.

Workflow tabs mirror the proposal's wireframe (Figure 1):
1. Folder Selection  →  2. Analysis Dashboard  →  3. Results and Report,
plus a separate Advanced / Research screen.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar, QTabWidget

from biomech_analyzer import DISCLAIMER, __version__
from biomech_analyzer.app.screens.advanced_settings import AdvancedSettingsScreen
from biomech_analyzer.app.screens.analysis_dashboard import AnalysisDashboardScreen
from biomech_analyzer.app.screens.folder_selection import FolderSelectionScreen
from biomech_analyzer.app.screens.results_report import ResultsReportScreen
from biomech_analyzer.app.state import AppState

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Biomech Analyzer v{__version__} — decision-support only")
        self.resize(1000, 720)
        self.state = AppState()

        self.tabs = QTabWidget()
        self.folder_screen = FolderSelectionScreen(self.state)
        self.dashboard_screen = AnalysisDashboardScreen(self.state)
        self.results_screen = ResultsReportScreen(self.state)
        self.advanced_screen = AdvancedSettingsScreen(self.state)

        self.tabs.addTab(self.folder_screen, "1. Folder Selection")
        self.tabs.addTab(self.dashboard_screen, "2. Analysis Dashboard")
        self.tabs.addTab(self.results_screen, "3. Results and Report")
        self.tabs.addTab(self.advanced_screen, "Advanced / Research")
        self.setCentralWidget(self.tabs)

        status = QStatusBar()
        status.showMessage(DISCLAIMER)
        self.setStatusBar(status)

        self.folder_screen.validated.connect(self._on_validated)
        self.dashboard_screen.analysis_finished.connect(self._on_analyzed)

    def _on_validated(self) -> None:
        self.dashboard_screen.refresh()
        self.tabs.setCurrentWidget(self.dashboard_screen)

    def _on_analyzed(self) -> None:
        self.results_screen.refresh()
        self.tabs.setCurrentWidget(self.results_screen)


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Biomech Analyzer")
    window = MainWindow()
    window.show()
    return app.exec()
