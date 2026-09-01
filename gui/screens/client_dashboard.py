"""
Client Dashboard screen — shows client info (read-only).
Navigation via sidebar; no action buttons here.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QFrame, QSpacerItem, QSizePolicy, QGridLayout,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from theme import COLORS


class ClientDashboardScreen(QWidget):
    """Dashboard showing client info."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.client_id = None
        self.client = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # ── Header ─────────────────────────────────────────
        self.title_label = QLabel("Client Dashboard")
        self.title_label.setObjectName("title")
        self.title_label.setStyleSheet(f"font-size: 24px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 6px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.title_label.setGraphicsEffect(shadow)
        layout.addWidget(self.title_label)

        # ── Client Info Card ───────────────────────────────
        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(24, 20, 24, 20)
        info_layout.setSpacing(12)

        def make_label(text, obj_name=None):
            lbl = QLabel(text)
            if obj_name:
                lbl.setObjectName(obj_name)
            return lbl

        info_layout.addWidget(make_label("Name:", "section_header"), 0, 0)
        self.lbl_name = make_label("—", "client_info")
        info_layout.addWidget(self.lbl_name, 0, 1)

        info_layout.addWidget(make_label("Date of Birth:", "section_header"), 1, 0)
        self.lbl_dob = make_label("—", "client_info")
        info_layout.addWidget(self.lbl_dob, 1, 1)

        info_layout.addWidget(make_label("Notes:", "section_header"), 2, 0)
        self.lbl_notes = make_label("—", "client_info")
        self.lbl_notes.setWordWrap(True)
        info_layout.addWidget(self.lbl_notes, 2, 1)

        info_layout.addWidget(make_label("Total Sessions:", "section_header"), 3, 0)
        self.lbl_sessions = make_label("—", "client_info")
        info_layout.addWidget(self.lbl_sessions, 3, 1)

        info_layout.setColumnStretch(1, 1)
        layout.addWidget(info_card)

        # ── Hint ───────────────────────────────────────────
        hint = QLabel("Use the sidebar to start a test or view session history for this client.")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px; padding: 8px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def load_client(self, client_id):
        """Load and display client data."""
        self.client_id = client_id
        self.client = self.db.get_client(client_id)

        if self.client:
            self.title_label.setText(f"Client Dashboard — {self.client['name']}")
            self.lbl_name.setText(self.client["name"])
            self.lbl_dob.setText(self.client.get("dob", "N/A"))
            self.lbl_notes.setText(self.client.get("notes", "No notes"))

            sessions = self.db.get_sessions(client_id)
            self.lbl_sessions.setText(str(len(sessions)))
