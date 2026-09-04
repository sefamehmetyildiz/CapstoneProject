"""Application-wide Qt stylesheet for a cleaner, friendlier UI."""

from __future__ import annotations

STYLESHEET = """
QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog { background: #f4f6f9; }
QTabWidget::pane {
    border: 1px solid #cfd8e3;
    background: #ffffff;
    border-radius: 4px;
}
QTabBar::tab {
    padding: 7px 16px;
    background: #e4eaf2;
    border: 1px solid #cfd8e3;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
    color: #33475b;
}
QTabBar::tab:selected {
    background: #ffffff;
    font-weight: 600;
    color: #1a3b5d;
}
QGroupBox {
    border: 1px solid #cfd8e3;
    border-radius: 5px;
    margin-top: 12px;
    background: #ffffff;
    font-weight: 600;
    color: #1a3b5d;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #b6c2d2;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background: #eef3fa; }
QPushButton:disabled { color: #9aa7b5; }
QPushButton[primary="true"] {
    background: #1f6fd6;
    color: white;
    border: 1px solid #1a5cb0;
    font-weight: 600;
}
QPushButton[primary="true"]:hover { background: #2a7ce6; }
QPushButton[primary="true"]:disabled { background: #9dbce3; }
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #b6c2d2;
    border-radius: 4px;
    padding: 4px 6px;
}
QTableWidget, QTreeWidget {
    background: #ffffff;
    alternate-background-color: #f4f7fb;
    border: 1px solid #cfd8e3;
    gridline-color: #dde4ec;
}
QHeaderView::section {
    background: #e8eef7;
    padding: 5px;
    border: none;
    border-right: 1px solid #cfd8e3;
    border-bottom: 1px solid #cfd8e3;
    font-weight: 600;
    color: #1a3b5d;
}
QProgressBar {
    border: 1px solid #b6c2d2;
    border-radius: 4px;
    text-align: center;
    background: #ffffff;
}
QProgressBar::chunk { background: #1f6fd6; border-radius: 3px; }
QStatusBar { background: #fff6e5; color: #8a5a00; }
QLabel[riskBadge="true"] {
    font-weight: 700;
    padding: 6px 12px;
    border-radius: 5px;
}
"""
