"""
Rehab Test System — Main Application Entry Point

PySide6 + PyQtGraph + SQLite rehabilitation testing GUI.
Persistent left sidebar for navigation.
"""

import sys
import os

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QSpacerItem, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor

from theme import apply_theme, COLORS
from database import Database

from screens.client_list import ClientListScreen
from screens.create_client import CreateClientScreen
from screens.client_dashboard import ClientDashboardScreen
from screens.live_test import LiveTestScreen
from screens.history_viewer import HistoryViewerScreen


# ── Screen indices ───────────────────────────────────────────
SCREEN_CLIENT_LIST = 0
SCREEN_CREATE_CLIENT = 1
SCREEN_CLIENT_DASHBOARD = 2
SCREEN_LIVE_TEST = 3
SCREEN_HISTORY_VIEWER = 4


class RehabTestApp(QMainWindow):
    """Main application window with persistent sidebar navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rehab Test System")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Track active client
        self._active_client_id = None
        self._active_client_name = None

        # Sidebar state
        self._sidebar_expanded = True
        self._sidebar_width_expanded = 220
        self._sidebar_width_collapsed = 50

        # ── Database ─────────────────────────────────────
        self.db = Database()
        self.db.seed_dummy_data()

        # ── Central widget: sidebar + content ────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Build sidebar
        root_layout.addWidget(self._build_sidebar())

        # Build content stack
        self.stack = QStackedWidget()
        self._create_screens()
        root_layout.addWidget(self.stack, stretch=1)

        # ── Connect Signals ──────────────────────────────
        self._connect_signals()

        # Start on client list
        self._goto_client_list()

    # ─────────────────────────────────────────────────────
    # Sidebar
    # ─────────────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(self._sidebar_width_expanded)
        self.sidebar.setStyleSheet(f"""
            QFrame#sidebar {{
                background-color: {COLORS['bg_card']};
                border-right: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toggle Row ───────────────────────
        title_frame = QFrame()
        title_frame.setFixedHeight(64)
        title_frame.setStyleSheet(f"""
            background-color: {COLORS['bg_surface']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        title_outer = QHBoxLayout(title_frame)
        title_outer.setContentsMargins(0, 0, 0, 0)
        title_outer.setSpacing(0)

        # Toggle button
        self.btn_toggle = QPushButton("☰")
        self.btn_toggle.setFixedSize(50, 64)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._toggle_sidebar)
        title_outer.addWidget(self.btn_toggle)
        title_outer.addStretch()

        layout.addWidget(title_frame)

        # ── Nav section label ────────────────────────────
        self._lbl_nav = self._section_label("NAVIGATION")
        layout.addWidget(self._lbl_nav)

        # ── Main nav buttons ─────────────────────────────
        self.btn_clients = self._nav_button("Clients", self._goto_client_list)
        layout.addWidget(self.btn_clients)

        self.btn_new_client = self._nav_button("New Client", self._goto_create_client)
        layout.addWidget(self.btn_new_client)

        # ── Active client section ────────────────────────
        self.client_section = QWidget()
        client_layout = QVBoxLayout(self.client_section)
        client_layout.setContentsMargins(0, 0, 0, 0)
        client_layout.setSpacing(0)

        self._lbl_active_section = self._section_label("ACTIVE CLIENT")
        client_layout.addWidget(self._lbl_active_section)

        self.lbl_active_client = QLabel("  No client selected")
        self.lbl_active_client.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
            padding: 8px 16px;
            background: transparent;
        """)
        client_layout.addWidget(self.lbl_active_client)

        self.btn_dashboard = self._nav_button("Dashboard", self._goto_dashboard_current)
        client_layout.addWidget(self.btn_dashboard)

        self.btn_test = self._nav_button("Start Test", self._goto_live_test_current)
        client_layout.addWidget(self.btn_test)

        self.btn_history = self._nav_button("View History", self._goto_history_current)
        client_layout.addWidget(self.btn_history)

        # Initially hide client-specific buttons
        self.btn_dashboard.setVisible(False)
        self.btn_test.setVisible(False)
        self.btn_history.setVisible(False)

        layout.addWidget(self.client_section)

        # ── Spacer ───────────────────────────────────────
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # ── Version + Quit ───────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"color: {COLORS['border']}; background: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(divider)

        self.btn_quit = self._nav_button("Quit", self._shutdown)
        self.btn_quit.setStyleSheet(f"""
            QPushButton {{
                color: {COLORS['danger']};
                text-align: left;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 0;
                background: transparent;
                min-width: 0;
            }}
            QPushButton:hover {{
                background-color: #5c1a1a;
                color: {COLORS['danger']};
            }}
        """)
        layout.addWidget(self.btn_quit)

        self._version_label = QLabel("v0.1.0 - POC")
        self._version_label.setAlignment(Qt.AlignCenter)
        self._version_label.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 10px;
            padding: 8px;
            background: transparent;
        """)
        layout.addWidget(self._version_label)

        # Store all nav buttons for active highlighting
        self._nav_buttons = [
            self.btn_clients, self.btn_new_client,
            self.btn_dashboard, self.btn_test, self.btn_history,
        ]

        # Collapsible widgets (hidden when sidebar is collapsed)
        self._collapsible_widgets = [
            self._lbl_nav,
            self.lbl_active_client, self._lbl_active_section,
            self._version_label,
        ]

        self._update_toggle_style(True)  # Set initial styles
        return self.sidebar

    def _nav_button(self, text, callback):
        """Create a sidebar navigation button."""
        btn = QPushButton(text)

        btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLORS['text_secondary']};
                text-align: left;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 0;
                background: transparent;
                min-width: 0;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_primary']};
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _section_label(self, text):
        """Create a small section label for the sidebar."""
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 12px 16px 4px 16px;
            background: transparent;
        """)
        return lbl

    # ─────────────────────────────────────────────────────
    # Sidebar Toggle
    # ─────────────────────────────────────────────────────
    def _update_toggle_style(self, is_expanded):
        """Update the styling of the toggle button based on collapse state."""
        self.btn_toggle.setText("☰")
        if is_expanded:
            # ☰: Nice flat square button when nav is open
            bg_color = "transparent"
            border_color = "transparent"
            text_color = COLORS['text_primary']
            hover_bg = COLORS['bg_surface']
            hover_border = COLORS['border']
            hover_text = COLORS['accent']
            border_radius_css = "border-radius: 0px;"
            font_size = "20px"
        else:
            # ☰: Distinctive blue tab when sidebar is closed
            bg_color = COLORS['accent_dark']
            border_color = COLORS['accent']
            text_color = "white"
            hover_bg = COLORS['accent']
            hover_border = COLORS['accent_hover']
            hover_text = "white"
            border_radius_css = """
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            """
            font_size = "20px"

        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                {border_radius_css}
                font-size: {font_size};
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: {hover_border};
                color: {hover_text};
            }}
        """)

    def _toggle_sidebar(self):
        """Animate sidebar between expanded and collapsed states."""
        self.btn_toggle.setText("☰")
        
        if hasattr(self, '_anim') and self._anim is not None:
            self._anim.stop()
            self._anim_min.stop()

        if self._sidebar_expanded:
            target_width = self._sidebar_width_collapsed
            self._update_toggle_style(False)
            # Hide text before collapse starts to prevent overflow
            self._hide_widgets()
        else:
            target_width = self._sidebar_width_expanded
            self._update_toggle_style(True)

        self._anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self._anim.setDuration(250)
        self._anim.setStartValue(self.sidebar.width())
        self._anim.setEndValue(target_width)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim_min = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self._anim_min.setDuration(250)
        self._anim_min.setStartValue(self.sidebar.width())
        self._anim_min.setEndValue(target_width)
        self._anim_min.setEasingCurve(QEasingCurve.InOutCubic)

        # Show text after expand completes
        if not self._sidebar_expanded:
            self._anim.finished.connect(self._show_widgets)

        self._sidebar_expanded = not self._sidebar_expanded
        self._anim.start()
        self._anim_min.start()

    def _hide_widgets(self):
        """Hide text widgets for collapse."""
        for w in self._collapsible_widgets:
            w.setVisible(False)
        for btn in self._nav_buttons:
            if not btn.property("full_text"):
                btn.setProperty("full_text", btn.text())
            full = btn.property("full_text")
            btn.setText(full[0] if full else "")
            
        if not self.btn_quit.property("full_text"):
            self.btn_quit.setProperty("full_text", self.btn_quit.text())
        self.btn_quit.setText("Q")

    def _show_widgets(self):
        """Show text widgets after expand."""
        for w in self._collapsible_widgets:
            w.setVisible(True)
        for btn in self._nav_buttons:
            full = btn.property("full_text")
            if full:
                btn.setText(full)
        full_quit = self.btn_quit.property("full_text")
        if full_quit:
            self.btn_quit.setText(full_quit)

    def _set_active_button(self, active_btn):
        """Highlight the active nav button."""
        for btn in self._nav_buttons:
            btn.setGraphicsEffect(None)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {COLORS['text_secondary']};
                    text-align: left;
                    padding: 12px 20px;
                    font-size: 13px;
                    font-weight: bold;
                    border: none;
                    border-radius: 0;
                    background: transparent;
                    min-width: 0;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_primary']};
                }}
            """)
        if active_btn:
            active_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {COLORS['text_primary']};
                    text-align: left;
                    padding: 12px 20px 10px 20px;
                    font-size: 13px;
                    font-weight: bold;
                    border: none;
                    border-bottom: 2px solid {COLORS['accent']};
                    border-radius: 0;
                    background-color: {COLORS['bg_surface']};
                    min-width: 0;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_primary']};
                }}
            """)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 100))
            active_btn.setGraphicsEffect(shadow)

    # ─────────────────────────────────────────────────────
    # Screens
    # ─────────────────────────────────────────────────────
    def _create_screens(self):
        self.client_list = ClientListScreen(self.db)
        self.create_client = CreateClientScreen(self.db)
        self.client_dashboard = ClientDashboardScreen(self.db)
        self.live_test = LiveTestScreen(self.db)
        self.history_viewer = HistoryViewerScreen(self.db)

        self.stack.addWidget(self.client_list)        # 0
        self.stack.addWidget(self.create_client)       # 1
        self.stack.addWidget(self.client_dashboard)    # 2
        self.stack.addWidget(self.live_test)            # 3
        self.stack.addWidget(self.history_viewer)       # 4

    def _connect_signals(self):
        # Client List → select a client
        self.client_list.client_selected.connect(self._on_client_selected)

        # Create Client → client created
        self.create_client.client_created.connect(self._on_client_created)

        # Live Test → test completed
        self.live_test.test_completed.connect(self._on_test_completed)

    # ─────────────────────────────────────────────────────
    # Active Client Management
    # ─────────────────────────────────────────────────────
    def _set_active_client(self, client_id):
        """Set the active client and update sidebar."""
        self._active_client_id = client_id
        client = self.db.get_client(client_id)
        if client:
            self._active_client_name = client['name']
            self.lbl_active_client.setText(f"  {client['name']}")
            self.lbl_active_client.setStyleSheet(f"""
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
                background: transparent;
            """)
        self.btn_dashboard.setVisible(True)
        self.btn_test.setVisible(True)
        self.btn_history.setVisible(True)

    # ─────────────────────────────────────────────────────
    # Navigation Handlers
    # ─────────────────────────────────────────────────────
    def _goto_client_list(self):
        self.client_list.refresh()
        self.stack.setCurrentIndex(SCREEN_CLIENT_LIST)
        self._set_active_button(self.btn_clients)

    def _goto_create_client(self):
        self.create_client.reset_form()
        self.stack.setCurrentIndex(SCREEN_CREATE_CLIENT)
        self._set_active_button(self.btn_new_client)

    def _goto_dashboard_current(self):
        if self._active_client_id:
            self.client_dashboard.load_client(self._active_client_id)
            self.stack.setCurrentIndex(SCREEN_CLIENT_DASHBOARD)
            self._set_active_button(self.btn_dashboard)

    def _goto_live_test_current(self):
        if self._active_client_id:
            self.live_test.setup(self._active_client_id)
            self.stack.setCurrentIndex(SCREEN_LIVE_TEST)
            self._set_active_button(self.btn_test)

    def _goto_history_current(self):
        if self._active_client_id:
            self.history_viewer.load_client(self._active_client_id)
            self.stack.setCurrentIndex(SCREEN_HISTORY_VIEWER)
            self._set_active_button(self.btn_history)

    # ── Signal Handlers ──────────────────────────────────
    def _on_client_selected(self, client_id):
        self._set_active_client(client_id)
        self._goto_dashboard_current()

    def _on_client_created(self, client_id):
        self._set_active_client(client_id)
        self._goto_dashboard_current()

    def _on_test_completed(self, session_id):
        pass  # Data is already saved; user can navigate via sidebar

    def _shutdown(self):
        self.db.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        self.db.close()
        event.accept()


def main():
    app = QApplication(sys.argv)

    font = QFont("Helvetica", 11)
    app.setFont(font)

    apply_theme(app)

    window = RehabTestApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
