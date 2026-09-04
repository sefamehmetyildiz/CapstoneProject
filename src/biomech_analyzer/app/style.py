"""Modern web-app style Qt stylesheet (sidebar navigation + card layout)."""

from __future__ import annotations

ACCENT = "#2563eb"
ACCENT_HOVER = "#3b82f6"
ACCENT_DARK = "#1d4ed8"
SIDEBAR_BG = "#0f172a"
PAGE_BG = "#f1f5f9"
CARD_BORDER = "#e2e8f0"
TEXT = "#0f172a"
TEXT_MUTED = "#64748b"

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {PAGE_BG}; }}

/* ---------------- Sidebar navigation ---------------- */
#Sidebar {{
    background: {SIDEBAR_BG};
    border: none;
}}
#Sidebar QLabel {{ color: #e2e8f0; background: transparent; }}
#AppTitle {{
    color: #ffffff;
    font-size: 12.5pt;
    font-weight: 700;
    padding: 4px 0 0 0;
}}
#AppSubtitle {{
    color: #94a3b8;
    font-size: 8pt;
    padding-bottom: 10px;
}}
#SidebarFooter {{
    color: #64748b;
    font-size: 7.5pt;
}}
QPushButton#NavButton {{
    background: transparent;
    color: #cbd5e1;
    border: none;
    border-radius: 8px;
    padding: 11px 14px;
    text-align: left;
    font-size: 10.5pt;
}}
QPushButton#NavButton:hover {{
    background: rgba(148, 163, 184, 0.14);
    color: #ffffff;
}}
QPushButton#NavButton:checked {{
    background: {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}

/* ---------------- Header bar ---------------- */
#HeaderBar {{
    background: #ffffff;
    border-bottom: 1px solid {CARD_BORDER};
}}
#PageTitle {{
    font-size: 14pt;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
#PageSubtitle {{
    color: {TEXT_MUTED};
    font-size: 9pt;
    background: transparent;
}}
#HeaderChip {{
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 12px;
    font-size: 9.5pt;
}}

/* ---------------- Content / cards ---------------- */
#ContentArea {{ background: {PAGE_BG}; }}
QGroupBox {{
    border: 1px solid {CARD_BORDER};
    border-radius: 10px;
    margin-top: 14px;
    background: #ffffff;
    font-weight: 600;
    color: {TEXT};
    padding: 10px 6px 6px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_MUTED};
    text-transform: uppercase;
    font-size: 8.5pt;
    letter-spacing: 1px;
}}
QLabel[riskBadge="true"] {{
    font-weight: 700;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 12pt;
}}

/* ---------------- Buttons ---------------- */
QPushButton {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 18px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #f1f5f9; border-color: #94a3b8; }}
QPushButton:pressed {{ background: #e2e8f0; }}
QPushButton:disabled {{ color: #94a3b8; background: #f8fafc; }}
QPushButton[primary="true"] {{
    background: {ACCENT};
    color: #ffffff;
    border: none;
    font-weight: 600;
    padding: 9px 22px;
}}
QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {ACCENT_DARK}; }}
QPushButton[primary="true"]:disabled {{ background: #93c5fd; color: #eff6ff; }}

/* ---------------- Inputs ---------------- */
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 1.5px solid {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {CARD_BORDER};
    border-radius: 8px;
    selection-background-color: #dbeafe;
    selection-color: {TEXT};
}}

/* ---------------- Tables & trees ---------------- */
QTableWidget, QTreeWidget {{
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid {CARD_BORDER};
    border-radius: 10px;
    gridline-color: #eef2f7;
    selection-background-color: #dbeafe;
    selection-color: {TEXT};
}}
QTableWidget::item, QTreeWidget::item {{ padding: 6px; }}
QHeaderView::section {{
    background: #f8fafc;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid {CARD_BORDER};
    font-weight: 700;
    font-size: 8.5pt;
    color: {TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTableCornerButton::section {{ background: #f8fafc; border: none; }}

/* ---------------- Sub-tabs (segmented control look) ---------------- */
QTabWidget::pane {{
    border: 1px solid {CARD_BORDER};
    background: #ffffff;
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    padding: 8px 18px;
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    margin-right: 4px;
    border-bottom: 3px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 3px solid {ACCENT};
}}

/* ---------------- Progress / status / splitter ---------------- */
QProgressBar {{
    border: none;
    border-radius: 7px;
    text-align: center;
    background: #e2e8f0;
    height: 14px;
    color: {TEXT};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 7px; }}
QStatusBar {{ background: #ffffff; color: {TEXT_MUTED}; border-top: 1px solid {CARD_BORDER}; }}
QSplitter::handle {{ background: {CARD_BORDER}; height: 2px; }}
QToolTip {{
    background: {SIDEBAR_BG};
    color: #e2e8f0;
    border: none;
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------------- Scrollbars (slim, web-like) ---------------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #cbd5e1; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #94a3b8; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #cbd5e1; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #94a3b8; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
