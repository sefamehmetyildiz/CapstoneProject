"""Main window — modern dashboard layout.

Web-app style shell: a dark sidebar with icon navigation on the left, a
white header bar showing the current page and the participant risk chip,
and a stacked content area hosting the five screens.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biomech_analyzer import __version__
from biomech_analyzer.app.screens.advanced_settings import AdvancedSettingsScreen
from biomech_analyzer.app.screens.analysis_dashboard import AnalysisDashboardScreen
from biomech_analyzer.app.screens.folder_selection import FolderSelectionScreen
from biomech_analyzer.app.screens.history import HistoryScreen
from biomech_analyzer.app.screens.results_report import ResultsReportScreen
from biomech_analyzer.app.state import AppState
from biomech_analyzer.app.style import STYLESHEET
from biomech_analyzer.core.constants import RISK_BG_COLORS, RISK_COLORS

log = logging.getLogger(__name__)

_NAV_ITEMS = [
    ("📂", "Folder Selection", "Select and validate a participant folder"),
    ("📊", "Analysis", "Run the automated multimodal analysis"),
    ("📄", "Results & Report", "Review findings and export the PDF report"),
    ("🕘", "History", "Past analyses, stored reports and ML retraining"),
    ("🧪", "Advanced / Research", "Analysis parameters and Research Mode"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            f"Biomech Analyzer v{__version__} — decision-support only"
        )
        self.resize(1240, 800)
        self.setMinimumSize(1000, 660)
        self.state = AppState()

        self.folder_screen = FolderSelectionScreen(self.state)
        self.dashboard_screen = AnalysisDashboardScreen(self.state)
        self.results_screen = ResultsReportScreen(self.state)
        self.history_screen = HistoryScreen(self.state)
        self.advanced_screen = AdvancedSettingsScreen(self.state)
        self._screens = [
            self.folder_screen,
            self.dashboard_screen,
            self.results_screen,
            self.history_screen,
            self.advanced_screen,
        ]

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), stretch=1)
        self.setCentralWidget(central)

        self.folder_screen.validated.connect(self._on_validated)
        self.dashboard_screen.analysis_finished.connect(self._on_analyzed)
        self._go(0)

    # ------------------------------------------------------------------ shell

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(244)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        title = QLabel("⚡ Biomech Analyzer")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        subtitle = QLabel("Single-Leg Jump Analysis Platform")
        subtitle.setObjectName("AppSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        for index, (icon, label, _sub) in enumerate(_NAV_ITEMS):
            # "&" is a Qt mnemonic marker inside button texts; escape it.
            btn = QPushButton(f"{icon}  {label.replace('&', '&&')}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self._go(i))
            self._nav_group.addButton(btn, index)
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        footer = QLabel(
            f"v{__version__} · offline\nDecision-support only —\nnot a medical diagnosis."
        )
        footer.setObjectName("SidebarFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _build_content(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("ContentArea")
        column = QVBoxLayout(wrapper)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(64)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(24, 8, 24, 8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel("")
        self.page_title.setObjectName("PageTitle")
        titles.addWidget(self.page_title)
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.page_subtitle)
        hlayout.addLayout(titles)
        hlayout.addStretch(1)
        self.header_chip = QLabel("No analysis yet")
        self.header_chip.setObjectName("HeaderChip")
        self._style_chip(None)
        hlayout.addWidget(self.header_chip)
        column.addWidget(header)

        self.stack = QStackedWidget()
        for screen in self._screens:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(24, 18, 24, 18)
            page_layout.addWidget(screen)
            self.stack.addWidget(page)
        column.addWidget(self.stack, stretch=1)
        return wrapper

    def _style_chip(self, level) -> None:
        if level is None:
            self.header_chip.setStyleSheet(
                "#HeaderChip { background: #e2e8f0; color: #64748b; }"
            )
            return
        self.header_chip.setStyleSheet(
            f"#HeaderChip {{ background: {RISK_BG_COLORS[level]}; "
            f"color: {RISK_COLORS[level]}; "
            f"border: 1px solid {RISK_COLORS[level]}; }}"
        )

    # ------------------------------------------------------------------ nav

    def _go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self._nav_buttons[index].setChecked(True)
        icon, label, sub = _NAV_ITEMS[index]
        self.page_title.setText(label)
        self.page_subtitle.setText(sub)
        if self._screens[index] is self.history_screen:
            self.history_screen.refresh()

    def current_screen(self) -> QWidget:
        return self._screens[self.stack.currentIndex()]

    # ------------------------------------------------------------------ flow

    def _on_validated(self) -> None:
        self.dashboard_screen.refresh()
        if self.state.validation is not None:
            self.header_chip.setText(
                f"Participant {self.state.validation.participant_id}"
            )
            self._style_chip(None)
        self._go(1)

    def _on_analyzed(self) -> None:
        self.results_screen.refresh()
        result = self.state.result
        if result is not None:
            self.header_chip.setText(
                f"{result.participant_id} · risk: {result.overall_risk.value}"
            )
            self._style_chip(result.overall_risk)
        self._go(2)


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Biomech Analyzer")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()
