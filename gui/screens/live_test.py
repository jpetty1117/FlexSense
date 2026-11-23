"""
Texas A&M University
Electronic Systems Engineering Technology
ESET-469 Embedded Real Time Software Development
Author: Squish Therapy
File: live_test.py
--------
Real-time 60 FPS Clinical Rehabilitation Dashboard featuring:
- Two Side-by-Side Hero Plots: Range of Motion (ROM vs. Time) & Clinical Force Deficit Curve (Force vs. Angle)
- Physical Therapy Quantitative HUD: Repetitions, Active ROM, Force Deficit (Weak Point), Therapy Work (J), and SpO2 Vitals
- Seamless Top Action Toolbar with Zero Encoder Tare and Non-Shifting Save/Discard Controls
- 1-Click Maximize/Restore for Deep Curve Analysis
"""

import re
import time
from collections import deque
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit, QFrame, QFormLayout, QSplitter,
    QGraphicsDropShadowEffect, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Signal, Qt, QTimer, QEvent
from PySide6.QtGui import QColor
import pyqtgraph as pg

from theme import COLORS
from simulation import LiveDataGenerator
from utils import patch_all_axes
from hardware_interface import STM32EncoderInterface


class HeroPlotPanel(QFrame):
    """Encapsulated hero plot card with title bar, color chip, autoscale, and maximize buttons."""

    maximize_toggled = Signal(int)  # emits plot_idx

    def __init__(self, plot_idx: int, title: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.plot_idx = plot_idx
        self.title_text = title
        self.accent_color = accent_color
        self.is_maximized = False
        self.setObjectName("hero_card")
        self.setStyleSheet(f"""
            QFrame#hero_card {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header bar
        self.header = QHBoxLayout()
        self.header.setContentsMargins(4, 2, 4, 2)
        self.header.setSpacing(8)

        # Accent dot
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent_color}; font-size: 14px;")
        self.header.addWidget(dot)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: bold; font-size: 13px;")
        self.header.addWidget(self.lbl_title)

        self.header.addStretch()

        # Reset view button
        self.btn_reset = QPushButton("⟲")
        self.btn_reset.setToolTip("Reset view (autorange)")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFixedSize(24, 24)
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 0px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_dark']};
                color: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        self.btn_reset.clicked.connect(self.reset_view)
        self.header.addWidget(self.btn_reset)

        # Maximize / Restore button
        self.btn_maximize = QPushButton("⛶")
        self.btn_maximize.setToolTip("Maximize panel")
        self.btn_maximize.setCursor(Qt.PointingHandCursor)
        self.btn_maximize.setFixedSize(24, 24)
        self.btn_maximize.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 0px;
                font-size: 13px;
                min-width: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_dark']};
                color: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        self.btn_maximize.clicked.connect(self._on_maximize_clicked)
        self.header.addWidget(self.btn_maximize)

        layout.addLayout(self.header)

        # PyQtGraph PlotWidget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(COLORS['graph_bg'])
        self.plot_item = self.plot_widget.getPlotItem()
        
        # Ensure ample margin on left axis and right edge so tick labels are never clipped
        self.plot_item.getAxis('left').setWidth(55)
        self.plot_item.getAxis('bottom').setHeight(30)
        self.plot_item.getAxis('right').setWidth(12)
        patch_all_axes(self.plot_item)

        layout.addWidget(self.plot_widget, stretch=1)

    def add_header_widget(self, widget):
        """Add custom widget into the header before the reset button."""
        idx = self.header.indexOf(self.btn_reset)
        if idx >= 0:
            self.header.insertWidget(idx, widget)
        else:
            self.header.addWidget(widget)

    def set_title(self, text: str):
        """Update header title text."""
        self.title_text = text
        self.lbl_title.setText(text)

    def _on_maximize_clicked(self):
        self.maximize_toggled.emit(self.plot_idx)

    def set_maximized(self, is_max: bool):
        self.is_maximized = is_max
        if is_max:
            self.btn_maximize.setText("🗗")
            self.btn_maximize.setToolTip("Restore side-by-side view")
            self.btn_maximize.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['accent_dark']};
                    color: {COLORS['accent']};
                    border: 1px solid {COLORS['accent']};
                    border-radius: 4px;
                    padding: 0px;
                    font-size: 13px;
                    min-width: 0px;
                }}
            """)
        else:
            self.btn_maximize.setText("⛶")
            self.btn_maximize.setToolTip("Maximize panel")
            self.btn_maximize.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    padding: 0px;
                    font-size: 13px;
                    min-width: 0px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['accent_dark']};
                    color: {COLORS['accent']};
                    border-color: {COLORS['accent']};
                }}
            """)

    def reset_view(self):
        self.plot_item.enableAutoRange()


class TargetLoadComboBox(QComboBox):
    """
    Unified single-control clinical target load selector:
    - Single box displaying the number with unit (e.g. '10.0 lbs').
    - Click to type any custom number.
    - Arrow keys on keyboard (Up/Down) increment/decrement by 0.5 lbs.
    - Click side arrow to drop down presets (5.0, 10.0, 15.0, 20.0, 25.0 lbs).
    - Mouse wheel increments/decrements by 0.5 lbs.
    """
    valueChanged = Signal(float)

    def __init__(self, default_val: float = 10.0, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self._current_val = float(default_val)
        self._presets = [5.0, 10.0, 15.0, 20.0, 25.0]

        for p in self._presets:
            self.addItem(f"{p:.1f} lbs", userData=p)

        self.setFixedHeight(32)
        self.setFixedWidth(118)
        self.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-weight: bold;
                padding-left: 8px;
                padding-right: 24px;
            }}
            QComboBox:hover, QComboBox:focus {{
                border-color: {COLORS['accent']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {COLORS['border']};
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background-color: {COLORS['bg_surface']};
            }}
            QComboBox::drop-down:hover {{
                background-color: {COLORS['accent_dark']};
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {COLORS['accent']};
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                selection-background-color: {COLORS['accent_dark']};
                selection-color: {COLORS['accent']};
                padding: 4px;
                font-size: 12px;
            }}
        """)

        le = self.lineEdit()
        if le:
            le.setStyleSheet(f"""
                QLineEdit {{
                    background: transparent;
                    border: none;
                    color: {COLORS['text_primary']};
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0px;
                }}
            """)
            le.installEventFilter(self)
            le.editingFinished.connect(self._on_editing_finished)

        self.activated.connect(self._on_preset_activated)
        self.setValue(self._current_val)

    def value(self) -> float:
        return self._current_val

    def setValue(self, val: float):
        val = max(0.0, min(25.0, round(float(val), 1)))
        self._current_val = val
        txt = f"{val:.1f} lbs"
        if self.lineEdit():
            self.lineEdit().blockSignals(True)
            self.lineEdit().setText(txt)
            self.lineEdit().blockSignals(False)

        # Sync dropdown index if it matches a preset
        matched = False
        for i in range(self.count()):
            d = self.itemData(i)
            if d is not None and abs(float(d) - val) < 0.1:
                self.blockSignals(True)
                self.setCurrentIndex(i)
                self.blockSignals(False)
                matched = True
                break
        if not matched:
            self.blockSignals(True)
            self.setCurrentIndex(-1)
            if self.lineEdit():
                self.lineEdit().setText(txt)
            self.blockSignals(False)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.FocusIn:
                QTimer.singleShot(0, self.lineEdit().selectAll)
            elif event.type() == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Up:
                    new_v = min(25.0, round(self._current_val + 0.5, 1))
                    if new_v != self._current_val:
                        self.setValue(new_v)
                        self.valueChanged.emit(new_v)
                    return True
                elif key == Qt.Key_Down:
                    new_v = max(0.0, round(self._current_val - 0.5, 1))
                    if new_v != self._current_val:
                        self.setValue(new_v)
                        self.valueChanged.emit(new_v)
                    return True
                elif key in (Qt.Key_Return, Qt.Key_Enter):
                    self._on_editing_finished()
                    self.lineEdit().clearFocus()
                    return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            new_v = min(25.0, round(self._current_val + 0.5, 1))
        elif delta < 0:
            new_v = max(0.0, round(self._current_val - 0.5, 1))
        else:
            return
        if new_v != self._current_val:
            self.setValue(new_v)
            self.valueChanged.emit(new_v)
        event.accept()

    def _on_editing_finished(self):
        text = self.lineEdit().text().strip()
        match = re.search(r'[-+]?\d*\.?\d+', text)
        if match:
            try:
                new_v = float(match.group())
                new_v = max(0.0, min(25.0, round(new_v, 1)))
            except ValueError:
                new_v = self._current_val
        else:
            new_v = self._current_val
        self.setValue(new_v)
        self.valueChanged.emit(new_v)

    def _on_preset_activated(self, index: int):
        data = self.itemData(index)
        if data is not None:
            new_v = float(data)
            self.setValue(new_v)
            self.valueChanged.emit(new_v)


