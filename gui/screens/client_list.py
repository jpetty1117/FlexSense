"""
Client List screen — displays all clients from the database.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from theme import COLORS


class ClientListScreen(QWidget):
    """Table of all clients with selection support."""

    client_selected = Signal(int)  # emits client_id

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        # ── Header ─────────────────────────────────────────
        title = QLabel("Select Client")
        title.setObjectName("title")
        title.setStyleSheet(f"font-size: 24px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 6px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        title.setGraphicsEffect(shadow)
        layout.addWidget(title)

        # ── Table ──────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Date of Birth", "Notes"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                alternate-background-color: {COLORS['bg_surface']};
            }}
        """)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

        # ── Select button ─────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_select = QPushButton("Open Client Dashboard →")
        btn_select.setObjectName("primary")

        btn_select.setMinimumHeight(44)
        btn_select.clicked.connect(self._on_select_clicked)
        btn_layout.addWidget(btn_select)

        layout.addLayout(btn_layout)

    def refresh(self):
        """Reload client data from the database."""
        clients = self.db.get_clients()
        self.table.setRowCount(len(clients))

        for row, client in enumerate(clients):
            self.table.setItem(row, 0, QTableWidgetItem(str(client["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(client["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(client.get("dob", "")))
            self.table.setItem(row, 3, QTableWidgetItem(client.get("notes", "")))

        # Auto-select first row
        if len(clients) > 0:
            self.table.selectRow(0)

    def _on_row_double_clicked(self, index):
        row = index.row()
        client_id = int(self.table.item(row, 0).text())
        self.client_selected.emit(client_id)

    def _on_select_clicked(self):
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            client_id = int(self.table.item(row, 0).text())
            self.client_selected.emit(client_id)
