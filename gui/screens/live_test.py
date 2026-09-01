"""
Live Test screen — real-time dual y-axis graphs with simulated data.
Strength is displayed as a constant label (isotonic).
After stopping, user chooses to Save or Discard test data.
"""

import time
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QFrame, QGroupBox, QFormLayout, QSplitter,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor
import pyqtgraph as pg

from theme import COLORS
from simulation import LiveDataGenerator
from utils import patch_all_axes


class LiveTestScreen(QWidget):
    """Live test screen with real-time updating graphs."""

    test_completed = Signal(int)  # emits session_id

    # Max points to show on live graph (rolling window)
    MAX_POINTS = 1500  # 30 seconds at 50 Hz

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.client_id = None
        self.session_id = None
        self.generator = None
        self.is_running = False
        self.elapsed_time = 0.0
        self.dt = 0.02  # 50 Hz → 20ms
        self.time_window = 10.0  # seconds visible on screen

        # Data buffers (kept until save/discard decision)
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_spo2_data = []

        # Rolling window buffers for live plotting
        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.spo2_data = []
        self.ticks = 0

        self._build_ui()
        self._setup_timer()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        # ── Header ─────────────────────────────────────────
        header_layout = QHBoxLayout()

        title = QLabel("Live Test")
        title.setObjectName("title")
        title.setStyleSheet(f"font-size: 22px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 6px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        title.setGraphicsEffect(shadow)
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.lbl_status = QLabel("IDLE")
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.lbl_status)

        layout.addLayout(header_layout)

        # ── Controls Panel ─────────────────────────────────
        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 12, 16, 12)

        # Test Parameters — only resistance (ROM is derived from data)
        params_group = QGroupBox("Test Parameters")
        params_form = QFormLayout(params_group)
        params_form.setSpacing(8)

        self.spin_resistance = QDoubleSpinBox()
        self.spin_resistance.setRange(0.0, 100.0)
        self.spin_resistance.setValue(10.0)
        self.spin_resistance.setSuffix(" lbs")
        self.spin_resistance.setMinimumHeight(36)
        params_form.addRow("Target Resistance:", self.spin_resistance)

        controls_layout.addWidget(params_group)

        # Strength display (constant, isotonic)
        strength_group = QGroupBox("Isotonic Strength")
        strength_layout = QVBoxLayout(strength_group)
        self.lbl_strength = QLabel("10.0 lbs")
        self.lbl_strength.setAlignment(Qt.AlignCenter)
        self.lbl_strength.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {COLORS['graph_strength']};
            padding: 8px;
        """)
        strength_layout.addWidget(self.lbl_strength)
        lbl_const = QLabel("(Constant Resistance)")
        lbl_const.setAlignment(Qt.AlignCenter)
        lbl_const.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        strength_layout.addWidget(lbl_const)
        controls_layout.addWidget(strength_group)

        self.spin_resistance.valueChanged.connect(
            lambda v: self.lbl_strength.setText(f"{v:.1f} lbs")
        )

        controls_layout.addStretch()

        # Start/Stop Button
        self.btn_start_stop = QPushButton("Start Test")
        self.btn_start_stop.setObjectName("primary")

        self.btn_start_stop.setMinimumHeight(56)
        self.btn_start_stop.setMinimumWidth(180)
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_start_stop.clicked.connect(self._toggle_test)
        controls_layout.addWidget(self.btn_start_stop)

        # Timer label
        self.lbl_timer = QLabel("0.0 s")
        self.lbl_timer.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 20px; font-weight: bold;")
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        self.lbl_timer.setMinimumWidth(100)
        controls_layout.addWidget(self.lbl_timer)

        layout.addWidget(controls)

        # ── Save / Discard bar (hidden by default) ─────────
        self.save_discard_bar = QFrame()
        self.save_discard_bar.setObjectName("card")
        sd_layout = QHBoxLayout(self.save_discard_bar)
        sd_layout.setContentsMargins(16, 10, 16, 10)

        sd_label = QLabel("Test complete — save this session?")
        sd_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: bold;")
        sd_layout.addWidget(sd_label)
        sd_layout.addStretch()

        self.btn_save = QPushButton("Save to Database")
        self.btn_save.setObjectName("primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setMinimumHeight(44)
        self.btn_save.setMinimumWidth(200)
        self.btn_save.clicked.connect(self._save_test)
        sd_layout.addWidget(self.btn_save)

        self.btn_discard = QPushButton("Discard")
        self.btn_discard.setObjectName("danger")
        self.btn_discard.setCursor(Qt.PointingHandCursor)
        self.btn_discard.setMinimumHeight(44)
        self.btn_discard.clicked.connect(self._discard_test)
        sd_layout.addWidget(self.btn_discard)

        self.save_discard_bar.setVisible(False)
        layout.addWidget(self.save_discard_bar)

        # ── Hint bar ───────────────────────────────────────
        hint = QLabel("Drag left/right axis to scale Y  |  Drag in graph to pan X  |  Scroll to zoom  |  Right-click to reset")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; padding: 2px 8px;")
        layout.addWidget(hint)

        # ── Graphs ─────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)
        pg.setConfigOptions(antialias=True)

        # Graph 1: Stacked ROM & Velocity vs Time
        self.graph_widget_1 = pg.GraphicsLayoutWidget()
        self.graph_widget_1.setBackground(COLORS['graph_bg'])

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


        splitter.addWidget(self.graph_widget_1)

        # Graph 2: SpO2 vs Time
        self.graph_widget_2 = pg.GraphicsLayoutWidget()
        self.graph_widget_2.setBackground(COLORS['graph_bg'])

        self.plot_spo2 = self.graph_widget_2.addPlot(row=0, col=0)
        self.plot_spo2.setTitle("SpO2 vs Time", color=COLORS['text_primary'], size="13pt")
        self.plot_spo2.setLabel('bottom', 'Time', units='s', color=COLORS['text_secondary'])
        self.plot_spo2.setLabel('left', 'SpO2 (%)', color=COLORS['graph_spo2'])
        self.plot_spo2.showGrid(x=True, y=True, alpha=0.2)
        self.plot_spo2.setYRange(92, 100)
        self.plot_spo2.getAxis('left').setPen(pg.mkPen(COLORS['graph_spo2']))
        self.plot_spo2.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_spo2']))
        self.plot_spo2.setMouseEnabled(x=True, y=True)
        self.plot_spo2.setMenuEnabled(True)

        self.curve_spo2 = self.plot_spo2.plot(
            pen=pg.mkPen(COLORS['graph_spo2'], width=2), name="SpO2"
        )

        patch_all_axes(self.plot_spo2)

        self._setup_crosshair()

        splitter.addWidget(self.graph_widget_2)
        splitter.setSizes([750, 250])

        layout.addWidget(splitter, stretch=1)

        # Set initial ranges appropriate for bicep curl time plots
        self.plot_rom.setXRange(0, self.time_window, padding=0)
        self.plot_rom.setYRange(-10, 180, padding=0)
        self.plot_vel.setYRange(-400, 400, padding=0)

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
        if not self.time_data:
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
        if not self.time_data:
            return
            
        pos = evt[0]
        in_spo2 = self.plot_spo2.sceneBoundingRect().contains(pos)
        
        if in_spo2:
            mousePoint = self.plot_spo2.vb.mapSceneToView(pos)
            self._update_crosshair(mousePoint.x())

    def _update_crosshair(self, x):
        t_arr = np.array(self.time_data)
        if len(t_arr) == 0:
            return
            
        idx = np.searchsorted(t_arr, x)
        if idx >= len(t_arr):
            idx = len(t_arr) - 1
        elif idx > 0:
            if abs(x - t_arr[idx-1]) < abs(x - t_arr[idx]):
                idx = idx - 1
                
        t_val = t_arr[idx]
        rom_val = self.rom_data[idx]
        vel_val = self.speed_data[idx]
        spo2_val = self.spo2_data[idx]
        
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

    def _setup_timer(self):
        """Create the QTimer for live data updates."""
        self.timer = QTimer(self)
        self.timer.setInterval(int(self.dt * 1000))  # 20ms
        self.timer.timeout.connect(self._update_data)

    def setup(self, client_id):
        """Prepare the screen for a new test."""
        self.client_id = client_id
        self._reset()

    def _reset(self):
        """Reset all data and graphs."""
        self.is_running = False
        self.elapsed_time = 0.0
        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.spo2_data = []
        self.session_id = None
        self.generator = None
        self.ticks = 0

        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_spo2_data = []

        self.curve_rom.setData([], [])
        self.curve_vel.setData([], [])
        self.curve_spo2.setData([], [])

        self.lbl_timer.setText("0.0 s")
        self.lbl_status.setText("IDLE")
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 16px; font-weight: bold;")
        self.btn_start_stop.setText("Start Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_start_stop.setVisible(True)
        self.save_discard_bar.setVisible(False)
        self.spin_resistance.setEnabled(True)

        # Reset default ranges
        self.plot_rom.setXRange(0, self.time_window, padding=0)
        self.plot_rom.setYRange(-10, 180, padding=0)
        self.plot_vel.setYRange(-400, 400, padding=0)
        self.plot_spo2.setYRange(92, 100, padding=0)

    def _toggle_test(self):
        if self.is_running:
            self._stop_test()
        else:
            self._start_test()

    def _start_test(self):
        """Begin a live test session."""
        target_resistance = self.spin_resistance.value()

        # Initialize generator (ROM is derived from data, not a target)
        self.generator = LiveDataGenerator(
            target_resistance=target_resistance,
        )

        # Update strength label
        self.lbl_strength.setText(f"{target_resistance:.1f} lbs")

        self.is_running = True
        self.spin_resistance.setEnabled(False)
        self.save_discard_bar.setVisible(False)

        # Clear previous data
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_spo2_data = []

        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.spo2_data = []
        self._start_time = time.time()
        self.elapsed_time = 0.0
        self.ticks = 0

        self.lbl_status.setText("RECORDING")
        self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px; font-weight: bold;")
        self.btn_start_stop.setText("Stop Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                background-color: #5c1a1a;
                border: 2px solid {COLORS['danger']};
                border-radius: 12px;
                color: {COLORS['danger']};
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: white;
            }}
        """)

        self.timer.start()

    def _stop_test(self):
        """Stop the live test — show save/discard options."""
        self.timer.stop()
        self.is_running = False

        self.lbl_status.setText("STOPPED - Save or Discard?")
        self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 16px; font-weight: bold;")

        # Hide start/stop, show save/discard
        self.btn_start_stop.setVisible(False)
        self.save_discard_bar.setVisible(True)
        self.spin_resistance.setEnabled(False)

    def _save_test(self):
        """Save the test data to the database."""
        if not self.full_time_data:
            self._discard_test()
            return

        target_resistance = self.spin_resistance.value()
        # Calculate observed max ROM from the data
        observed_max_rom = max(self.full_rom_data) if self.full_rom_data else 0.0

        # Create session and save data
        session_id = self.db.create_session(
            self.client_id, target_resistance, round(observed_max_rom, 1)
        )
        strength_data = [target_resistance] * len(self.full_time_data)
        self.db.save_test_data_batch(
            session_id,
            self.full_time_data,
            self.full_rom_data,
            self.full_speed_data,
            strength_data,
            self.full_spo2_data,
        )
        self.db.complete_session(session_id)

        self.lbl_status.setText("SAVED")
        self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px; font-weight: bold;")
        self.save_discard_bar.setVisible(False)
        self.btn_start_stop.setVisible(True)
        self.btn_start_stop.setText("Start New Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.spin_resistance.setEnabled(True)

        self.test_completed.emit(session_id)

    def _discard_test(self):
        """Discard the test data without saving."""
        self.lbl_status.setText("DISCARDED")
        self.lbl_status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 16px; font-weight: bold;")
        self.save_discard_bar.setVisible(False)
        self.btn_start_stop.setVisible(True)
        self.btn_start_stop.setText("Start New Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.spin_resistance.setEnabled(True)

        # Clear buffers
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_spo2_data = []

        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.spo2_data = []

    def _update_data(self):
        """Called every timer tick to generate and plot new data."""
        if not self.generator:
            return

        # Use system clock to prevent event-loop timing drift
        self.elapsed_time = time.time() - self._start_time

        rom, speed, spo2 = self.generator.next_sample(self.elapsed_time)

        self.full_time_data.append(self.elapsed_time)
        self.full_rom_data.append(rom)
        self.full_speed_data.append(speed)
        self.full_spo2_data.append(spo2)

        self.time_data.append(self.elapsed_time)
        self.rom_data.append(rom)
        self.speed_data.append(speed)
        self.spo2_data.append(spo2)

        self.ticks += 1

        # Rolling window
        if len(self.time_data) > self.MAX_POINTS:
            self.time_data = self.time_data[-self.MAX_POINTS:]
            self.rom_data = self.rom_data[-self.MAX_POINTS:]
            self.speed_data = self.speed_data[-self.MAX_POINTS:]
            self.spo2_data = self.spo2_data[-self.MAX_POINTS:]

        # Throttle GUI updates to ~16 Hz (every 3rd tick) to prevent event loop choking
        if self.ticks % 3 == 0:
            t = np.array(self.time_data)
            
            # Update stacked plots
            self.curve_rom.setData(t, np.array(self.rom_data))
            self.curve_vel.setData(t, np.array(self.speed_data))
    
            # Update SpO2 vs Time
            self.curve_spo2.setData(t, np.array(self.spo2_data))
    
            # Scroll X axis to show the time window
            if self.elapsed_time > self.time_window:
                x_min = self.elapsed_time - self.time_window
                x_max = self.elapsed_time
            else:
                x_min = 0
                x_max = self.time_window
                
            self.plot_rom.setXRange(x_min, x_max, padding=0)
            # self.plot_vel is XLinked to self.plot_rom, so it scrolls automatically
            self.plot_spo2.setXRange(x_min, x_max, padding=0)
    
            # Update timer label
            self.lbl_timer.setText(f"{self.elapsed_time:.1f} s")


