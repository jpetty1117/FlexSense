"""
Dark medical/clinical theme for the Rehabilitation Test GUI.
"""

# ── Color Palette ────────────────────────────────────────────────
COLORS = {
    "bg_dark": "#0d1117",
    "bg_card": "#161b22",
    "bg_surface": "#21262d",
    "bg_input": "#1c2128",
    "border": "#30363d",
    "border_focus": "#16c79a",
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "text_muted": "#6e7681",
    "accent": "#16c79a",
    "accent_hover": "#1de9b6",
    "accent_dark": "#0f8a6b",
    "danger": "#f85149",
    "warning": "#d29922",
    "info": "#58a6ff",
    "graph_bg": "#0d1117",
    "graph_grid": "#21262d",
    "graph_rom": "#16c79a",
    "graph_speed": "#58a6ff",
    "graph_strength": "#f0883e",
    "graph_spo2": "#f778ba",
}


STYLESHEET = f"""
    /* ── Global ──────────────────────────────────── */
    QWidget {{
        background-color: {COLORS['bg_dark']};
        color: {COLORS['text_primary']};
        font-family: 'Helvetica', 'Arial', sans-serif;
        font-size: 14px;
    }}

    /* ── Labels ──────────────────────────────────── */
    QLabel {{
        background-color: transparent;
        padding: 2px;
    }}

    QLabel#title {{
        font-size: 32px;
        font-weight: bold;
        color: {COLORS['text_primary']};
        padding: 10px 10px 8px 10px;
        border-bottom: 2px solid {COLORS['accent']};
    }}

    QLabel#subtitle {{
        font-size: 18px;
        color: {COLORS['text_secondary']};
        padding: 4px;
    }}

    QLabel#section_header {{
        font-size: 16px;
        font-weight: bold;
        color: {COLORS['text_primary']};
        border-bottom: 2px solid {COLORS['accent']};
        padding-bottom: 6px;
        margin-top: 8px;
    }}

    QLabel#client_info {{
        font-size: 15px;
        color: {COLORS['text_primary']};
        padding: 4px 8px;
    }}

    /* ── Buttons ─────────────────────────────────── */
    QPushButton {{
        background-color: {COLORS['bg_surface']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        padding: 12px 24px;
        font-size: 15px;
        font-weight: bold;
        min-width: 120px;
    }}

    QPushButton:hover {{
        background-color: {COLORS['accent_dark']};
        border-color: {COLORS['accent']};
        color: white;
    }}

    QPushButton:pressed {{
        background-color: {COLORS['accent']};
    }}

    QPushButton#primary {{
        background-color: {COLORS['accent_dark']};
        border-color: {COLORS['accent']};
        color: white;
    }}

    QPushButton#primary:hover {{
        background-color: {COLORS['accent']};
    }}

    QPushButton#danger {{
        background-color: #5c1a1a;
        border-color: {COLORS['danger']};
        color: {COLORS['danger']};
    }}

    QPushButton#danger:hover {{
        background-color: {COLORS['danger']};
        color: white;
    }}

    QPushButton#back {{
        background-color: transparent;
        border: 1px solid {COLORS['border']};
        color: {COLORS['text_secondary']};
        min-width: 80px;
        padding: 8px 16px;
        font-size: 13px;
    }}

    QPushButton#back:hover {{
        border-color: {COLORS['accent']};
        color: {COLORS['accent']};
    }}

    /* ── Inputs ──────────────────────────────────── */
    QLineEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {COLORS['bg_input']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 14px;
    }}

    QLineEdit:focus, QTextEdit:focus, QDateEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {COLORS['border_focus']};
    }}

    QDateEdit::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 28px;
        border-left: 1px solid {COLORS['border']};
        background-color: {COLORS['bg_surface']};
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }}

    QDateEdit::down-arrow {{
        image: none;
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {COLORS['accent']};
    }}

    QDateEdit::drop-down:hover {{
        background-color: {COLORS['accent_dark']};
    }}

    /* Calendar popup styling */
    QCalendarWidget {{
        background-color: {COLORS['bg_card']};
        color: {COLORS['text_primary']};
    }}

    QCalendarWidget QToolButton {{
        color: {COLORS['text_primary']};
        background-color: {COLORS['bg_surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 4px;
        padding: 4px 8px;
        min-width: 40px;
    }}

    QCalendarWidget QToolButton:hover {{
        background-color: {COLORS['accent_dark']};
    }}

    QCalendarWidget QAbstractItemView {{
        background-color: {COLORS['bg_card']};
        color: {COLORS['text_primary']};
        selection-background-color: {COLORS['accent_dark']};
        selection-color: white;
    }}

    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background-color: {COLORS['bg_surface']};
        border: 1px solid {COLORS['border']};
        width: 20px;
    }}

    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {COLORS['accent_dark']};
    }}

    /* ── Tables ──────────────────────────────────── */
    QTableWidget {{
        background-color: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        gridline-color: {COLORS['border']};
        selection-background-color: {COLORS['accent_dark']};
        selection-color: white;
    }}

    QTableWidget::item {{
        padding: 8px;
        border-bottom: 1px solid {COLORS['border']};
    }}

    QTableWidget::item:hover {{
        background-color: {COLORS['bg_surface']};
    }}

    QHeaderView::section {{
        background-color: {COLORS['bg_surface']};
        color: {COLORS['text_primary']};
        border: none;
        border-bottom: 2px solid {COLORS['accent']};
        padding: 10px 8px;
        font-weight: bold;
        font-size: 13px;
    }}

    /* ── List Widget ─────────────────────────────── */
    QListWidget {{
        background-color: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        outline: none;
    }}

    QListWidget::item {{
        padding: 12px;
        border-bottom: 1px solid {COLORS['border']};
        color: {COLORS['text_primary']};
    }}

    QListWidget::item:hover {{
        background-color: {COLORS['bg_surface']};
    }}

    QListWidget::item:selected {{
        background-color: {COLORS['accent_dark']};
        color: white;
    }}

    /* ── Scroll Bars ─────────────────────────────── */
    QScrollBar:vertical {{
        background-color: {COLORS['bg_dark']};
        width: 10px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {COLORS['border']};
        border-radius: 5px;
        min-height: 30px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {COLORS['text_muted']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: {COLORS['bg_dark']};
        height: 10px;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {COLORS['border']};
        border-radius: 5px;
        min-width: 30px;
    }}

    /* ── Frames / Cards ──────────────────────────── */
    QFrame#card {{
        background-color: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        padding: 16px;
    }}

    /* ── Group Box ───────────────────────────────── */
    QGroupBox {{
        background-color: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 24px;
        font-weight: bold;
        color: {COLORS['text_primary']};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 4px 12px;
        color: {COLORS['text_primary']};
    }}

    /* ── Status Bar ──────────────────────────────── */
    QStatusBar {{
        background-color: {COLORS['bg_card']};
        color: {COLORS['text_secondary']};
        border-top: 1px solid {COLORS['border']};
    }}
"""


def apply_theme(app):
    """Apply the dark medical theme to the QApplication."""
    app.setStyleSheet(STYLESHEET)
