"""
History Viewer screen — displays historical test sessions and their data.
Strength is displayed as a constant label (isotonic).
Axis scaling via drag on axes, panning via drag in graph (native pyqtgraph).
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QFrame, QGroupBox,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
import pyqtgraph as pg

from theme import COLORS
from utils import patch_all_axes


class HistoryViewerScreen(QWidget):
    """View historical test sessions and their graph data."""



    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.client_id = None
        self.sessions = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        # ── Header ─────────────────────────────────────────
        header_layout = QHBoxLayout()

        self.title_label = QLabel("Test History")
        self.title_label.setObjectName("title")
        self.title_label.setStyleSheet(f"font-size: 22px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 6px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.title_label.setGraphicsEffect(shadow)
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Hint
        hint = QLabel("Drag left/right axis to scale Y  |  Drag in graph to pan X  |  Scroll to zoom  |  Right-click to reset")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        header_layout.addWidget(hint)

        layout.addLayout(header_layout)

        # ── Main Content (splitter: session list | graphs) ─
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)

        # Left: Session list + info
        self.left_panel = QFrame()
        self.left_panel.setObjectName("card")
        self.left_panel.setFixedWidth(250)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        lbl_sessions = QLabel("Sessions")
        lbl_sessions.setObjectName("section_header")
        left_layout.addWidget(lbl_sessions)

        self.session_list = QListWidget()
        self.session_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self.session_list)

        # Session info section
        self.lbl_session_info = QLabel("")
        self.lbl_session_info.setWordWrap(True)
        self.lbl_session_info.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            padding: 8px;
            background-color: {COLORS['bg_surface']};
            border-radius: 6px;
        """)
        left_layout.addWidget(self.lbl_session_info)

        # Strength indicator (isotonic constant)
        strength_box = QGroupBox("Isotonic Strength")
        strength_box_layout = QVBoxLayout(strength_box)
        self.lbl_strength = QLabel("— lbs")
        self.lbl_strength.setAlignment(Qt.AlignCenter)
        self.lbl_strength.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['graph_strength']};
            padding: 6px;
        """)
        strength_box_layout.addWidget(self.lbl_strength)
        lbl_const = QLabel("(Constant Resistance)")
        lbl_const.setAlignment(Qt.AlignCenter)
        lbl_const.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        strength_box_layout.addWidget(lbl_const)
        left_layout.addWidget(strength_box)

        content_layout.addWidget(self.left_panel)

        # Toggle Button
        from PySide6.QtWidgets import QSizePolicy
        self.btn_toggle_sessions = QPushButton("◀")
        self.btn_toggle_sessions.setFixedWidth(24)
        self.btn_toggle_sessions.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_toggle_sessions.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_sessions.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_muted']};
                border: 1px solid {COLORS['border']};
                border-left: none;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                font-weight: bold;
                font-size: 14px;
                min-width: 0px;
                max-width: 24px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_dark']};
                color: {COLORS['accent']};
            }}
        """)
        self.btn_toggle_sessions.clicked.connect(self._toggle_sessions)
        content_layout.addWidget(self.btn_toggle_sessions)

        # Right: Graphs
        right_panel = QWidget()
        right_panel.setContentsMargins(6, 0, 0, 0)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        pg.setConfigOptions(antialias=True)

        # Graph 1: Stacked ROM & Velocity vs Time
        self.graph_widget_1 = pg.GraphicsLayoutWidget()
        self.graph_widget_1.setBackground(COLORS['graph_bg'])

        # Top Plot: ROM
        self.plot_rom = self.graph_widget_1.addPlot(row=0, col=0)
        self.plot_rom.setTitle("ROM vs Time", color=COLORS['text_primary'], size="13pt")
        self.plot_rom.setLabel('left', 'ROM (°)', color=COLORS['graph_rom'])
        self.plot_rom.showGrid(x=True, y=True, alpha=0.2)
        self.plot_rom.getAxis('left').setPen(pg.mkPen(COLORS['graph_rom']))
        self.plot_rom.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_rom']))
        self.plot_rom.setMouseEnabled(x=True, y=True)
        self.plot_rom.setMenuEnabled(True)

        self.curve_rom = self.plot_rom.plot(
            pen=pg.mkPen(COLORS['graph_rom'], width=2), name="ROM"
        )
        patch_all_axes(self.plot_rom)

        self.graph_widget_1.nextRow()

        # Bottom Plot: Velocity
        self.plot_vel = self.graph_widget_1.addPlot(row=1, col=0)
        self.plot_vel.setTitle("Velocity vs Time", color=COLORS['text_primary'], size="13pt")
        self.plot_vel.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
        self.plot_vel.setLabel('left', 'Velocity (°/s)', color=COLORS['graph_speed'])
        self.plot_vel.showGrid(x=True, y=True, alpha=0.2)
        self.plot_vel.getAxis('bottom').setPen(pg.mkPen(COLORS['text_secondary']))
        self.plot_vel.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_secondary']))
        self.plot_vel.getAxis('left').setPen(pg.mkPen(COLORS['graph_speed']))
        self.plot_vel.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_speed']))
        self.plot_vel.setMouseEnabled(x=True, y=True)
        self.plot_vel.setMenuEnabled(True)

        self.plot_vel.setXLink(self.plot_rom)

        self.curve_vel = self.plot_vel.plot(
            pen=pg.mkPen(COLORS['graph_speed'], width=2), name="Velocity"
        )
        patch_all_axes(self.plot_vel)


        right_layout.addWidget(self.graph_widget_1, stretch=3)

        # Graph 2: SpO2 vs Time
        self.graph_widget_2 = pg.GraphicsLayoutWidget()
        self.graph_widget_2.setBackground(COLORS['graph_bg'])

        self.plot_spo2 = self.graph_widget_2.addPlot(row=0, col=0)
        self.plot_spo2.setTitle("SpO2 vs Time", color=COLORS['text_primary'], size="13pt")
        self.plot_spo2.setLabel('bottom', 'Time', units='s', color=COLORS['text_secondary'])
        self.plot_spo2.setLabel('left', 'SpO2 (%)', color=COLORS['graph_spo2'])
        self.plot_spo2.showGrid(x=True, y=True, alpha=0.2)
        self.plot_spo2.getAxis('left').setPen(pg.mkPen(COLORS['graph_spo2']))
        self.plot_spo2.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_spo2']))
        self.plot_spo2.setMouseEnabled(x=True, y=True)
        self.plot_spo2.setMenuEnabled(True)

        self.curve_spo2 = self.plot_spo2.plot(
            pen=pg.mkPen(COLORS['graph_spo2'], width=2), name="SpO2"
        )

        patch_all_axes(self.plot_spo2)

        self._setup_crosshair()

        right_layout.addWidget(self.graph_widget_2, stretch=1)

        content_layout.addWidget(right_panel, stretch=1)

        layout.addLayout(content_layout, stretch=1)

    def _toggle_sessions(self):
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        if hasattr(self, '_anim') and self._anim is not None:
            self._anim.stop()
            self._anim_min.stop()

        if self.left_panel.width() > 0:
            target_width = 0
            self.btn_toggle_sessions.setText("▶")
        else:
            target_width = 250
            self.btn_toggle_sessions.setText("◀")

        self._anim = QPropertyAnimation(self.left_panel, b"maximumWidth")
        self._anim.setDuration(250)
        self._anim.setStartValue(self.left_panel.width())
        self._anim.setEndValue(target_width)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim_min = QPropertyAnimation(self.left_panel, b"minimumWidth")
        self._anim_min.setDuration(250)
        self._anim_min.setStartValue(self.left_panel.width())
        self._anim_min.setEndValue(target_width)
        self._anim_min.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim.start()
        self._anim_min.start()

    def _setup_crosshair(self):
        pen = pg.mkPen(COLORS['accent'], style=Qt.DashLine)
        self.vLine_rom = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_rom = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.vLine_vel = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_vel = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.vLine_spo2 = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_spo2 = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        
        self.plot_rom.addItem(self.vLine_rom, ignoreBounds=True)
        self.plot_rom.addItem(self.hLine_rom, ignoreBounds=True)
        self.plot_vel.addItem(self.vLine_vel, ignoreBounds=True)
        self.plot_vel.addItem(self.hLine_vel, ignoreBounds=True)
        self.plot_spo2.addItem(self.vLine_spo2, ignoreBounds=True)
        self.plot_spo2.addItem(self.hLine_spo2, ignoreBounds=True)
        
        bg_color = QColor(COLORS['bg_surface'])
        bg_color.setAlpha(180)
        
        self.label_rom = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_rom.addItem(self.label_rom, ignoreBounds=True)
        self.label_vel = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_vel.addItem(self.label_vel, ignoreBounds=True)
        self.label_spo2 = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_spo2.addItem(self.label_spo2, ignoreBounds=True)
        
        self.proxy_1 = pg.SignalProxy(self.graph_widget_1.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_1)
        self.proxy_2 = pg.SignalProxy(self.graph_widget_2.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_2)

    def _mouse_moved_1(self, evt):
        if not hasattr(self, 'current_time_data') or self.current_time_data is None or len(self.current_time_data) == 0:
            return
            
        pos = evt[0]
        in_rom = self.plot_rom.sceneBoundingRect().contains(pos)
        in_vel = self.plot_vel.sceneBoundingRect().contains(pos)
        
        if in_rom:
            mousePoint = self.plot_rom.vb.mapSceneToView(pos)
            self._update_crosshair(mousePoint.x())
        elif in_vel:
            mousePoint = self.plot_vel.vb.mapSceneToView(pos)
            self._update_crosshair(mousePoint.x())

    def _mouse_moved_2(self, evt):
        if not hasattr(self, 'current_time_data') or self.current_time_data is None or len(self.current_time_data) == 0:
            return
            
        pos = evt[0]
        in_spo2 = self.plot_spo2.sceneBoundingRect().contains(pos)
        
        if in_spo2:
            mousePoint = self.plot_spo2.vb.mapSceneToView(pos)
            self._update_crosshair(mousePoint.x())

    def _update_crosshair(self, x):
        t_arr = self.current_time_data
        if len(t_arr) == 0:
            return
            
        idx = np.searchsorted(t_arr, x)
        if idx >= len(t_arr):
            idx = len(t_arr) - 1
        elif idx > 0:
            if abs(x - t_arr[idx-1]) < abs(x - t_arr[idx]):
                idx = idx - 1
                
        t_val = t_arr[idx]
        rom_val = self.current_rom_data[idx]
        vel_val = self.current_vel_data[idx]
        spo2_val = self.current_spo2_data[idx]
        
        self.vLine_rom.setPos(t_val)
        self.vLine_vel.setPos(t_val)
        self.vLine_spo2.setPos(t_val)
        self.hLine_rom.setPos(rom_val)
        self.hLine_vel.setPos(vel_val)
        self.hLine_spo2.setPos(spo2_val)
        
        # Calculate dynamic anchors to prevent text from disappearing off-screen
        x_range = self.plot_rom.viewRange()[0]
        y_range_rom = self.plot_rom.viewRange()[1]
        y_range_vel = self.plot_vel.viewRange()[1]
        y_range_spo2 = self.plot_spo2.viewRange()[1]

        # Horizontal: flip text to left side of crosshair if past the midway point
        anchor_x = 1 if t_val > x_range[0] + (x_range[1] - x_range[0]) / 2 else 0
        
        # Vertical ROM: draw above point if in lower half, below if in upper half
        anchor_y_rom = 1 if rom_val < y_range_rom[0] + (y_range_rom[1] - y_range_rom[0]) / 2 else 0
        
        # Vertical Vel: draw above point if in lower half, below if in upper half
        anchor_y_vel = 1 if vel_val < y_range_vel[0] + (y_range_vel[1] - y_range_vel[0]) / 2 else 0

        # Vertical SpO2: draw above point if in lower half, below if in upper half
        anchor_y_spo2 = 1 if spo2_val < y_range_spo2[0] + (y_range_spo2[1] - y_range_spo2[0]) / 2 else 0

        self.label_rom.setAnchor((anchor_x, anchor_y_rom))
        self.label_rom.setText(f"Time: {t_val:.1f}s\nROM: {rom_val:.1f}°")
        self.label_rom.setPos(t_val, rom_val)
        
        self.label_vel.setAnchor((anchor_x, anchor_y_vel))
        self.label_vel.setText(f"Time: {t_val:.1f}s\nVel: {vel_val:.1f}°/s")
        self.label_vel.setPos(t_val, vel_val)

        self.label_spo2.setAnchor((anchor_x, anchor_y_spo2))
        self.label_spo2.setText(f"Time: {t_val:.1f}s\nSpO2: {spo2_val:.1f}%")
        self.label_spo2.setPos(t_val, spo2_val)



    def load_client(self, client_id):
        """Load session history for a client."""
        self.client_id = client_id
        client = self.db.get_client(client_id)
        if client:
            self.title_label.setText(f"Test History — {client['name']}")

        self.sessions = self.db.get_sessions(client_id)
        self.session_list.clear()

        total = len(self.sessions)
        for i, session in enumerate(self.sessions):
            # Sessions are newest-first; #1 = oldest, #total = newest
            session_num = total - i
            date_str = session['date'][:10] if session['date'] else 'Unknown'
            item_text = (
                f"Session #{session_num} — {date_str}\n"
                f"  Resistance: {session['target_resistance']} lbs | "
                f"Max ROM: {session['target_angle']}°"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, session['id'])
            self.session_list.addItem(item)

        # Clear graphs
        self.curve_rom.setData([], [])
        self.curve_vel.setData([], [])
        self.curve_spo2.setData([], [])
        self.current_time_data = []
        self.current_rom_data = []
        self.current_vel_data = []
        self.current_spo2_data = []
        self.lbl_session_info.setText("Select a session to view its data.")
        self.lbl_strength.setText("— lbs")

        # Auto-select first
        if self.sessions:
            self.session_list.setCurrentRow(0)

    def _on_session_selected(self, row):
        """Load and display data for the selected session."""
        if row < 0 or row >= len(self.sessions):
            return

        session = self.sessions[row]
        session_id = session['id']

        # Update session info
        self.lbl_session_info.setText(
            f"Date: {session['date'][:19]}\n"
            f"Target Resistance: {session['target_resistance']} lbs\n"
            f"Max ROM: {session['target_angle']}°\n"
            f"Status: {session.get('status', 'N/A')}\n"
            f"Notes: {session.get('notes', 'N/A')}"
        )

        # Update strength label (constant isotonic value)
        self.lbl_strength.setText(f"{session['target_resistance']} lbs")

        # Load test data
        data_rows = self.db.get_session_data(session_id)

        if not data_rows:
            self.curve_rom.setData([], [])
            self.curve_vel.setData([], [])
            self.curve_spo2.setData([], [])
            self.current_time_data = []
            self.current_spo2_data = []
            return

        timestamps = np.array([r['timestamp_s'] for r in data_rows])
        rom = np.array([r['rom_angle'] for r in data_rows])
        speed = np.array([r['speed'] for r in data_rows])
        spo2 = np.array([r['spo2'] for r in data_rows])

        self.current_time_data = timestamps
        self.current_rom_data = rom
        self.current_vel_data = speed
        self.current_spo2_data = spo2

        # Update stacked graphs
        self.curve_rom.setData(timestamps, rom)
        self.curve_vel.setData(timestamps, speed)

        # Set sensible default ranges
        self.plot_rom.setXRange(float(timestamps[0]), float(timestamps[-1]), padding=0)
        self.plot_rom.setYRange(-10, float(session['target_angle']) + 20, padding=0)
        
        speed_abs_max = max(abs(float(speed.min())), abs(float(speed.max())))
        self.plot_vel.setYRange(-speed_abs_max * 1.1, speed_abs_max * 1.1, padding=0)

        # Update graph 2
        self.curve_spo2.setData(timestamps, spo2)
        self.plot_spo2.setXRange(float(timestamps[0]), float(timestamps[-1]))
        self.plot_spo2.setYRange(
            max(90, float(spo2.min()) - 1),
            min(100, float(spo2.max()) + 1),
            padding=0,
        )
