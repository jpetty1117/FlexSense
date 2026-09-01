"""
Create Client screen — form for adding a new client.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QDateEdit, QFrame, QFormLayout, QSpacerItem,
    QSizePolicy, QMessageBox, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt, QDate
from PySide6.QtGui import QColor
from theme import COLORS


class CreateClientScreen(QWidget):
    """Form to create a new client and save to database."""

    client_created = Signal(int)  # emits new client_id

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        # ── Header ─────────────────────────────────────────
        title = QLabel("Create New Client")
        title.setObjectName("title")
        title.setStyleSheet(f"font-size: 24px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 6px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        title.setGraphicsEffect(shadow)
        layout.addWidget(title)

        # ── Form Card ──────────────────────────────────────
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(20)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)

        # Name
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Enter client full name...")
        self.input_name.setMinimumHeight(40)
        name_label = QLabel("Full Name:")
        name_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        form.addRow(name_label, self.input_name)

        # Date of Birth
        self.input_dob = QDateEdit()
        self.input_dob.setCalendarPopup(True)
        self.input_dob.setDate(QDate(1990, 1, 1))
        self.input_dob.setDisplayFormat("MM-dd-yyyy")
        self.input_dob.setMinimumHeight(40)
        dob_label = QLabel("Date of Birth:")
        dob_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        form.addRow(dob_label, self.input_dob)

        # Notes
        self.input_notes = QTextEdit()
        self.input_notes.setPlaceholderText("Injury description, rehab goals, etc...")
        self.input_notes.setMaximumHeight(120)
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        form.addRow(notes_label, self.input_notes)

        card_layout.addLayout(form)
        layout.addWidget(card)

        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # ── Save button ───────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_save = QPushButton("Save Client")
        btn_save.setObjectName("primary")

        btn_save.setMinimumHeight(48)
        btn_save.setMinimumWidth(200)
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _on_save(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Client name is required.")
            return

        dob = self.input_dob.date().toString("MM-dd-yyyy")
        notes = self.input_notes.toPlainText().strip()

        client_id = self.db.create_client(name, dob, notes)
        self.client_created.emit(client_id)

    def reset_form(self):
        """Clear all form fields."""
        self.input_name.clear()
        self.input_dob.setDate(QDate(1990, 1, 1))
        self.input_notes.clear()