class LiveTestScreen(QWidget):
    """Clinical physical therapy dashboard with side-by-side hero plots and quantitative metrics."""

    test_completed = Signal(int)  # emits session_id

    MAX_POINTS = 1500  # 30 seconds at 50 Hz

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.client_id = None
        self.session_id = None
        self.generator = None
        self.hw = STM32EncoderInterface()
        self._hw_start_ms = None
        self._start_time = time.time()
        self.is_running = False
        self.elapsed_time = 0.0
        self.preview_time = 0.0
        self.current_rom = 0.0
        self.current_speed = 0.0
        self.current_force = 0.0
        self.current_spo2 = 0.0
        self.dt = 0.016  # ~60 Hz update rate
        self.time_window = 10.0  # seconds visible on screen

        # Data buffers
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_force_data = []
        self.full_spo2_data = []

        self.time_data = deque(maxlen=self.MAX_POINTS)
        self.rom_data = deque(maxlen=self.MAX_POINTS)
        self.speed_data = deque(maxlen=self.MAX_POINTS)
        self.force_data = deque(maxlen=self.MAX_POINTS)
        self.spo2_data = deque(maxlen=self.MAX_POINTS)
        self.ticks = 0

        # Plot range caching to prevent redundant scene recalculations at 60 Hz
        self._last_y_max = 25.0
        self._last_x_max = 10.0
        self._last_spo2_active = None
        self._last_deficit_style_active = None

        # Physical Therapy Clinical Metrics
        self.target_reps = 10
        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self._angle_zero_offset = 0.0

        # Repetition & Fatigue state tracking
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.rep_peak_forces = []
        self.session_baseline_rom = 0.0
        self.fatigue_index_pct = 100.0

        # Angular Tracking Architecture (16 bins: 0° to 160°, 10° per bin)
        self.NUM_ANGLE_BINS = 16
        self.angle_bin_centers = np.linspace(5.0, 155.0, self.NUM_ANGLE_BINS, dtype=np.float32)
        self.early_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.cur_rep_angle_forces = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.latest_rep_rom_curve = []
        self.latest_rep_force_curve = []
        self.fatigue_drop_angle = None
        self.fatigue_drop_delta = 0.0
        self.fatigue_drop_pct = 100.0

        # Movement Smoothness metric tracking & Angular Profile
        self.smoothness_vel_buf = deque(maxlen=60)
        self.smoothness_score = 92.0
        self.cur_rep_angle_smoothness = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_smooth_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.smoothness_angle_profile = np.full(self.NUM_ANGLE_BINS, 92.0, dtype=np.float32)
        self.smoothness_min_angle = None
        self.smoothness_min_score = 92.0

        self.combo_presets = None
        self.lbl_hud_work = QLabel("0 J")
        self.lbl_hud_work_sub = QLabel("")

        self._build_ui()
        self._setup_timer()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        # ── Header ─────────────────────────────────────────
        header_layout = QHBoxLayout()

        title = QLabel("Live Test")
        title.setObjectName("title")
        title.setStyleSheet(f"font-size: 22px; color: {COLORS['text_primary']}; border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 4px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        title.setGraphicsEffect(shadow)
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.lbl_status = QLabel("● IDLE")
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['border']};")
        header_layout.addWidget(self.lbl_status)

        layout.addLayout(header_layout)

        # ── Action Controls Toolbar (2-Row Responsive Layout) ─
        controls = QFrame()
        controls.setObjectName("card")
        controls.setStyleSheet(f"""
            QFrame#card {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(14, 9, 14, 9)
        controls_layout.setSpacing(8)

        # ── Row 1: Target Load, Presets, Forearm Length & Zeroing ─
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        lbl_load = QLabel("Target Load:")
        lbl_load.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        row1.addWidget(lbl_load)

        # Unified Target Load Control: click to type, keyboard Up/Down arrows to step, side arrow for presets
        self.spin_resistance = TargetLoadComboBox(default_val=10.0)
        self.spin_resistance.valueChanged.connect(self._on_resistance_value_changed)
        row1.addWidget(self.spin_resistance)

        # Apply / Command Load Button
        self.btn_send_load = QPushButton("Apply Load")
        self.btn_send_load.setToolTip("Transmit commanded target load (RES <lbs>) to stepper actuator")
        self.btn_send_load.setCursor(Qt.PointingHandCursor)
        self.btn_send_load.setFixedHeight(32)
        self.btn_send_load.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
                color: #0d1117;
            }}
        """)
        self.btn_send_load.clicked.connect(self._on_apply_load_clicked)
        row1.addWidget(self.btn_send_load)

        row1.addSpacing(6)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"background-color: {COLORS['border']};")
        sep.setFixedWidth(1)
        sep.setFixedHeight(22)
        row1.addWidget(sep)

        row1.addSpacing(6)

        # Forearm Length Parameter (Pin 1: 9" to Pin 5: 13")
        lbl_forearm = QLabel("Forearm:")
        lbl_forearm.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        row1.addWidget(lbl_forearm)

        self.combo_forearm = QComboBox()
        self.combo_forearm.setFixedHeight(32)
        self.combo_forearm.setMinimumWidth(150)
        self.combo_forearm.setCursor(Qt.PointingHandCursor)
        self.combo_forearm.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                font-size: 12px;
                font-weight: bold;
                padding-left: 8px;
                padding-right: 20px;
            }}
            QComboBox:hover, QComboBox:focus {{
                border-color: {COLORS['accent']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                selection-background-color: {COLORS['accent_dark']};
                selection-color: {COLORS['accent']};
                padding: 4px;
            }}
        """)
        for pin_num in range(1, 6):
            length_in = float(pin_num + 8)  # Pin 1=9", Pin 2=10", Pin 3=11", Pin 4=12", Pin 5=13"
            cm = length_in * 2.54
            self.combo_forearm.addItem(
                f"Pin {pin_num}: {length_in:.0f}\" ({cm:.1f} cm)",
                userData={"pin": pin_num, "inches": length_in, "meters": length_in * 0.0254}
            )
        self.combo_forearm.setCurrentIndex(3)  # Default Pin 4 (12 in)
        self.combo_forearm.currentIndexChanged.connect(self._on_forearm_changed)
        row1.addWidget(self.combo_forearm)

        row1.addStretch()

        # Intuitive Zero / Tare Button
        self.btn_zero = QPushButton("⟲ Zero Sensors")
        self.btn_zero.setToolTip("Zero joint angle and tare load cell baseline (also homes carriage)")
        self.btn_zero.setCursor(Qt.PointingHandCursor)
        self.btn_zero.setFixedHeight(32)
        self.btn_zero.setMinimumWidth(115)
        self.btn_zero.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['info']};
                border: 1px solid {COLORS['info']};
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['info']};
                color: white;
            }}
        """)
        self.btn_zero.clicked.connect(self._zero_encoder)
        row1.addWidget(self.btn_zero)

        controls_layout.addLayout(row1)

        # ── Row 2: Test Execution & Saved Sessions Controls ─
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Start / Stop Button
        self.btn_start_stop = QPushButton("▶  Start Test")
        self.btn_start_stop.setObjectName("primary")
        self.btn_start_stop.setCursor(Qt.PointingHandCursor)
        self.btn_start_stop.setFixedHeight(36)
        self.btn_start_stop.setMinimumWidth(130)
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px;
                font-weight: bold;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_start_stop.clicked.connect(self._toggle_test)
        row2.addWidget(self.btn_start_stop)

        # Save to Database Button
        self.btn_save = QPushButton("✓ Save Session")
        self.btn_save.setObjectName("primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setMinimumWidth(130)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                font-size: 13px;
                font-weight: bold;
                background-color: #0f8a6b;
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_save.clicked.connect(self._save_test)
        self.btn_save.setVisible(False)
        row2.addWidget(self.btn_save)

        # Discard Button
        self.btn_discard = QPushButton("✕ Discard")
        self.btn_discard.setObjectName("danger")
        self.btn_discard.setCursor(Qt.PointingHandCursor)
        self.btn_discard.setFixedHeight(36)
        self.btn_discard.setMinimumWidth(90)
        self.btn_discard.setStyleSheet(f"""
            QPushButton {{
                font-size: 13px;
                font-weight: bold;
                background-color: #5c1a1a;
                border: 2px solid {COLORS['danger']};
                border-radius: 8px;
                color: {COLORS['danger']};
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: white;
            }}
        """)
        self.btn_discard.clicked.connect(self._discard_test)
        self.btn_discard.setVisible(False)
        row2.addWidget(self.btn_discard)

        # Session Timer Readout Card
        timer_box = QFrame()
        timer_box.setFixedHeight(36)
        timer_box.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        tb_layout = QHBoxLayout(timer_box)
        tb_layout.setContentsMargins(8, 2, 10, 2)
        tb_layout.setSpacing(6)
        lbl_timer_icon = QLabel("⏱")
        lbl_timer_icon.setStyleSheet(f"font-size: 14px; color: {COLORS['text_muted']};")
        tb_layout.addWidget(lbl_timer_icon)

        self.lbl_timer = QLabel("0.0 s")
        self.lbl_timer.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 18px; font-weight: bold; font-family: monospace;")
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        self.lbl_timer.setMinimumWidth(65)
        tb_layout.addWidget(self.lbl_timer)
        row2.addWidget(timer_box)

        row2.addSpacing(6)

        # Target Reps Configuration
        lbl_target_reps = QLabel("Target Reps:")
        lbl_target_reps.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        row2.addWidget(lbl_target_reps)

        self.spin_target_reps = QSpinBox()
        self.spin_target_reps.setRange(1, 50)
        self.spin_target_reps.setValue(10)
        self.spin_target_reps.setFixedHeight(36)
        self.spin_target_reps.setFixedWidth(65)
        self.spin_target_reps.setStyleSheet(f"""
            QSpinBox {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-weight: bold;
                padding-left: 6px;
            }}
            QSpinBox:hover, QSpinBox:focus {{
                border-color: {COLORS['accent']};
            }}
        """)
        self.spin_target_reps.valueChanged.connect(self._on_target_reps_changed)
        row2.addWidget(self.spin_target_reps)

        row2.addStretch()

        controls_layout.addLayout(row2)
        layout.addWidget(controls)

        # ── Physical Therapy Quantitative HUD Strip (6 Cards, Equal Width) ─
        hud_frame = QFrame()
        hud_frame.setObjectName("hud_strip")
        hud_frame.setStyleSheet(f"""
            QFrame#hud_strip {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        hud_layout = QHBoxLayout(hud_frame)
        hud_layout.setContentsMargins(8, 6, 8, 6)
        hud_layout.setSpacing(6)

        # 1. Repetitions & Progress Card
        self.progress_reps = QProgressBar()
        self.progress_reps.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.progress_reps.setFixedHeight(5)
        self.progress_reps.setRange(0, self.target_reps)
        self.progress_reps.setValue(0)
        self.progress_reps.setTextVisible(False)
        self.progress_reps.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['bg_dark']};
                border: 1px solid {COLORS['border']};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['accent']};
                border-radius: 2px;
            }}
        """)
        hud_layout.addWidget(self._create_hud_card(
            title="REPETITIONS",
            attr_name="lbl_hud_reps",
            sub_attr_name="lbl_hud_reps_sub",
            default_val="0 / 10 Reps",
            default_sub="Target: 10 Reps (0%)",
            val_color=COLORS['accent'],
            extra_widget=self.progress_reps,
        ), 1)

        # 2. Active ROM Card
        hud_layout.addWidget(self._create_hud_card(
            title="ACTIVE ROM",
            attr_name="lbl_hud_rom",
            sub_attr_name="lbl_hud_rom_sub",
            default_val="0.0°",
            default_sub="Live: 0° • Peak: 0°",
            val_color=COLORS['graph_rom'],
        ), 1)

        # 3. Handle Force Card
        hud_layout.addWidget(self._create_hud_card(
            title="HANDLE FORCE",
            attr_name="lbl_hud_force",
            sub_attr_name="lbl_hud_force_sub",
            default_val="0.0 lbs",
            default_sub="10 lbs • 0 J",
            val_color=COLORS['graph_strength'],
        ), 1)

        # 4. Fatigue Index Card
        hud_layout.addWidget(self._create_hud_card(
            title="FATIGUE INDEX",
            attr_name="lbl_hud_fatigue",
            sub_attr_name="lbl_hud_fatigue_sub",
            default_val="100%",
            default_sub="● Good Endurance",
            val_color=COLORS['accent'],
        ), 1)

        # 5. Movement Smoothness Card
        hud_layout.addWidget(self._create_hud_card(
            title="SMOOTHNESS",
            attr_name="lbl_hud_smoothness",
            sub_attr_name="lbl_hud_smoothness_sub",
            default_val="---%",
            default_sub="Awaiting Movement",
            val_color=COLORS.get('accent_cyan', '#00e5ff'),
        ), 1)

        # 6. Pulse Oximetry Card
        hud_layout.addWidget(self._create_hud_card(
            title="PULSE OXIMETRY",
            attr_name="lbl_hud_spo2",
            sub_attr_name="lbl_hud_spo2_sub",
            default_val="98%",
            default_sub="● Sensor Active",
            val_color=COLORS['graph_spo2'],
        ), 1)

        layout.addWidget(hud_frame)

        # ── Two Hero Plots (Side-by-Side Horizontal QSplitter)
        pg.setConfigOptions(antialias=False)
        self.hero_splitter = QSplitter(Qt.Horizontal)
        self.hero_splitter.setChildrenCollapsible(False)

        # Hero Plot 1 (Left): Range of Motion vs. Time
        self.panel_rom = HeroPlotPanel(0, "Range of Motion (ROM)", COLORS['graph_rom'])
        self.plot_rom = self.panel_rom.plot_item
        self.plot_rom.setLabel('left', 'Joint Angle (°)', color=COLORS['graph_rom'])
        self.plot_rom.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
        self.plot_rom.showGrid(x=True, y=True, alpha=0.25)
        self.plot_rom.getAxis('left').setPen(pg.mkPen(COLORS['graph_rom']))
        self.plot_rom.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_rom']))
        self.plot_rom.setYRange(-5, 160, padding=0)
        self.plot_rom.setXRange(0, self.time_window, padding=0)

        self.curve_rom = self.plot_rom.plot(
            pen=pg.mkPen(COLORS['graph_rom'], width=2.2), name="ROM"
        )
        self.curve_rom.setClipToView(True)
        self.curve_rom.setDownsampling(auto=True, method='peak')
        self.panel_rom.maximize_toggled.connect(self._toggle_maximize)
        self.hero_splitter.addWidget(self.panel_rom)

        # Hero Plot 2 (Right): Force vs. Time or Angle
        self.panel_force = HeroPlotPanel(1, "Handle Force", COLORS['graph_strength'])
        self.plot_force = self.panel_force.plot_item
        self.plot_force.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
        self.plot_force.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
        self.plot_force.showGrid(x=True, y=True, alpha=0.25)
        self.plot_force.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
        self.plot_force.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
        self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_secondary']))
        self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_secondary']))
        self.plot_force.setXRange(0, self.time_window, padding=0)
        self.plot_force.setYRange(0, 25, padding=0)

        # Mode toggle segmented pill buttons on Hero Plot 2
        self.toggle_mode_frame = QFrame()
        self.toggle_mode_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        t_layout = QHBoxLayout(self.toggle_mode_frame)
        t_layout.setContentsMargins(2, 2, 2, 2)
        t_layout.setSpacing(2)

        self.btn_mode_time = QPushButton("Time")
        self.btn_mode_force_angle = QPushButton("Force/Angle")
        self.btn_mode_smooth_angle = QPushButton("Smooth/Angle")
        for btn in (self.btn_mode_time, self.btn_mode_force_angle, self.btn_mode_smooth_angle):
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
        self.btn_mode_time.clicked.connect(lambda: self._set_force_plot_mode("TIME"))
        self.btn_mode_force_angle.clicked.connect(lambda: self._set_force_plot_mode("FORCE_ANGLE"))
        self.btn_mode_smooth_angle.clicked.connect(lambda: self._set_force_plot_mode("SMOOTH_ANGLE"))
        t_layout.addWidget(self.btn_mode_time)
        t_layout.addWidget(self.btn_mode_force_angle)
        t_layout.addWidget(self.btn_mode_smooth_angle)
        self.panel_force.add_header_widget(self.toggle_mode_frame)

        # Dashed Target Resistance Reference Line (Time and Force/Angle)
        self.line_target_force = pg.InfiniteLine(
            pos=10.0, angle=0,
            pen=pg.mkPen(COLORS['warning'], style=Qt.DashLine, width=1.5)
        )
        self.plot_force.addItem(self.line_target_force)
        self.lbl_target_force_line = pg.TextItem("Target Load: 10.0 lbs", color=COLORS['warning'], anchor=(1, 0), fill=pg.mkColor(13, 17, 23, 180))
        self.lbl_target_force_line.setPos(self.time_window - 0.4, 10.2)
        self.plot_force.addItem(self.lbl_target_force_line)

        # Early Reps Baseline Force Curve (active in Force/Angle mode)
        self.curve_force_baseline = self.plot_force.plot(
            pen=pg.mkPen(COLORS['accent'], style=Qt.DashLine, width=1.8), name="Baseline Force"
        )
        self.curve_force_baseline.setClipToView(True)

        # Live / Recent Force Curve (Time and Force/Angle modes)
        self.curve_force_live = self.plot_force.plot(
            pen=pg.mkPen(COLORS['graph_strength'], width=2.2), name="Live Force"
        )
        self.curve_force_live.setClipToView(True)
        self.curve_force_live.setDownsampling(auto=True, method='peak')

        # Smoothness Profile Curve (active in Smooth/Angle mode)
        self.curve_smooth_angle = self.plot_force.plot(
            pen=pg.mkPen(COLORS.get('accent_cyan', '#00e5ff'), width=2.4), name="Smoothness Profile"
        )
        self.curve_smooth_angle.setClipToView(True)

        # Smoothness Reference Lines (active in Smooth/Angle mode)
        self.line_smooth_fluid = pg.InfiniteLine(
            pos=85.0, angle=0,
            pen=pg.mkPen(COLORS['accent'], style=Qt.DashLine, width=1.2)
        )
        self.plot_force.addItem(self.line_smooth_fluid)
        self.lbl_smooth_fluid = pg.TextItem("Fluid (85%)", color=COLORS['accent'], anchor=(1.0, 1.2), fill=pg.mkColor(13, 17, 23, 160))
        self.lbl_smooth_fluid.setPos(158.0, 85.0)
        self.plot_force.addItem(self.lbl_smooth_fluid)

        self.line_smooth_tremor = pg.InfiniteLine(
            pos=70.0, angle=0,
            pen=pg.mkPen(COLORS['warning'], style=Qt.DashLine, width=1.2)
        )
        self.plot_force.addItem(self.line_smooth_tremor)
        self.lbl_smooth_tremor = pg.TextItem("Tremor (70%)", color=COLORS['warning'], anchor=(1.0, 1.2), fill=pg.mkColor(13, 17, 23, 160))
        self.lbl_smooth_tremor.setPos(158.0, 70.0)
        self.plot_force.addItem(self.lbl_smooth_tremor)

        # Deficit Callout & Marker (active in Force/Angle mode)
        self.deficit_marker = pg.ScatterPlotItem(
            size=12, pen=pg.mkPen(COLORS['danger'], width=2), brush=pg.mkBrush(COLORS['warning'])
        )
        self.plot_force.addItem(self.deficit_marker)
        self.deficit_callout = pg.TextItem("", color=COLORS['warning'], anchor=(0.5, 1.3))
        self.plot_force.addItem(self.deficit_callout)

        # Fatigue Drop Marker & Callout (active in Force/Angle mode)
        self.fatigue_marker = pg.ScatterPlotItem(
            size=14, pen=pg.mkPen(COLORS['warning'], width=2), brush=pg.mkBrush(COLORS['danger'])
        )
        self.plot_force.addItem(self.fatigue_marker)
        self.fatigue_callout = pg.TextItem("", color=COLORS['warning'], anchor=(0.5, 1.3))
        self.plot_force.addItem(self.fatigue_callout)

        # Minimum Smoothness Marker & Callout (active in Smooth/Angle mode)
        self.smooth_marker = pg.ScatterPlotItem(
            size=12, pen=pg.mkPen(COLORS['warning'], width=2), brush=pg.mkBrush(COLORS.get('accent_cyan', '#00e5ff'))
        )
        self.plot_force.addItem(self.smooth_marker)
        self.smooth_callout = pg.TextItem("", color=COLORS.get('accent_cyan', '#00e5ff'), anchor=(0.5, 1.4))
        self.plot_force.addItem(self.smooth_callout)

        self.panel_force.maximize_toggled.connect(self._toggle_maximize)
        self.hero_splitter.addWidget(self.panel_force)

        # 50/50 Initial Split
        self.hero_splitter.setSizes([600, 600])
        layout.addWidget(self.hero_splitter, stretch=1)

        self._set_force_plot_mode("TIME")
        self._setup_crosshair()

    def _create_hud_card(self, title, attr_name, sub_attr_name, default_val, default_sub, val_color, extra_widget=None):
        """Builds a single quantitative physical therapy card."""
        card = QFrame()
        card.setObjectName("hud_card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setMinimumWidth(85)
        card.setStyleSheet(f"""
            QFrame#hud_card {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(8, 4, 8, 4)
        c_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        c_layout.addWidget(lbl_title)

        lbl_val = QLabel(default_val)
        lbl_val.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {val_color};")
        setattr(self, attr_name, lbl_val)
        c_layout.addWidget(lbl_val)

        if extra_widget is not None:
            c_layout.addWidget(extra_widget)

        lbl_sub = QLabel(default_sub)
        lbl_sub.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        setattr(self, sub_attr_name, lbl_sub)
        c_layout.addWidget(lbl_sub)

        return card

    def _setup_crosshair(self):
        """Interactive dashed crosshairs on both hero plots."""
        pen = pg.mkPen(COLORS['accent'], style=Qt.DashLine)
        self.vLine_rom = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_rom = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.plot_rom.addItem(self.vLine_rom, ignoreBounds=True)
        self.plot_rom.addItem(self.hLine_rom, ignoreBounds=True)

        self.vLine_force = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_force = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.plot_force.addItem(self.vLine_force, ignoreBounds=True)
        self.plot_force.addItem(self.hLine_force, ignoreBounds=True)

        bg_color = QColor(COLORS['bg_surface'])
        bg_color.setAlpha(190)
        self.label_rom_hover = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_rom.addItem(self.label_rom_hover, ignoreBounds=True)
        self.label_force_hover = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_force.addItem(self.label_force_hover, ignoreBounds=True)

        self.proxy_1 = pg.SignalProxy(self.panel_rom.plot_widget.scene().sigMouseMoved, rateLimit=25, slot=self._mouse_moved_rom)
        self.proxy_2 = pg.SignalProxy(self.panel_force.plot_widget.scene().sigMouseMoved, rateLimit=25, slot=self._mouse_moved_force)

    def _mouse_moved_rom(self, evt):
        if not self.time_data:
            return
        pos = evt[0]
        if self.plot_rom.sceneBoundingRect().contains(pos):
            mousePoint = self.plot_rom.vb.mapSceneToView(pos)
            x_val = mousePoint.x()
            t_arr = np.asarray(self.time_data)
            idx = np.searchsorted(t_arr, x_val)
            if idx >= len(t_arr):
                idx = len(t_arr) - 1
            t_pt = t_arr[idx]
            rom_pt = self.rom_data[idx]

            self.vLine_rom.setPos(t_pt)
            self.hLine_rom.setPos(rom_pt)
            self.label_rom_hover.setText(f"Time: {t_pt:.1f}s\nAngle: {rom_pt:.1f}°")
            self.label_rom_hover.setPos(t_pt, rom_pt)

    def _set_force_plot_mode(self, mode: str):
        """Toggle Hero Plot 2 between Time, Force vs Angle (Fatigue), and Smoothness vs Angle."""
        if mode == "ANGLE":
            mode = "FORCE_ANGLE"
        self.force_plot_mode = mode

        active_force_style = f"""
            QPushButton {{
                font-size: 10px;
                font-weight: bold;
                padding: 1px 5px;
                border: none;
                border-radius: 4px;
                color: #0d1117;
                background-color: {COLORS['graph_strength']};
                min-width: 0px;
            }}
        """
        active_smooth_style = f"""
            QPushButton {{
                font-size: 10px;
                font-weight: bold;
                padding: 1px 5px;
                border: none;
                border-radius: 4px;
                color: #0d1117;
                background-color: {COLORS.get('accent_cyan', '#00e5ff')};
                min-width: 0px;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                font-size: 10px;
                padding: 1px 5px;
                border: none;
                border-radius: 4px;
                color: {COLORS['text_secondary']};
                background: transparent;
                min-width: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
                background-color: {COLORS['bg_input']};
            }}
        """
        target_r = self.spin_resistance.value()

        if mode == "TIME":
            self.btn_mode_time.setStyleSheet(active_force_style)
            self.btn_mode_force_angle.setStyleSheet(inactive_style)
            self.btn_mode_smooth_angle.setStyleSheet(inactive_style)
            self.panel_force.set_title("Handle Force")
            self.plot_force.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
            self.plot_force.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
            self.plot_force.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_force.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_secondary']))
            self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_secondary']))

            self.curve_force_live.setVisible(True)
            self.curve_force_baseline.setVisible(False)
            self.curve_smooth_angle.setVisible(False)
            self.line_target_force.setVisible(True)
            self.lbl_target_force_line.setVisible(True)
            self.line_smooth_fluid.setVisible(False)
            self.lbl_smooth_fluid.setVisible(False)
            self.line_smooth_tremor.setVisible(False)
            self.lbl_smooth_tremor.setVisible(False)
            self.deficit_marker.setVisible(False)
            self.deficit_callout.setVisible(False)
            self.fatigue_marker.setVisible(False)
            self.fatigue_callout.setVisible(False)
            self.smooth_marker.setVisible(False)
            self.smooth_callout.setVisible(False)

            current_t = self.time_data[-1] if self.time_data else 0.0
            if current_t > self.time_window:
                x_min = current_t - self.time_window
                x_max = current_t
            else:
                x_min = 0.0
                x_max = self.time_window
            self.plot_force.setXRange(x_min, x_max, padding=0)
            self.plot_force.setYRange(0, max(25.0, target_r * 1.6), padding=0)
            self.lbl_target_force_line.setPos(x_max - 0.4, target_r + 0.2)
            if self.time_data and self.force_data:
                self.curve_force_live.setData(np.asarray(self.time_data, dtype=np.float32), np.asarray(self.force_data, dtype=np.float32))
            else:
                self.curve_force_live.setData([], [])

        elif mode == "FORCE_ANGLE":
            self.btn_mode_time.setStyleSheet(inactive_style)
            self.btn_mode_force_angle.setStyleSheet(active_force_style)
            self.btn_mode_smooth_angle.setStyleSheet(inactive_style)
            self.panel_force.set_title("Force / Angle")
            self.plot_force.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
            self.plot_force.setLabel('bottom', 'Joint Angle (°)', color=COLORS['text_primary'])
            self.plot_force.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_force.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_primary']))
            self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_primary']))

            self.curve_force_live.setVisible(True)
            self.curve_force_baseline.setVisible(True)
            self.curve_smooth_angle.setVisible(False)
            self.line_target_force.setVisible(True)
            self.lbl_target_force_line.setVisible(True)
            self.line_smooth_fluid.setVisible(False)
            self.lbl_smooth_fluid.setVisible(False)
            self.line_smooth_tremor.setVisible(False)
            self.lbl_smooth_tremor.setVisible(False)
            self.deficit_marker.setVisible(True)
            self.deficit_callout.setVisible(True)
            self.fatigue_marker.setVisible(True)
            self.fatigue_callout.setVisible(True)
            self.smooth_marker.setVisible(False)
            self.smooth_callout.setVisible(False)

            self.plot_force.setXRange(0, 160, padding=0)
            self.plot_force.setYRange(0, max(25.0, target_r * 1.6), padding=0)
            self.lbl_target_force_line.setPos(155, target_r + 0.2)
            if self.latest_rep_rom_curve and len(self.latest_rep_rom_curve) >= 2:
                r_pts = np.asarray(self.latest_rep_rom_curve, dtype=np.float32)
                f_pts = np.asarray(self.latest_rep_force_curve, dtype=np.float32)
                s_idx = np.argsort(r_pts)
                self.curve_force_live.setData(r_pts[s_idx], f_pts[s_idx])
            elif self.reps_count >= 1:
                valid_b = [b for b in range(self.NUM_ANGLE_BINS) if self.recent_rep_force_bins[b]]
                if valid_b:
                    x_pts = self.angle_bin_centers[valid_b]
                    y_pts = np.asarray([np.mean(self.recent_rep_force_bins[b]) for b in valid_b], dtype=np.float32)
                    self.curve_force_live.setData(x_pts, y_pts)
                else:
                    self.curve_force_live.setData([], [])
            else:
                self.curve_force_live.setData([], [])

            # Baseline force curve from early reps
            if self.reps_count >= 2:
                base_c = [float(np.mean(self.early_rep_force_bins[b])) if self.early_rep_force_bins[b] else 0.0 for b in range(self.NUM_ANGLE_BINS)]
                self.curve_force_baseline.setData(self.angle_bin_centers, np.asarray(base_c, dtype=np.float32))
            else:
                self.curve_force_baseline.setData([], [])

        elif mode == "SMOOTH_ANGLE":
            self.btn_mode_time.setStyleSheet(inactive_style)
            self.btn_mode_force_angle.setStyleSheet(inactive_style)
            self.btn_mode_smooth_angle.setStyleSheet(active_smooth_style)
            self.panel_force.set_title("Smoothness / Angle")
            self.plot_force.setLabel('left', 'Movement Smoothness (%)', color=COLORS.get('accent_cyan', '#00e5ff'))
            self.plot_force.setLabel('bottom', 'Joint Angle (°)', color=COLORS['text_primary'])
            self.plot_force.getAxis('left').setPen(pg.mkPen(COLORS.get('accent_cyan', '#00e5ff')))
            self.plot_force.getAxis('left').setTextPen(pg.mkPen(COLORS.get('accent_cyan', '#00e5ff')))
            self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_primary']))
            self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_primary']))

            self.curve_force_live.setVisible(False)
            self.curve_force_baseline.setVisible(False)
            self.curve_smooth_angle.setVisible(True)
            self.line_target_force.setVisible(False)
            self.lbl_target_force_line.setVisible(False)
            self.line_smooth_fluid.setVisible(True)
            self.lbl_smooth_fluid.setVisible(True)
            self.line_smooth_tremor.setVisible(True)
            self.lbl_smooth_tremor.setVisible(True)
            self.deficit_marker.setVisible(False)
            self.deficit_callout.setVisible(False)
            self.fatigue_marker.setVisible(False)
            self.fatigue_callout.setVisible(False)
            self.smooth_marker.setVisible(True)
            self.smooth_callout.setVisible(True)

            self.plot_force.setXRange(0, 160, padding=0)
            self.plot_force.setYRange(0, 105, padding=0)
            valid_b = [b for b in range(self.NUM_ANGLE_BINS) if self.recent_rep_smooth_bins[b]]
            if valid_b:
                x_pts = self.angle_bin_centers[valid_b]
                y_pts = np.asarray([self.smoothness_angle_profile[b] for b in valid_b], dtype=np.float32)
                self.curve_smooth_angle.setData(x_pts, y_pts)
            elif self.reps_count > 0 or len(self.full_time_data) >= 30:
                self.curve_smooth_angle.setData(self.angle_bin_centers, self.smoothness_angle_profile)
            else:
                self.curve_smooth_angle.setData([], [])

    def _mouse_moved_force(self, evt):
        if not self.force_data:
            return
        pos = evt[0]
        if self.plot_force.sceneBoundingRect().contains(pos):
            mousePoint = self.plot_force.vb.mapSceneToView(pos)
            x_val = mousePoint.x()
            y_val = mousePoint.y()
            if self.force_plot_mode == "TIME":
                if not self.time_data:
                    return
                t_arr = np.asarray(self.time_data)
                idx = np.searchsorted(t_arr, x_val)
                if idx >= len(t_arr):
                    idx = len(t_arr) - 1
                t_pt = t_arr[idx]
                f_pt = self.force_data[idx]
                self.vLine_force.setPos(t_pt)
                self.hLine_force.setPos(f_pt)
                self.label_force_hover.setText(f"Time: {t_pt:.1f}s\nForce: {f_pt:.1f} lbs")
                self.label_force_hover.setPos(t_pt, f_pt)
            elif self.force_plot_mode == "SMOOTH_ANGLE":
                c_x = self.curve_smooth_angle.xData
                c_y = self.curve_smooth_angle.yData
                if c_x is not None and len(c_x) > 0:
                    c_x_arr = np.asarray(c_x, dtype=np.float32)
                    c_y_arr = np.asarray(c_y, dtype=np.float32)
                    x_clamped = max(float(c_x_arr[0]), min(float(c_x_arr[-1]), x_val))
                    val = float(np.interp(x_clamped, c_x_arr, c_y_arr))
                    self.vLine_force.setPos(x_clamped)
                    self.hLine_force.setPos(val)
                    self.label_force_hover.setText(f"Angle: {x_clamped:.1f}°\nSmoothness: {val:.0f}%")
                    self.label_force_hover.setPos(x_clamped, val)
                    self.vLine_force.setVisible(True)
                    self.hLine_force.setVisible(True)
                    self.label_force_hover.setVisible(True)
                else:
                    self.vLine_force.setVisible(False)
                    self.hLine_force.setVisible(False)
                    self.label_force_hover.setVisible(False)
            else:
                c_x = self.curve_force_live.xData
                c_y = self.curve_force_live.yData
                if c_x is not None and len(c_x) > 0:
                    c_x_arr = np.asarray(c_x, dtype=np.float32)
                    c_y_arr = np.asarray(c_y, dtype=np.float32)
                    x_clamped = max(float(c_x_arr[0]), min(float(c_x_arr[-1]), x_val))
                    val = float(np.interp(x_clamped, c_x_arr, c_y_arr))
                    self.vLine_force.setPos(x_clamped)
                    self.hLine_force.setPos(val)
                    self.label_force_hover.setText(f"Angle: {x_clamped:.1f}°\nForce: {val:.1f} lbs")
                    self.label_force_hover.setPos(x_clamped, val)
                    self.vLine_force.setVisible(True)
                    self.hLine_force.setVisible(True)
                    self.label_force_hover.setVisible(True)
                else:
                    self.vLine_force.setVisible(False)
                    self.hLine_force.setVisible(False)
                    self.label_force_hover.setVisible(False)

    def _toggle_maximize(self, idx):
        if self._maximized_idx == idx:
            # Restore side-by-side
            self.panel_rom.setVisible(True)
            self.panel_force.setVisible(True)
            self.panel_rom.set_maximized(False)
            self.panel_force.set_maximized(False)
            self.hero_splitter.setSizes([600, 600])
            self._maximized_idx = None
        else:
            if idx == 0:
                self.panel_rom.setVisible(True)
                self.panel_force.setVisible(False)
                self.panel_rom.set_maximized(True)
                self.panel_force.set_maximized(False)
            else:
                self.panel_rom.setVisible(False)
                self.panel_force.setVisible(True)
                self.panel_rom.set_maximized(False)
                self.panel_force.set_maximized(True)
            self._maximized_idx = idx

    def _on_resistance_value_changed(self, val: float):
        self.line_target_force.setPos(val)
        if self.force_plot_mode == "TIME":
            current_t = self.time_data[-1] if self.time_data else self.time_window
            self.lbl_target_force_line.setPos(max(self.time_window, current_t) - 0.4, val)
        elif self.force_plot_mode == "FORCE_ANGLE":
            self.lbl_target_force_line.setPos(155, val)
        self.lbl_target_force_line.setText(f"Target Load: {val:.1f} lbs")
        if self.force_plot_mode != "SMOOTH_ANGLE":
            self.plot_force.setYRange(0, max(25.0, val * 1.6), padding=0)

        # Dynamic auto-sync: instantly apply to simulation generator or hardware interface
        if getattr(self, 'generator', None):
            self.generator.target_resistance = val
        if getattr(self, 'hw', None) and self.hw.is_connected:
            self.hw.set_resistance(val)

        if self.last_deficit_angle is None:
            res_txt = f"{val:.0f} lbs" if val.is_integer() else f"{val:.1f} lbs"
            self.lbl_hud_force_sub.setText(f"{res_txt} • {self.therapy_work_j:.0f} J")

    def _on_target_reps_changed(self, val: int):
        self.target_reps = int(val)
        self.progress_reps.setRange(0, self.target_reps)
        pct = int(min(100.0, (self.reps_count / max(1, self.target_reps)) * 100.0))
        self.progress_reps.setValue(min(self.reps_count, self.target_reps))
        self.lbl_hud_reps.setText(f"{self.reps_count} / {self.target_reps} Reps")
        self.lbl_hud_reps_sub.setText(f"Target: {self.target_reps} Reps ({pct}%)")

    def _submit_resistance(self):
        """Transmit commanded target resistance to STM32 NEMA stepper controller."""
        val = self.spin_resistance.value()
        self._on_resistance_value_changed(val)

    def _on_apply_load_clicked(self):
        """Explicitly transmits commanded target resistance to STM32 NEMA stepper controller."""
        val = self.spin_resistance.value()
        self._on_resistance_value_changed(val)
        if getattr(self, 'hw', None) and self.hw.is_connected:
            self.hw.set_resistance(val)
        self.btn_send_load.setText("✓ Sent")
        self.btn_send_load.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: #0d1117;
                border: 1px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        QTimer.singleShot(1500, self._reset_send_load_btn)

    def _reset_send_load_btn(self):
        self.btn_send_load.setText("Apply Load")
        self.btn_send_load.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
                color: #0d1117;
            }}
        """)

    def _on_resistance_changed(self, val):
        self._on_resistance_value_changed(val)

    def get_forearm_pin(self) -> int:
        data = self.combo_forearm.currentData()
        if isinstance(data, dict) and "pin" in data:
            return int(data["pin"])
        return self.combo_forearm.currentIndex() + 1

    def get_forearm_inches(self) -> float:
        data = self.combo_forearm.currentData()
        if isinstance(data, dict) and "inches" in data:
            return float(data["inches"])
        return float(self.combo_forearm.currentIndex() + 9)

    def get_forearm_meters(self) -> float:
        return self.get_forearm_inches() * 0.0254

    def _on_forearm_changed(self, _idx=0):
        pin = self.get_forearm_pin()
        inches = self.get_forearm_inches()
        self.lbl_hud_work_sub.setText(f"Cumulative Energy (Pin {pin}: {inches:.0f}\")")
        if not self.is_running:
            self.lbl_hud_force_sub.setText(f"Peak: {self.max_session_force:.1f} lbs • Target: {self.spin_resistance.value():.1f} lbs")

    def _zero_encoder(self):
        """Homes NEMA stepper carriage to limit, backs off 5 mm, and tares encoder & load cell."""
        if not self.hw.is_connected:
            self.hw.connect()
        if self.hw.is_connected:
            self.lbl_status.setText("● HOMING NEMA & TARING SENSORS...")
            self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['warning']};")
            QApplication.processEvents()
            self.hw.home()
            self.hw.zero()
        self.current_rom = 0.0
        self.current_force = 0.0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        if not self.is_running:
            self.time_data.clear()
            self.rom_data.clear()
            self.speed_data.clear()
            self.force_data.clear()
            self.spo2_data.clear()
            self.preview_time = 0.0
            self.curve_rom.setData([], [])
            self.curve_force_live.setData([], [])
        self.lbl_hud_rom.setText("0.0°")
        self.lbl_hud_rom_sub.setText("Live Angle: 0.0°")
        self.lbl_hud_force.setText("0.0 lbs")
        self.lbl_hud_force_sub.setText(f"Sensor Tared • Target: {self.spin_resistance.value():.1f} lbs")
        self.lbl_status.setText("● NEMA HOMED & SENSORS TARED (Ready)")
        self.lbl_status.setStyleSheet(f"color: {COLORS['info']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['info']};")

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(int(self.dt * 1000))  # 16ms ~ 60 FPS
        self.timer.timeout.connect(self._update_data)
        self.timer.start()

    def setup(self, client_id):
        self.client_id = client_id
        if self.client_id:
            client = self.db.get_client(self.client_id)
            if client and "forearm_pin" in client and client["forearm_pin"]:
                pin_idx = max(0, min(4, int(client["forearm_pin"]) - 1))
                self.combo_forearm.setCurrentIndex(pin_idx)
        if not self.hw.is_connected:
            self.hw.connect()
        self._reset()
        self.generator = None  # Do NOT generate preview curl samples while idle
        if self.hw.is_connected:
            self.lbl_status.setText("● READY (Hardware Connected - Set Load & Click 'Start Test')")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.lbl_status.setText("● READY (Simulation Mode - Set Load & Click 'Start Test')")
            self.lbl_status.setStyleSheet(f"color: {COLORS['info']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['info']};")
        if not self.timer.isActive():
            self.timer.start()

    def cleanup(self):
        """Safely pause timers and close hardware streaming on view unload / app close."""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, 'hw') and self.hw.is_connected:
            self.hw.stop_streaming()
            self.hw.disconnect()

    def _reset(self):
        """Reset test session state while maintaining clean ready state."""
        self.is_running = False
        self.elapsed_time = 0.0
        self._hw_start_ms = None
        self.session_id = None
        self.ticks = 0

        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_force_data = []
        self.full_spo2_data = []

        self.time_data.clear()
        self.rom_data.clear()
        self.speed_data.clear()
        self.force_data.clear()
        self.spo2_data.clear()

        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.rep_peak_forces = []
        self.fatigue_index_pct = 100.0
        self.smoothness_vel_buf.clear()
        self.smoothness_score = 92.0
        self.session_baseline_rom = self.current_rom
        self.progress_reps.setValue(0)

        self.early_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.cur_rep_angle_forces = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.latest_rep_rom_curve = []
        self.latest_rep_force_curve = []
        self.fatigue_drop_angle = None
        self.fatigue_drop_delta = 0.0
        self.fatigue_drop_pct = 100.0
        self.cur_rep_angle_smoothness = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_smooth_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.smoothness_angle_profile = np.full(self.NUM_ANGLE_BINS, 92.0, dtype=np.float32)
        self.smoothness_min_angle = None
        self.smoothness_min_score = 92.0

        self.curve_rom.setData([], [])
        self.curve_force_live.setData([], [])
        self.curve_force_baseline.setData([], [])
        self.curve_smooth_angle.setData([], [])
        self.deficit_marker.setData([], [])
        self.deficit_callout.setText("")
        self.fatigue_marker.setData([], [])
        self.fatigue_callout.setText("")
        self.smooth_marker.setData([], [])
        self.smooth_callout.setText("")

        # Reset plot viewports cleanly back to 0.0s
        self.plot_rom.setXRange(0.0, self.time_window, padding=0)
        if self.force_plot_mode == "TIME":
            self.plot_force.setXRange(0.0, self.time_window, padding=0)
        else:
            self.plot_force.setXRange(0.0, 160.0, padding=0)
        self._last_x_max = self.time_window
        self._last_y_max = 25.0
        self.plot_force.setYRange(0, 25.0, padding=0)

        pct_reps = int(min(100.0, (self.reps_count / max(1, self.target_reps)) * 100.0))
        self.lbl_hud_reps.setText(f"0 / {self.target_reps} Reps")
        self.lbl_hud_reps_sub.setText(f"Target: {self.target_reps} Reps ({pct_reps}%)")
        self.lbl_hud_rom.setText(f"{self.current_rom:.1f}°")
        self.lbl_hud_rom_sub.setText(f"Live: {self.current_rom:.0f}° • Peak: {self.max_session_rom:.0f}°")
        self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
        self.lbl_hud_force.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['graph_strength']};")
        res_v = self.spin_resistance.value()
        res_txt = f"{res_v:.0f} lbs" if res_v.is_integer() else f"{res_v:.1f} lbs"
        self.lbl_hud_force_sub.setText(f"{res_txt} • 0 J")
        self.lbl_hud_force_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_secondary']};")
        self.lbl_hud_fatigue.setText("100%")
        self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['accent']};")
        self.lbl_hud_fatigue_sub.setText("● Baseline Level")
        self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_secondary']};")
        self.lbl_hud_smoothness.setText("---%")
        self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['text_muted']};")
        self.lbl_hud_smoothness_sub.setText("Awaiting Movement")
        self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        self.lbl_hud_work.setText("0 J")
        if self.current_spo2 > 0:
            self.lbl_hud_spo2.setText(f"{self.current_spo2:.0f}%")
        else:
            self.lbl_hud_spo2.setText("---%")

        self.lbl_timer.setText("0.0 s")
        if self.hw.is_connected:
            self.lbl_status.setText("● READY (Hardware Connected - Set Load & Click 'Start Test')")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.lbl_status.setText("● READY (Simulation Mode - Set Load & Click 'Start Test')")
            self.lbl_status.setStyleSheet(f"color: {COLORS['info']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['info']};")

        self.btn_start_stop.setText("▶  Start Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px;
                font-weight: bold;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_start_stop.setVisible(True)
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)
        self.spin_resistance.setEnabled(True)
        self.btn_zero.setEnabled(True)
        if not self.timer.isActive():
            self.timer.start()

    def _toggle_test(self):
        if self.is_running:
            self._stop_test()
        else:
            self._start_test()

    def _start_test(self):
        target_resistance = self.spin_resistance.value()
        self._on_resistance_changed(target_resistance)

        self.is_running = True
        self.spin_resistance.setEnabled(False)
        self.btn_zero.setEnabled(False)
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)

        # Clear session buffers for the new recording
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_force_data = []
        self.full_spo2_data = []

        self.time_data.clear()
        self.rom_data.clear()
        self.speed_data.clear()
        self.force_data.clear()
        self.spo2_data.clear()

        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.rep_peak_forces = []
        self.fatigue_index_pct = 100.0
        self.smoothness_vel_buf.clear()
        self.smoothness_score = 92.0
        self.session_baseline_rom = self.current_rom
        self.progress_reps.setValue(0)

        self.early_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_force_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.cur_rep_angle_forces = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.latest_rep_rom_curve = []
        self.latest_rep_force_curve = []
        self.fatigue_drop_angle = None
        self.fatigue_drop_delta = 0.0
        self.fatigue_drop_pct = 100.0
        self.cur_rep_angle_smoothness = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.recent_rep_smooth_bins = [[] for _ in range(self.NUM_ANGLE_BINS)]
        self.smoothness_angle_profile = np.full(self.NUM_ANGLE_BINS, 92.0, dtype=np.float32)
        self.smoothness_min_angle = None
        self.smoothness_min_score = 92.0

        # Clear curves and reset plot viewports cleanly to 0.0s for the new test
        self.curve_rom.setData([], [])
        self.curve_force_live.setData([], [])
        self.curve_force_baseline.setData([], [])
        self.curve_smooth_angle.setData([], [])
        self.deficit_marker.setData([], [])
        self.deficit_callout.setText("")
        self.fatigue_marker.setData([], [])
        self.fatigue_callout.setText("")
        self.smooth_marker.setData([], [])
        self.smooth_callout.setText("")

        self.plot_rom.setXRange(0.0, self.time_window, padding=0)
        if self.force_plot_mode == "TIME":
            self.plot_force.setXRange(0.0, self.time_window, padding=0)
        else:
            self.plot_force.setXRange(0.0, 160.0, padding=0)
        self._last_x_max = self.time_window

        self.lbl_timer.setText("0.0 s")

        self._start_time = time.time()
        self.elapsed_time = 0.0
        self.ticks = 0
        self._hw_start_ms = None

        self.btn_start_stop.setText("⏹  Stop Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px;
                font-weight: bold;
                background-color: #5c1a1a;
                border: 2px solid {COLORS['danger']};
                border-radius: 8px;
                color: {COLORS['danger']};
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: white;
            }}
        """)

        if not self.hw.is_connected:
            self.hw.connect()

        if self.hw.is_connected:
            self.hw.start_streaming(target_resistance=target_resistance)
            self.lbl_status.setText("● RECORDING (Live Hardware)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.generator = LiveDataGenerator(target_resistance=target_resistance)
            self.lbl_status.setText("● RECORDING (Simulation Mode)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['info']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['info']};")

        if not self.timer.isActive():
            self.timer.start()

    def _stop_test(self):
        self.is_running = False

        if self.hw.is_connected:
            self.hw.stop_streaming()
        self.generator = None

        self.lbl_status.setText("● COMPLETE - Review & Save or Discard")
        self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['warning']};")

        self.btn_start_stop.setVisible(True)
        self.btn_start_stop.setText("▶  Start New Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px;
                font-weight: bold;
                background-color: {COLORS['accent_dark']};
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
        """)
        self.btn_save.setVisible(True)
        self.btn_discard.setVisible(True)
        self.spin_resistance.setEnabled(True)
        self.btn_zero.setEnabled(True)

    def _save_test(self):
        if not self.full_time_data:
            self._discard_test()
            return

        target_resistance = self.spin_resistance.value()
        forearm_pin = self.get_forearm_pin()
        forearm_inches = self.get_forearm_inches()
        observed_max_rom = self.max_session_rom if self.max_session_rom > 0 else (max(self.full_rom_data) if self.full_rom_data else 0.0)
        observed_max_force = self.max_session_force if self.max_session_force > 0 else (max(self.full_force_data) if self.full_force_data else 0.0)
        peak_torque_in_lb = observed_max_force * forearm_inches

        deficit_str = f"Stall at {self.last_deficit_angle:.1f}° ({self.last_deficit_force:.1f} lbs)" if self.last_deficit_angle else "Full Strength"
        notes = (
            f"Reps: {self.reps_count}/{self.target_reps} | Peak ROM: {observed_max_rom:.1f}° | "
            f"Peak Force: {observed_max_force:.1f} lbs ({peak_torque_in_lb:.1f} in-lb) | "
            f"Fatigue Index: {self.fatigue_index_pct:.0f}% | Smoothness: {self.smoothness_score:.0f}% | "
            f"Forearm: Pin {forearm_pin} ({forearm_inches:.0f}\") | Deficit: {deficit_str} | Work: {self.therapy_work_j:.0f} J"
        )

        session_id = self.db.create_session(
            self.client_id, target_resistance, round(observed_max_rom, 1),
            notes=notes, forearm_pin=forearm_pin, forearm_length_in=forearm_inches
        )
        self.db.save_test_data_batch(
            session_id,
            self.full_time_data,
            self.full_rom_data,
            self.full_speed_data,
            self.full_force_data,
            self.full_spo2_data,
        )
        self.db.complete_session(session_id)

        self.test_completed.emit(session_id)
        self._reset()
        self.lbl_status.setText("● SAVED TO DATABASE - Live Preview Ready")
        self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")

    def _discard_test(self):
        self._reset()
        self.lbl_status.setText("● DISCARDED - Live Preview Ready")
        self.lbl_status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['danger']};")

    def _append_sample(self, t_val, rom, speed, force, spo2):
        self.full_time_data.append(t_val)
        self.full_rom_data.append(rom)
        self.full_speed_data.append(speed)
        self.full_force_data.append(force)
        self.full_spo2_data.append(spo2)

        # Deque automatically maintains maxlen with O(1) circular buffer, zero list copying
        self.time_data.append(t_val)
        self.rom_data.append(rom)
        self.speed_data.append(speed)
        self.force_data.append(force)
        self.spo2_data.append(spo2)
        self.ticks += 1
        self.current_spo2 = spo2

        # Latch true physiological peak ROM (preventing uncalibrated spin away)
        clamped_rom = max(0.0, min(180.0, rom))
        if clamped_rom > self.max_session_rom:
            self.max_session_rom = clamped_rom

        # Latch true peak applied force
        if force > self.max_session_force:
            self.max_session_force = force

        # Mechanical Work Integration (Concentric phase)
        if len(self.full_rom_data) >= 2:
            d_rom = self.full_rom_data[-1] - self.full_rom_data[-2]
            if d_rom > 0 and speed > 5.0:
                forearm_m = self.get_forearm_meters()
                d_s = forearm_m * (d_rom * np.pi / 180.0)
                f_newtons = force * 4.44822
                self.therapy_work_j += f_newtons * d_s

        # Angular binning for real-time tracking (10° per bin across 0° - 160°)
        clamped_angle = max(0.0, min(159.9, rom))
        angle_bin = int(clamped_angle // 10.0)
        if 0 <= angle_bin < self.NUM_ANGLE_BINS:
            self.cur_rep_angle_forces[angle_bin].append(force)

        # Smoothness calculation using rolling window of velocities
        self.smoothness_vel_buf.append(speed)
        if len(self.smoothness_vel_buf) >= 20:
            sub_v = np.asarray(self.smoothness_vel_buf)
            max_v = float(np.max(np.abs(sub_v)))
            if max_v > 10.0:
                kernel = np.ones(7) / 7.0
                v_smooth = np.convolve(sub_v, kernel, mode='same')
                v_noise = sub_v - v_smooth
                tremor_ratio = float(np.std(v_noise) / max(8.0, float(np.max(np.abs(v_smooth)))))
                raw_score = max(35.0, min(98.0, 100.0 * (1.0 - 1.6 * tremor_ratio)))
                self.smoothness_score = 0.94 * self.smoothness_score + 0.06 * raw_score

                # Map tremor to current joint angle bin (accumulate samples during movement)
                if 0 <= angle_bin < self.NUM_ANGLE_BINS:
                    self.cur_rep_angle_smoothness[angle_bin].append(raw_score)

        # Adaptive Repetition State Machine
        target_r = self.spin_resistance.value()
        if not hasattr(self, 'current_rep_peak'):
            self.current_rep_peak = 0.0

        if self.rep_state in ("EXTENDED", "IDLE"):
            if rom < self.session_baseline_rom or self.ticks <= 5:
                self.session_baseline_rom = rom

            if rom > (self.session_baseline_rom + 25.0) and speed > 10.0:
                self.rep_state = "FLEXING"
                self.current_rep_peak = rom
                self.rep_rom_buf = [rom]
                self.rep_force_buf = [force]
        elif self.rep_state == "FLEXING":
            self.rep_rom_buf.append(rom)
            self.rep_force_buf.append(force)
            if rom > self.current_rep_peak:
                self.current_rep_peak = rom
            # Detect apex: excursion >= 30 deg and arm starts returning
            if (self.current_rep_peak - self.session_baseline_rom) >= 30.0 and speed < -8.0:
                self.rep_state = "EXTENDING"
        elif self.rep_state == "EXTENDING":
            # Rep completed when arm returns near baseline extension or below 35 deg
            if rom <= max(35.0, self.session_baseline_rom + 15.0):
                self.reps_count += 1
                self.rep_state = "EXTENDED"

                # Save the completed concentric rep curves so each rep overwrites cleanly on plot
                if self.rep_rom_buf:
                    self.latest_rep_rom_curve = list(self.rep_rom_buf)
                    self.latest_rep_force_curve = list(self.rep_force_buf)

                # Peak force recorded for this rep & Fatigue Index calculation
                if self.rep_force_buf:
                    rep_pk = float(max(self.rep_force_buf))
                    self.rep_peak_forces.append(rep_pk)
                    if len(self.rep_peak_forces) >= 2:
                        early_mean = float(np.mean(self.rep_peak_forces[:2]))
                        recent_mean = float(np.mean(self.rep_peak_forces[-2:]))
                        if early_mean > 0.5:
                            raw_fi = (recent_mean / early_mean) * 100.0
                            self.fatigue_index_pct = max(10.0, min(100.0, raw_fi))
                        else:
                            self.fatigue_index_pct = 100.0
                    else:
                        self.fatigue_index_pct = 100.0

                # Commit per-angle forces for completed rep & compute Fatigue Drop vs Angle
                for b in range(self.NUM_ANGLE_BINS):
                    if self.cur_rep_angle_forces[b]:
                        mean_b_f = float(np.mean(self.cur_rep_angle_forces[b]))
                        if self.reps_count <= 2:
                            self.early_rep_force_bins[b].append(mean_b_f)
                        self.recent_rep_force_bins[b].append(mean_b_f)
                        if len(self.recent_rep_force_bins[b]) > 2:
                            self.recent_rep_force_bins[b].pop(0)
                        self.cur_rep_angle_forces[b] = []
                    else:
                        self.cur_rep_angle_forces[b] = []

                # Commit per-angle smoothness for completed rep & update smoothness profile
                for b in range(self.NUM_ANGLE_BINS):
                    if self.cur_rep_angle_smoothness[b]:
                        mean_b_s = float(np.mean(self.cur_rep_angle_smoothness[b]))
                        self.recent_rep_smooth_bins[b].append(mean_b_s)
                        if len(self.recent_rep_smooth_bins[b]) > 3:
                            self.recent_rep_smooth_bins[b].pop(0)
                        self.smoothness_angle_profile[b] = float(np.mean(self.recent_rep_smooth_bins[b]))
                        self.cur_rep_angle_smoothness[b] = []
                    else:
                        self.cur_rep_angle_smoothness[b] = []

                # Apply spatial 3-point filter across adjacent bins for stable, natural profile
                active_smooth_b = [b for b in range(self.NUM_ANGLE_BINS) if self.recent_rep_smooth_bins[b]]
                if len(active_smooth_b) >= 3:
                    prof_copy = np.copy(self.smoothness_angle_profile)
                    for b in range(1, self.NUM_ANGLE_BINS - 1):
                        if b in active_smooth_b:
                            self.smoothness_angle_profile[b] = 0.25 * prof_copy[b - 1] + 0.5 * prof_copy[b] + 0.25 * prof_copy[b + 1]

                if active_smooth_b:
                    min_b = min(active_smooth_b, key=lambda b: self.smoothness_angle_profile[b])
                    self.smoothness_min_score = float(self.smoothness_angle_profile[min_b])
                    self.smoothness_min_angle = float(self.angle_bin_centers[min_b])

                if self.reps_count >= 2:
                    drop_candidates = []
                    for b in range(self.NUM_ANGLE_BINS):
                        if self.early_rep_force_bins[b] and self.recent_rep_force_bins[b]:
                            base_f = float(np.mean(self.early_rep_force_bins[b]))
                            rec_f = float(np.mean(self.recent_rep_force_bins[b]))
                            if base_f > 1.0:
                                drop = base_f - rec_f
                                drop_candidates.append((drop, b, base_f, rec_f))
                    if drop_candidates:
                        drop_candidates.sort(key=lambda x: x[0], reverse=True)
                        best_drop, best_b, b_base, b_rec = drop_candidates[0]
                        if best_drop >= 0.5:
                            self.fatigue_drop_angle = float(self.angle_bin_centers[best_b])
                            self.fatigue_drop_delta = float(best_drop)
                            self.fatigue_drop_pct = float(b_rec / max(0.1, b_base) * 100.0)
                        else:
                            self.fatigue_drop_angle = None
                            self.fatigue_drop_delta = 0.0

                # Analyze concentric buffer for force deficit valley
                if self.rep_rom_buf:
                    r_arr = np.asarray(self.rep_rom_buf)
                    f_arr = np.asarray(self.rep_force_buf)
                    mask = (r_arr >= 40.0) & (r_arr <= 110.0)
                    if np.any(mask):
                        mid_f = f_arr[mask]
                        mid_r = r_arr[mask]
                        min_idx = np.argmin(mid_f)
                        min_force = float(mid_f[min_idx])
                        min_angle = float(mid_r[min_idx])
                        if min_force < target_r * 0.80:
                            self.last_deficit_angle = min_angle
                            self.last_deficit_force = min_force
                        else:
                            self.last_deficit_angle = None
                            self.last_deficit_force = None
                self.rep_rom_buf = []
                self.rep_force_buf = []

    def _update_data(self):
        target_r = self.spin_resistance.value()
        new_data = False

        if self.is_running:
            self.elapsed_time = time.time() - self._start_time

            if self.hw.is_connected:
                samples = self.hw.read_samples()
                if samples:
                    for sample in samples:
                        t_ms = sample[0]
                        rom = sample[2]
                        speed = sample[3]
                        load = sample[4]
                        spo2 = float(sample[6]) if len(sample) > 6 else 0.0
                        force_val = max(0.0, float(load))

                        self.current_rom = rom
                        self.current_speed = speed
                        self.current_force = force_val
                        self.current_spo2 = spo2

                        if self._hw_start_ms is None:
                            self._hw_start_ms = t_ms
                        sample_time = max(0.0, (t_ms - self._hw_start_ms) / 1000.0)
                        self._append_sample(sample_time, rom, speed, force_val, spo2)
                    new_data = True
            elif self.generator:
                sample_time = max(0.0, time.time() - self._start_time)
                rom, speed, force_val, spo2 = self.generator.next_sample(sample_time)
                self.current_rom = rom
                self.current_speed = speed
                self.current_force = force_val
                self.current_spo2 = spo2
                self._append_sample(sample_time, rom, speed, force_val, spo2)
                new_data = True
        else:
            # IDLE state: If hardware is connected, update instantaneous numbers without plotting or scrolling
            if self.hw.is_connected:
                self.current_rom = self.hw.last_angle
                self.current_speed = self.hw.last_velocity
                self.current_force = max(0.0, float(self.hw.last_load_cell))
                self.current_spo2 = getattr(self.hw, 'last_spo2', 0.0)

        # Plot updates: ONLY update when actively running and new data is present!
        if self.is_running and new_data and self.time_data:
            t = np.asarray(self.time_data, dtype=np.float32)
            rom_arr = np.asarray(self.rom_data, dtype=np.float32)
            force_arr = np.asarray(self.force_data, dtype=np.float32)
            current_t = float(self.time_data[-1])

            # Auto-scale force Y axis ONLY if range changed by > 0.5 lbs
            y_max = max(25.0, target_r * 1.5, self.max_session_force * 1.25)
            if abs(y_max - self._last_y_max) > 0.5:
                self._last_y_max = y_max
                self.plot_force.setYRange(0, y_max, padding=0)

            # 1. Update Hero Plot 1: ROM vs. Time
            if self.panel_rom.isVisible():
                self.curve_rom.setData(t, rom_arr)
                if current_t > self.time_window:
                    x_min = current_t - self.time_window
                    x_max = current_t
                    if abs(x_max - self._last_x_max) > 0.05:
                        self._last_x_max = x_max
                        self.plot_rom.setXRange(x_min, x_max, padding=0)
                elif self._last_x_max != self.time_window:
                    self._last_x_max = self.time_window
                    self.plot_rom.setXRange(0.0, self.time_window, padding=0)

            # 2. Update Hero Plot 2: Force (Time, Force/Angle, Smooth/Angle)
            if self.panel_force.isVisible():
                if self.force_plot_mode == "TIME":
                    self.curve_force_live.setData(t, force_arr)
                    if current_t > self.time_window:
                        x_min = current_t - self.time_window
                        x_max = current_t
                        if abs(x_max - self._last_x_max) > 0.05:
                            self.plot_force.setXRange(x_min, x_max, padding=0)
                        self.lbl_target_force_line.setPos(x_max - 0.4, target_r + 0.2)
                    else:
                        self.lbl_target_force_line.setPos(self.time_window - 0.4, target_r + 0.2)
                elif self.force_plot_mode == "FORCE_ANGLE":
                    # Display concentric stroke for current rep or completed rep cleanly
                    if len(self.rep_rom_buf) >= 3:
                        r_pts = np.asarray(self.rep_rom_buf, dtype=np.float32)
                        f_pts = np.asarray(self.rep_force_buf, dtype=np.float32)
                        s_idx = np.argsort(r_pts)
                        r_sorted = r_pts[s_idx]
                        f_sorted = f_pts[s_idx]
                        if len(f_sorted) >= 7:
                            kernel = np.ones(5) / 5.0
                            f_smooth = np.convolve(f_sorted, kernel, mode='same')
                            self.curve_force_live.setData(r_sorted, f_smooth)
                        else:
                            self.curve_force_live.setData(r_sorted, f_sorted)
                    elif self.latest_rep_rom_curve and len(self.latest_rep_rom_curve) >= 3:
                        r_pts = np.asarray(self.latest_rep_rom_curve, dtype=np.float32)
                        f_pts = np.asarray(self.latest_rep_force_curve, dtype=np.float32)
                        s_idx = np.argsort(r_pts)
                        r_sorted = r_pts[s_idx]
                        f_sorted = f_pts[s_idx]
                        if len(f_sorted) >= 7:
                            kernel = np.ones(5) / 5.0
                            f_smooth = np.convolve(f_sorted, kernel, mode='same')
                            self.curve_force_live.setData(r_sorted, f_smooth)
                        else:
                            self.curve_force_live.setData(r_sorted, f_sorted)
                    elif self.reps_count >= 1:
                        valid_b = [b for b in range(self.NUM_ANGLE_BINS) if self.recent_rep_force_bins[b]]
                        if valid_b:
                            x_pts = self.angle_bin_centers[valid_b]
                            y_pts = np.asarray([np.mean(self.recent_rep_force_bins[b]) for b in valid_b], dtype=np.float32)
                            self.curve_force_live.setData(x_pts, y_pts)
                        else:
                            self.curve_force_live.setData([], [])
                    else:
                        self.curve_force_live.setData([], [])

                    if self.reps_count >= 2:
                        base_c = [float(np.mean(self.early_rep_force_bins[b])) if self.early_rep_force_bins[b] else 0.0 for b in range(self.NUM_ANGLE_BINS)]
                        self.curve_force_baseline.setData(self.angle_bin_centers, np.asarray(base_c, dtype=np.float32))
                    else:
                        self.curve_force_baseline.setData([], [])

                    if self.fatigue_drop_angle is not None:
                        b_drop = int(self.fatigue_drop_angle // 10)
                        rec_f = float(np.mean(self.recent_rep_force_bins[b_drop])) if (b_drop < self.NUM_ANGLE_BINS and self.recent_rep_force_bins[b_drop]) else (target_r - self.fatigue_drop_delta)
                        self.fatigue_marker.setData([self.fatigue_drop_angle], [rec_f])
                        self.fatigue_callout.setPos(self.fatigue_drop_angle, rec_f)
                        self.fatigue_callout.setText(f"Drop: {self.fatigue_drop_angle:.0f}° (-{self.fatigue_drop_delta:.1f} lbs)")
                    else:
                        self.fatigue_marker.setData([], [])
                        self.fatigue_callout.setText("")

                    if self.last_deficit_angle is not None:
                        self.deficit_marker.setData([self.last_deficit_angle], [self.last_deficit_force])
                        self.deficit_callout.setPos(self.last_deficit_angle, self.last_deficit_force)
                        self.deficit_callout.setText(f"Stall: {self.last_deficit_angle:.1f}° ({self.last_deficit_force:.1f} lbs)")
                    else:
                        self.deficit_marker.setData([], [])
                        self.deficit_callout.setText("")
                elif self.force_plot_mode == "SMOOTH_ANGLE":
                    valid_b = [b for b in range(self.NUM_ANGLE_BINS) if self.recent_rep_smooth_bins[b]]
                    if valid_b:
                        x_pts = self.angle_bin_centers[valid_b]
                        y_pts = np.asarray([self.smoothness_angle_profile[b] for b in valid_b], dtype=np.float32)
                        self.curve_smooth_angle.setData(x_pts, y_pts)
                    elif self.reps_count > 0 or len(self.full_time_data) >= 30:
                        self.curve_smooth_angle.setData(self.angle_bin_centers, self.smoothness_angle_profile)
                    else:
                        self.curve_smooth_angle.setData([], [])

                    # Flag movement hitch only for significant tremor deficit (< 80%)
                    if self.smoothness_min_angle is not None and self.smoothness_min_score < 80.0:
                        self.smooth_marker.setData([self.smoothness_min_angle], [self.smoothness_min_score])
                        self.smooth_callout.setPos(self.smoothness_min_angle, self.smoothness_min_score)
                        self.smooth_callout.setText(f"Hitch: {self.smoothness_min_angle:.0f}° ({self.smoothness_min_score:.0f}%)")
                    else:
                        self.smooth_marker.setData([], [])
                        self.smooth_callout.setText("")

        # Update HUD Cards
        pct_reps = int(min(100.0, (self.reps_count / max(1, self.target_reps)) * 100.0))
        self.progress_reps.setValue(min(self.reps_count, self.target_reps))

        if self.is_running:
            self.lbl_hud_reps.setText(f"{self.reps_count} / {self.target_reps} Reps")
            self.lbl_hud_reps_sub.setText(f"Target: {self.target_reps} Reps ({pct_reps}%)")
            self.lbl_hud_rom.setText(f"{self.max_session_rom:.1f}°")
            self.lbl_hud_rom_sub.setText(f"Live: {self.current_rom:.0f}° • Peak: {self.max_session_rom:.0f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
            tgt_txt = f"{target_r:.0f} lbs" if target_r.is_integer() else f"{target_r:.1f} lbs"
            if self.last_deficit_angle is not None:
                self.lbl_hud_force_sub.setText(f"Stall: {self.last_deficit_angle:.1f}° ({self.last_deficit_force:.1f} lbs)")
                if self._last_deficit_style_active is not True:
                    self._last_deficit_style_active = True
                    self.lbl_hud_force_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['warning']};")
            else:
                self.lbl_hud_force_sub.setText(f"{tgt_txt} • {self.therapy_work_j:.0f} J")
                if self._last_deficit_style_active is not False:
                    self._last_deficit_style_active = False
                    self.lbl_hud_force_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_secondary']};")

            # Fatigue Index Card
            if self.fatigue_drop_angle is not None:
                self.lbl_hud_fatigue.setText(f"{self.fatigue_index_pct:.0f}%")
                self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['warning']};")
                self.lbl_hud_fatigue_sub.setText(f"Drop at {self.fatigue_drop_angle:.0f}° (-{self.fatigue_drop_delta:.1f} lbs)")
                self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['warning']};")
            elif len(self.rep_peak_forces) >= 2:
                self.lbl_hud_fatigue.setText(f"{self.fatigue_index_pct:.0f}%")
                if self.fatigue_index_pct >= 90.0:
                    self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['accent']};")
                    self.lbl_hud_fatigue_sub.setText("● Good Endurance")
                    self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['accent']};")
                elif self.fatigue_index_pct >= 75.0:
                    self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['warning']};")
                    self.lbl_hud_fatigue_sub.setText("● Mild Fatigue")
                    self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['warning']};")
                else:
                    self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['danger']};")
                    self.lbl_hud_fatigue_sub.setText("● High Fatigue")
                    self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['danger']};")
            else:
                self.lbl_hud_fatigue.setText("100%")
                self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['accent']};")
                self.lbl_hud_fatigue_sub.setText("● Baseline Level")
                self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_secondary']};")

            # Movement Smoothness Card
            if self.smoothness_min_angle is not None and self.smoothness_min_score < 80.0:
                self.lbl_hud_smoothness.setText(f"{self.smoothness_score:.0f}%")
                self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['warning']};")
                self.lbl_hud_smoothness_sub.setText(f"Hitch at {self.smoothness_min_angle:.0f}° ({self.smoothness_min_score:.0f}%)")
                self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['warning']};")
            elif self.reps_count > 0 or len(self.full_time_data) >= 30:
                self.lbl_hud_smoothness.setText(f"{self.smoothness_score:.0f}%")
                if self.smoothness_score >= 85.0:
                    self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS.get('accent_cyan', '#00e5ff')};")
                    self.lbl_hud_smoothness_sub.setText("● Fluid (0°-160°)")
                    self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS.get('accent_cyan', '#00e5ff')};")
                elif self.smoothness_score >= 70.0:
                    self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['warning']};")
                    self.lbl_hud_smoothness_sub.setText("● Moderate Tremor")
                    self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['warning']};")
                else:
                    self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['danger']};")
                    self.lbl_hud_smoothness_sub.setText("● Jerky Motion")
                    self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['danger']};")
            else:
                self.lbl_hud_smoothness.setText("---%")
                self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['text_muted']};")
                self.lbl_hud_smoothness_sub.setText("Awaiting Movement")
                self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")

            if self.time_data:
                self.lbl_timer.setText(f"{self.time_data[-1]:.1f} s")
        elif not self.btn_save.isVisible():
            # IDLE / Pre-test mode
            self.lbl_hud_reps.setText(f"0 / {self.target_reps} Reps")
            self.lbl_hud_reps_sub.setText(f"Target: {self.target_reps} Reps (0%)")
            self.lbl_hud_rom.setText(f"{self.current_rom:.1f}°")
            self.lbl_hud_rom_sub.setText(f"Live Angle: {self.current_rom:.0f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
            tgt_txt = f"{target_r:.0f} lbs" if target_r.is_integer() else f"{target_r:.1f} lbs"
            self.lbl_hud_force_sub.setText(f"{tgt_txt} • 0 J")
            self.lbl_hud_fatigue.setText("100%")
            self.lbl_hud_fatigue.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['accent']};")
            self.lbl_hud_fatigue_sub.setText("● Baseline Level")
            self.lbl_hud_fatigue_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_secondary']};")
            self.lbl_hud_smoothness.setText("---%")
            self.lbl_hud_smoothness.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['text_muted']};")
            self.lbl_hud_smoothness_sub.setText("Awaiting Movement")
            self.lbl_hud_smoothness_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
            self.lbl_timer.setText("0.0 s")
        else:
            # Post-test review mode (Save/Discard visible)
            self.lbl_hud_reps.setText(f"{self.reps_count} / {self.target_reps} Reps")
            self.lbl_hud_reps_sub.setText(f"Target: {self.target_reps} Reps ({pct_reps}%)")
            self.lbl_hud_rom_sub.setText(f"Live: {self.current_rom:.0f}° • Peak: {self.max_session_rom:.0f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
            tgt_txt = f"{target_r:.0f} lbs" if target_r.is_integer() else f"{target_r:.1f} lbs"
            self.lbl_hud_force_sub.setText(f"{tgt_txt} • {self.therapy_work_j:.0f} J")

        # SpO2 Vitals Display - ONLY update stylesheet on state transition!
        spo2_active = (self.current_spo2 > 0.0)
        if spo2_active:
            self.lbl_hud_spo2.setText(f"{self.current_spo2:.0f}%")
            if self._last_spo2_active != True:
                self._last_spo2_active = True
                self.lbl_hud_spo2.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS.get('accent_cyan', '#00e5ff')};")
                self.lbl_hud_spo2_sub.setText("● Sensor Active")
                self.lbl_hud_spo2_sub.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLORS['accent']};")
        else:
            self.lbl_hud_spo2.setText("---%")
            if self._last_spo2_active != False:
                self._last_spo2_active = False
                self.lbl_hud_spo2.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['text_muted']};")
                self.lbl_hud_spo2_sub.setText("Place Finger on Sensor")
                self.lbl_hud_spo2_sub.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
