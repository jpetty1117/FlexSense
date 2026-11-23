"""
Rehab Test System - Streamlined Dev & Calibration Workstation
-------------------------------------------------------------
Unified, ergonomic developer workstation:
  1. Top Live Sensor HUD Strip (Angle, Speed, Force, Carriage, SpO2, TMC2209)
  2. Quick Hardware Actions (Zero Encoder, Zero Motor, Tare Load Cell, Query TMC, Reset Arrest)
  3. Stepper Carriage Position Control (Jog buttons, set pos, quick presets, smooth slider, zero motor)
  4. Command Target Load & Shaft Torque with Forearm Pin Selection and instant LUT displacement preview
  5. Homing & TMC2209 Motor Tuning + High-Speed Descent Drop Arrest Safety Control
  6. Single-Curl Torque-Domain LUT Calibration (Peak latch, point capture, fit & export to brake_lut.h, pio rebuild)
  7. Dual PyQtGraph Visualizers: Torque Calibration Curve + Real-Time Live Curl Force Stripchart
  8. Interactive Serial Command Terminal & Activity Log (VCP / USB CDC)
"""

import os
import sys
import json
import time
import subprocess
from collections import deque
import numpy as np
import pyqtgraph as pg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QLineEdit, QCheckBox, QGroupBox,
    QGridLayout, QMessageBox, QSizePolicy, QScrollArea, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

try:
    from theme import COLORS
except ImportError:
    from gui.theme import COLORS

try:
    from hardware_interface import STM32EncoderInterface
except ImportError:
    from gui.hardware_interface import STM32EncoderInterface

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class DevToolsScreen(QWidget):
    """Unified developer, diagnostics, and calibration workstation."""

    def __init__(self, db, hw=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.hw = hw or STM32EncoderInterface()

        # Telemetry & state
        self.live_timestamp_ms = 0
        self.live_angle = 0.0
        self.live_speed = 0.0
        self.live_force = 0.0
        self.live_torque = 0.0
        self.live_carriage_mm = 0.0
        self.live_spo2 = 0.0

        self.forearm_length_in = 12.0  # Default Pin 4: 12.0 inches
        self.commanded_pos_mm = 0.0
        self.commanded_load_lbs = 10.0
        self.commanded_torque_lbf_in = 120.0
        self.peak_curl_force = 0.0
        self.peak_curl_torque = 0.0
        self.captured_lut_points = []  # List of tuples: (pos_mm, force_lbs, torque_lbf_in)

        self._last_term_stream_t = 0.0

        # Rolling buffer for real-time curl force stripchart
        self._strip_time = deque(maxlen=200)
        self._strip_force = deque(maxlen=200)
        self._strip_start_t = time.time()

        self._build_ui()
        self._setup_telemetry_timer()
        self._probe_hardware()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.hw.is_connected:
            self._probe_hardware()
        elif not getattr(self.hw, 'is_streaming', False):
            self.hw.start_streaming()
        # Query current motor direction polarity, driver status, and forearm setting
        self._send_raw_command("DIR?")
        self._send_raw_command("TMC")
        self._send_raw_command(f"ARM {self.forearm_length_in:.1f}")

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.hw and self.hw.is_connected and getattr(self.hw, 'is_streaming', False):
            self.hw.stop_streaming()

    # ─────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 6, 10, 6)
        root_layout.setSpacing(6)

        # ── 1. Header Bar ──
        header = QHBoxLayout()
        header.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("Dev & Calibration Workstation")
        title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 16px; font-weight: bold;")
        title_box.addWidget(title)

        subtitle = QLabel("Torque-Domain Kinematic LUT • Stepper Positioning • High-Speed Descent Drop Arrest • Multi-Sensor HUD")
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)

        header.addStretch()

        self.lbl_hw_status = QLabel("Checking hardware...")
        self.lbl_hw_status.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        header.addWidget(self.lbl_hw_status)

        self.btn_reconnect = QPushButton("Probe USB")
        self.btn_reconnect.setFixedHeight(28)
        self.btn_reconnect.setCursor(Qt.PointingHandCursor)
        self.btn_reconnect.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        self.btn_reconnect.clicked.connect(self._probe_hardware)
        header.addWidget(self.btn_reconnect)

        root_layout.addLayout(header)

        # ── 1B. Emergency Descent Drop Arrest Alert Banner ──
        self.lbl_arrest_banner = QLabel("🛑 DESCENT DROP ARREST ENGAGED: Rapid drop detected! Brake locked to halt handle fall.")
        self.lbl_arrest_banner.setStyleSheet("""
            QLabel {
                background-color: #8b0000;
                color: #ffffff;
                border: 2px solid #f85149;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 5px 12px;
            }
        """)
        self.lbl_arrest_banner.setVisible(False)
        root_layout.addWidget(self.lbl_arrest_banner)

        # ── 2. Top Live Sensor HUD Strip & Hardware Action Toolbar ──
        root_layout.addWidget(self._build_sensor_hud())

        # ── 3. Two-Column Main Body ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)

        # Left Column: Wrapped in smooth QScrollArea so nothing clips in split-window mode
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #161b22;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #58a6ff;
            }
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        left_col = QVBoxLayout(scroll_content)
        left_col.setContentsMargins(0, 0, 4, 0)
        left_col.setSpacing(6)

        # A. Stepper Position & Jog Panel
        left_col.addWidget(self._build_position_panel())

        # B. Command Target Load & Shaft Torque Panel
        left_col.addWidget(self._build_load_panel())

        # C. Homing & Motor Configuration + Descent Safety Panel
        left_col.addWidget(self._build_homing_panel())

        # D. Single-Curl Torque LUT Calibration Panel
        left_col.addWidget(self._build_lut_panel())

        scroll_area.setWidget(scroll_content)
        body_layout.addWidget(scroll_area, stretch=6)

        # Right Column: Visualizers (Torque LUT Curve + Live Curl Stripchart) & Serial Terminal
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # Top Right: PyQtGraph Calibration Curve Plot (Torque vs Displacement)
        right_col.addWidget(self._build_plot_panel(), stretch=5)

        # Middle Right: Real-Time Live Curl Force Stripchart
        right_col.addWidget(self._build_stripchart_panel(), stretch=3)

        # Bottom Right: Serial Activity Log & Terminal
        right_col.addWidget(self._build_terminal_panel(), stretch=4)

        body_layout.addLayout(right_col, stretch=7)

        root_layout.addLayout(body_layout, stretch=1)

    # ─────────────────────────────────────────────────────────
    # Sub-Panels: Sensor HUD & Hardware Actions
    # ─────────────────────────────────────────────────────────
    def _build_sensor_hud(self):
        """Top live telemetry HUD cards and hardware quick action buttons."""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(5)

        # Row 1: 6 Sensor Readout Tiles
        grid = QGridLayout()
        grid.setSpacing(6)

        def make_tile(title_text, val_obj, sub_obj, col_idx):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLORS['bg_surface']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(6, 3, 6, 3)
            c_lay.setSpacing(1)

            lbl_t = QLabel(title_text)
            lbl_t.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: bold; border: none;")
            c_lay.addWidget(lbl_t)
            c_lay.addWidget(val_obj)
            c_lay.addWidget(sub_obj)
            grid.addWidget(card, 0, col_idx)

        # 1. Joint Angle (TIM2 2:1 belt)
        self.lbl_hud_angle_val = QLabel("0.0°")
        self.lbl_hud_angle_val.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 15px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_angle_sub = QLabel("TIM2 (2:1 belt)")
        self.lbl_hud_angle_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("JOINT ANGLE", self.lbl_hud_angle_val, self.lbl_hud_angle_sub, 0)

        # 2. Joint Angular Velocity
        self.lbl_hud_vel_val = QLabel("0.0 °/s")
        self.lbl_hud_vel_val.setStyleSheet(f"color: {COLORS['info']}; font-size: 15px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_vel_sub = QLabel("100 Hz velocity")
        self.lbl_hud_vel_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("ANGULAR SPEED", self.lbl_hud_vel_val, self.lbl_hud_vel_sub, 1)

        # 3. Handle Force & Shaft Torque
        self.lbl_hud_force_val = QLabel("0.0 lbs")
        self.lbl_hud_force_val.setStyleSheet(f"color: {COLORS['graph_strength']}; font-size: 15px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_force_sub = QLabel("0.0 lbf·in (Pin 4)")
        self.lbl_hud_force_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("HANDLE / TORQUE", self.lbl_hud_force_val, self.lbl_hud_force_sub, 2)

        # 4. Stepper Carriage Position
        self.lbl_hud_pos_val = QLabel("0.0 mm")
        self.lbl_hud_pos_val.setStyleSheet(f"color: {COLORS['accent']}; font-size: 15px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_pos_sub = QLabel("Lead screw actual")
        self.lbl_hud_pos_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("CARRIAGE POS", self.lbl_hud_pos_val, self.lbl_hud_pos_sub, 3)

        # 5. Pulse Oximetry (MAX30102)
        self.lbl_hud_spo2_val = QLabel("-- %")
        self.lbl_hud_spo2_val.setStyleSheet("color: #ff6b6b; font-size: 15px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_spo2_sub = QLabel("MAX30102 SpO2")
        self.lbl_hud_spo2_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("PULSE OXIMETRY", self.lbl_hud_spo2_val, self.lbl_hud_spo2_sub, 4)

        # 6. TMC2209 Driver State
        self.lbl_hud_tmc_val = QLabel("Probing...")
        self.lbl_hud_tmc_val.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px; font-weight: bold; font-family: monospace; border: none;")
        self.lbl_hud_tmc_sub = QLabel("SG: --- | 1.3A")
        self.lbl_hud_tmc_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none;")
        make_tile("TMC2209 DRIVER", self.lbl_hud_tmc_val, self.lbl_hud_tmc_sub, 5)

        layout.addLayout(grid)

        # Row 2: Sensor & Hardware Diagnostic Toolbar
        row_bar = QHBoxLayout()
        row_bar.setSpacing(5)

        btn_z_enc = QPushButton("⟲ Zero Encoder")
        btn_z_enc.setFixedHeight(24)
        btn_z_enc.setCursor(Qt.PointingHandCursor)
        btn_z_enc.setStyleSheet(self._secondary_btn_style(COLORS['info']))
        btn_z_enc.clicked.connect(lambda: self._send_raw_command("ZERO"))
        row_bar.addWidget(btn_z_enc)

        btn_z_motor = QPushButton("⟲ Zero Motor")
        btn_z_motor.setFixedHeight(24)
        btn_z_motor.setCursor(Qt.PointingHandCursor)
        btn_z_motor.setStyleSheet(self._secondary_btn_style(COLORS['accent_cyan']))
        btn_z_motor.clicked.connect(self._zero_motor_pos)
        row_bar.addWidget(btn_z_motor)

        btn_t_lc = QPushButton("⚖ Tare Load Cell")
        btn_t_lc.setFixedHeight(24)
        btn_t_lc.setCursor(Qt.PointingHandCursor)
        btn_t_lc.setStyleSheet(self._secondary_btn_style(COLORS['warning']))
        btn_t_lc.clicked.connect(lambda: self._send_raw_command("TARE"))
        row_bar.addWidget(btn_t_lc)

        btn_q_tmc = QPushButton("🔍 Query TMC2209")
        btn_q_tmc.setFixedHeight(24)
        btn_q_tmc.setCursor(Qt.PointingHandCursor)
        btn_q_tmc.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_q_tmc.clicked.connect(lambda: self._send_raw_command("TMC"))
        row_bar.addWidget(btn_q_tmc)

        btn_reset_arrest = QPushButton("🔓 Unlock Arrest")
        btn_reset_arrest.setFixedHeight(24)
        btn_reset_arrest.setCursor(Qt.PointingHandCursor)
        btn_reset_arrest.setStyleSheet(self._secondary_btn_style(COLORS['danger']))
        btn_reset_arrest.clicked.connect(lambda: self._send_raw_command("RESETARREST"))
        row_bar.addWidget(btn_reset_arrest)

        row_bar.addStretch()

        btn_stream_start = QPushButton("▶ Start Stream")
        btn_stream_start.setFixedHeight(24)
        btn_stream_start.setCursor(Qt.PointingHandCursor)
        btn_stream_start.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_stream_start.clicked.connect(lambda: self._send_raw_command("START"))
        row_bar.addWidget(btn_stream_start)

        btn_stream_stop = QPushButton("⏸ Stop Stream")
        btn_stream_stop.setFixedHeight(24)
        btn_stream_stop.setCursor(Qt.PointingHandCursor)
        btn_stream_stop.setStyleSheet(self._secondary_btn_style(COLORS['danger']))
        btn_stream_stop.clicked.connect(lambda: self._send_raw_command("STOP"))
        row_bar.addWidget(btn_stream_stop)

        layout.addLayout(row_bar)

        return container

    # ─────────────────────────────────────────────────────────
    # Sub-Panels: Left Column
    # ─────────────────────────────────────────────────────────
    def _build_position_panel(self):
        """Stepper positioning, relative increments, presets, and slider."""
        grp = QGroupBox("1. Stepper Position Control (Jog && Set)")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        # Row 1: Live readout + Set position input + Send button + Zero Motor Pos
        row_pos = QHBoxLayout()
        row_pos.setSpacing(6)

        lbl_cp = QLabel("Curr Pos:")
        lbl_cp.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: bold;")
        row_pos.addWidget(lbl_cp)

        self.lbl_curr_pos = QLabel("0.0 mm")
        self.lbl_curr_pos.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']};
                border-radius: 5px;
                padding: 2px 7px;
                font-size: 12px;
                font-weight: bold;
                font-family: monospace;
            }}
        """)
        row_pos.addWidget(self.lbl_curr_pos)

        row_pos.addSpacing(6)

        lbl_sp = QLabel("Set Pos:")
        lbl_sp.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: bold;")
        row_pos.addWidget(lbl_sp)

        self.spin_stepper_pos = QDoubleSpinBox()
        self.spin_stepper_pos.setFixedWidth(78)
        self.spin_stepper_pos.setRange(-25.0, 35.0)
        self.spin_stepper_pos.setSingleStep(0.5)
        self.spin_stepper_pos.setDecimals(1)
        self.spin_stepper_pos.setSuffix(" mm")
        self.spin_stepper_pos.setValue(0.0)
        self.spin_stepper_pos.setStyleSheet(self._input_style())
        self.spin_stepper_pos.valueChanged.connect(self._on_pos_spin_changed)
        row_pos.addWidget(self.spin_stepper_pos)

        self.btn_send_pos = QPushButton("Move (POS)")
        self.btn_send_pos.setFixedHeight(28)
        self.btn_send_pos.setCursor(Qt.PointingHandCursor)
        self.btn_send_pos.setStyleSheet(self._primary_btn_style())
        self.btn_send_pos.clicked.connect(self._command_stepper_pos)
        row_pos.addWidget(self.btn_send_pos)

        self.btn_zero_motor = QPushButton("⟲ Zero Motor Pos")
        self.btn_zero_motor.setFixedHeight(28)
        self.btn_zero_motor.setCursor(Qt.PointingHandCursor)
        self.btn_zero_motor.setStyleSheet(self._secondary_btn_style(COLORS['accent_cyan']))
        self.btn_zero_motor.clicked.connect(self._zero_motor_pos)
        row_pos.addWidget(self.btn_zero_motor)

        row_pos.addStretch()
        layout.addLayout(row_pos)

        # Row 2: Relative Jog / Increment Buttons
        row_jog = QHBoxLayout()
        row_jog.setSpacing(4)

        lbl_jog = QLabel("Jog Step:")
        lbl_jog.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: bold;")
        row_jog.addWidget(lbl_jog)

        jog_steps = [
            ("-5.0", -5.0),
            ("-1.0", -1.0),
            ("-0.1", -0.1),
            ("+0.1", +0.1),
            ("+1.0", +1.0),
            ("+5.0", +5.0),
        ]
        for text, delta in jog_steps:
            btn_j = QPushButton(text)
            btn_j.setFixedHeight(24)
            btn_j.setCursor(Qt.PointingHandCursor)
            color = COLORS['danger'] if delta < 0 else COLORS['accent']
            btn_j.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_input']};
                    color: {color};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 10px;
                    padding: 2px 5px;
                }}
                QPushButton:hover {{
                    background-color: {color};
                    color: {COLORS['bg_dark']};
                }}
            """)
            btn_j.clicked.connect(lambda checked=False, d=delta: self._jog_stepper(d))
            row_jog.addWidget(btn_j)

        row_jog.addStretch()
        layout.addLayout(row_jog)

        # Row 3: Quick Preset Position Buttons
        row_presets = QHBoxLayout()
        row_presets.setSpacing(4)
        lbl_pre = QLabel("Presets:")
        lbl_pre.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: bold;")
        row_presets.addWidget(lbl_pre)

        presets = [
            ("-5 mm", -5.0),
            ("-2 mm", -2.0),
            ("0 mm", 0.0),
            ("2.5 mm", 2.5),
            ("6 mm", 6.0),
            ("9 mm", 9.0),
            ("12 mm", 12.0),
            ("15 mm", 15.0),
        ]
        for label_text, pos_val in presets:
            btn_p = QPushButton(label_text)
            btn_p.setFixedHeight(22)
            btn_p.setCursor(Qt.PointingHandCursor)
            btn_p.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    font-size: 10px;
                    padding: 1px 4px;
                }}
                QPushButton:hover {{
                    border-color: {COLORS['accent']};
                    color: {COLORS['accent']};
                }}
            """)
            btn_p.clicked.connect(lambda checked=False, p=pos_val: self._set_preset_position(p))
            row_presets.addWidget(btn_p)

        row_presets.addStretch()
        layout.addLayout(row_presets)

        # Row 4: Smooth Slider (-25.0 to +35.0 mm)
        self.slider_stepper_pos = QSlider(Qt.Horizontal)
        self.slider_stepper_pos.setRange(-250, 350)  # -25.0 to +35.0 mm in 0.1 mm units
        self.slider_stepper_pos.setValue(0)
        self.slider_stepper_pos.setStyleSheet(self._slider_style())
        self.slider_stepper_pos.valueChanged.connect(self._on_pos_slider_changed)
        layout.addWidget(self.slider_stepper_pos)

        return grp

    def _build_load_panel(self):
        """Command target resistance & shaft torque (RES <lbs>, ARM <in>, TORQ <lbf·in>) with instant LUT preview."""
        grp = QGroupBox("2. Command Target Load & Shaft Torque (Brake Resistance)")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        # Row 1: Forearm Pin selection + Target Load + Target Torque + Apply button
        row_load = QHBoxLayout()
        row_load.setSpacing(6)

        lbl_arm = QLabel("Forearm:")
        lbl_arm.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: bold;")
        row_load.addWidget(lbl_arm)

        self.combo_forearm = QComboBox()
        self.combo_forearm.setFixedHeight(26)
        self.combo_forearm.setCursor(Qt.PointingHandCursor)
        self.combo_forearm.setStyleSheet(self._input_style())
        forearm_pins = [
            ("Pin 1: 9\" (22.9 cm)", 9.0),
            ("Pin 2: 10\" (25.4 cm)", 10.0),
            ("Pin 3: 11\" (27.9 cm)", 11.0),
            ("Pin 4: 12\" (30.5 cm)", 12.0),
            ("Pin 5: 13\" (33.0 cm)", 13.0),
        ]
        for label, length_in in forearm_pins:
            self.combo_forearm.addItem(label, length_in)
        self.combo_forearm.setCurrentIndex(3)  # Default Pin 4: 12 inches
        self.combo_forearm.currentIndexChanged.connect(self._on_forearm_changed)
        row_load.addWidget(self.combo_forearm)

        row_load.addSpacing(6)

        lbl_tl = QLabel("Target Load:")
        lbl_tl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: bold;")
        row_load.addWidget(lbl_tl)

        self.spin_cmd_load = QDoubleSpinBox()
        self.spin_cmd_load.setFixedWidth(78)
        self.spin_cmd_load.setRange(0.0, 25.0)
        self.spin_cmd_load.setSingleStep(0.5)
        self.spin_cmd_load.setDecimals(1)
        self.spin_cmd_load.setSuffix(" lbs")
        self.spin_cmd_load.setValue(10.0)
        self.spin_cmd_load.setStyleSheet(self._input_style())
        self.spin_cmd_load.valueChanged.connect(self._on_cmd_load_changed)
        row_load.addWidget(self.spin_cmd_load)

        self.btn_send_load = QPushButton("Apply Load (RES)")
        self.btn_send_load.setFixedHeight(28)
        self.btn_send_load.setCursor(Qt.PointingHandCursor)
        self.btn_send_load.setStyleSheet(self._primary_btn_style())
        self.btn_send_load.clicked.connect(self._command_load_resistance)
        row_load.addWidget(self.btn_send_load)

        row_load.addStretch()
        layout.addLayout(row_load)

        # Row 2: Torque readout + LUT Feedforward displacement preview
        row_torque_prev = QHBoxLayout()
        row_torque_prev.setSpacing(12)

        self.lbl_target_torque = QLabel("Target Torque: 120.0 lbf·in")
        self.lbl_target_torque.setStyleSheet(f"color: {COLORS['warning']}; font-size: 11px; font-weight: bold;")
        row_torque_prev.addWidget(self.lbl_target_torque)

        self.lbl_lut_feedforward = QLabel("LUT Displacement: ~10.2 mm")
        self.lbl_lut_feedforward.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 11px; font-weight: bold;")
        row_torque_prev.addWidget(self.lbl_lut_feedforward)

        row_torque_prev.addStretch()
        layout.addLayout(row_torque_prev)

        # Row 3: Quick preset buttons for target load
        row_presets = QHBoxLayout()
        row_presets.setSpacing(4)
        lbl_p = QLabel("Load Presets:")
        lbl_p.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: bold;")
        row_presets.addWidget(lbl_p)

        load_presets = [0.0, 2.5, 5.0, 10.0, 15.0, 20.0, 25.0]
        for lp in load_presets:
            btn_lp = QPushButton(f"{lp:.1f} lbs" if lp > 0 else "0 lbs (Release)")
            btn_lp.setFixedHeight(22)
            btn_lp.setCursor(Qt.PointingHandCursor)
            btn_lp.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    font-size: 10px;
                    padding: 1px 4px;
                }}
                QPushButton:hover {{
                    border-color: {COLORS['accent']};
                    color: {COLORS['accent']};
                }}
            """)
            btn_lp.clicked.connect(lambda checked=False, val=lp: self._set_preset_load(val))
            row_presets.addWidget(btn_lp)

        row_presets.addStretch()
        layout.addLayout(row_presets)

        return grp

    def _build_homing_panel(self):
        """Homing controls, sensitivity threshold, direction polarity, and descent safety."""
        grp = QGroupBox("3. Homing, Driver Settings && Descent Safety")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        # Row 1: Home Button + Emergency Stop
        row_actions = QHBoxLayout()
        row_actions.setSpacing(8)

        self.btn_home = QPushButton("⟲ Home Stepper (PB13 Switch)")
        self.btn_home.setFixedHeight(30)
        self.btn_home.setCursor(Qt.PointingHandCursor)
        self.btn_home.setStyleSheet(self._primary_btn_style())
        self.btn_home.clicked.connect(self._home_stepper)
        row_actions.addWidget(self.btn_home, stretch=1)

        self.btn_estop = QPushButton("🛑 EMERGENCY STOP")
        self.btn_estop.setFixedHeight(30)
        self.btn_estop.setCursor(Qt.PointingHandCursor)
        self.btn_estop.setStyleSheet(f"""
            QPushButton {{
                background-color: #8b0000;
                color: white;
                border: 2px solid {COLORS['danger']};
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 8px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
            }}
        """)
        self.btn_estop.clicked.connect(self._emergency_stop_clicked)
        row_actions.addWidget(self.btn_estop, stretch=1)

        layout.addLayout(row_actions)

        # Row 2: Motor Direction Polarity + Invert Button
        row_dir = QHBoxLayout()
        row_dir.setSpacing(8)

        self.btn_toggle_dir = QPushButton("⇄ Invert Motor DIR")
        self.btn_toggle_dir.setFixedHeight(26)
        self.btn_toggle_dir.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_dir.setStyleSheet(self._secondary_btn_style(COLORS['accent_cyan']))
        self.btn_toggle_dir.clicked.connect(self._toggle_motor_dir)
        row_dir.addWidget(self.btn_toggle_dir)

        self.lbl_dir_status = QLabel("DIR: Standard (+mm Tightens)")
        self.lbl_dir_status.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; font-size: 11px;")
        row_dir.addWidget(self.lbl_dir_status)

        row_dir.addStretch()
        layout.addLayout(row_dir)

        # Row 3: Homing Current
        row_curr = QHBoxLayout()
        row_curr.setSpacing(8)
        lbl_cur = QLabel("Current:")
        lbl_cur.setFixedWidth(80)
        lbl_cur.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_curr.addWidget(lbl_cur)
        self.spin_homing_curr = QDoubleSpinBox()
        self.spin_homing_curr.setFixedWidth(80)
        self.spin_homing_curr.setRange(300, 1800)
        self.spin_homing_curr.setValue(800)
        self.spin_homing_curr.setSingleStep(50)
        self.spin_homing_curr.setDecimals(0)
        self.spin_homing_curr.setSuffix(" mA")
        self.spin_homing_curr.setStyleSheet(self._input_style())
        row_curr.addWidget(self.spin_homing_curr)

        btn_apply_curr = QPushButton("Set")
        btn_apply_curr.setFixedHeight(24)
        btn_apply_curr.setFixedWidth(36)
        btn_apply_curr.setCursor(Qt.PointingHandCursor)
        btn_apply_curr.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_apply_curr.clicked.connect(lambda: self._send_raw_command(f"HOMECURR {int(self.spin_homing_curr.value())}"))
        row_curr.addWidget(btn_apply_curr)
        row_curr.addStretch()
        layout.addLayout(row_curr)

        # Row 4: Homing Speed
        row_spd = QHBoxLayout()
        row_spd.setSpacing(8)
        lbl_spd = QLabel("Speed:")
        lbl_spd.setFixedWidth(80)
        lbl_spd.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_spd.addWidget(lbl_spd)
        self.spin_homing_speed = QDoubleSpinBox()
        self.spin_homing_speed.setFixedWidth(80)
        self.spin_homing_speed.setRange(100, 3000)
        self.spin_homing_speed.setValue(350)
        self.spin_homing_speed.setSingleStep(50)
        self.spin_homing_speed.setDecimals(0)
        self.spin_homing_speed.setSuffix(" us")
        self.spin_homing_speed.setStyleSheet(self._input_style())
        row_spd.addWidget(self.spin_homing_speed)

        btn_apply_spd = QPushButton("Set")
        btn_apply_spd.setFixedHeight(24)
        btn_apply_spd.setFixedWidth(36)
        btn_apply_spd.setCursor(Qt.PointingHandCursor)
        btn_apply_spd.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_apply_spd.clicked.connect(lambda: self._send_raw_command(f"HOMESPEED {int(self.spin_homing_speed.value())}"))
        row_spd.addWidget(btn_apply_spd)
        row_spd.addStretch()
        layout.addLayout(row_spd)

        # Row 5: Homing Standoff Slack (Backoff mm off limit switch)
        row_slack = QHBoxLayout()
        row_slack.setSpacing(8)
        lbl_slk = QLabel("Backoff Slack:")
        lbl_slk.setFixedWidth(80)
        lbl_slk.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_slack.addWidget(lbl_slk)
        self.spin_homing_slack = QDoubleSpinBox()
        self.spin_homing_slack.setFixedWidth(80)
        self.spin_homing_slack.setRange(0.0, 50.0)
        self.spin_homing_slack.setValue(30.0)
        self.spin_homing_slack.setSingleStep(0.5)
        self.spin_homing_slack.setDecimals(1)
        self.spin_homing_slack.setSuffix(" mm")
        self.spin_homing_slack.setStyleSheet(self._input_style())
        row_slack.addWidget(self.spin_homing_slack)

        btn_apply_slk = QPushButton("Set")
        btn_apply_slk.setFixedHeight(24)
        btn_apply_slk.setFixedWidth(36)
        btn_apply_slk.setCursor(Qt.PointingHandCursor)
        btn_apply_slk.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_apply_slk.clicked.connect(lambda: self._send_raw_command(f"HOMESLACK {self.spin_homing_slack.value():.1f}"))
        row_slack.addWidget(btn_apply_slk)

        lbl_slk_hint = QLabel("(Off PB13)")
        lbl_slk_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        row_slack.addWidget(lbl_slk_hint)
        row_slack.addStretch()
        layout.addLayout(row_slack)

        # Row 6: Descent Drop Arrest Safety Control
        row_safety = QHBoxLayout()
        row_safety.setSpacing(8)
        lbl_ar = QLabel("Drop Arrest:")
        lbl_ar.setFixedWidth(80)
        lbl_ar.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_safety.addWidget(lbl_ar)

        self.spin_arrest_thresh = QDoubleSpinBox()
        self.spin_arrest_thresh.setFixedWidth(80)
        self.spin_arrest_thresh.setRange(-400.0, -50.0)
        self.spin_arrest_thresh.setValue(-160.0)
        self.spin_arrest_thresh.setSingleStep(10.0)
        self.spin_arrest_thresh.setDecimals(0)
        self.spin_arrest_thresh.setSuffix(" °/s")
        self.spin_arrest_thresh.setStyleSheet(self._input_style())
        row_safety.addWidget(self.spin_arrest_thresh)

        btn_set_arrest = QPushButton("Set")
        btn_set_arrest.setFixedHeight(24)
        btn_set_arrest.setFixedWidth(36)
        btn_set_arrest.setCursor(Qt.PointingHandCursor)
        btn_set_arrest.setStyleSheet(self._secondary_btn_style(COLORS['accent']))
        btn_set_arrest.clicked.connect(lambda: self._send_raw_command(f"ARRESTTHR {int(self.spin_arrest_thresh.value())}"))
        row_safety.addWidget(btn_set_arrest)

        row_safety.addStretch()
        layout.addLayout(row_safety)

        # Row 5: Realtime homing status
        self.lbl_homing_status = QLabel("Last Homing: Standby (Click 'Home Stepper' to calibrate 0.0 mm reference)")
        self.lbl_homing_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        layout.addWidget(self.lbl_homing_status)

        return grp

    def _build_lut_panel(self):
        """Single-curl torque point capture workflow, live peak tracking, and LUT table."""
        grp = QGroupBox("4. Single-Curl Torque LUT Calibration (Point Capture)")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)

        # Row 1: Live Sensors (Instantaneous Force, Angle, Latched Peak)
        row_sensors = QHBoxLayout()
        row_sensors.setSpacing(8)

        lbl_f_title = QLabel("Live Force:")
        lbl_f_title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_sensors.addWidget(lbl_f_title)

        self.lbl_live_force = QLabel("0.0 lbs")
        self.lbl_live_force.setStyleSheet(f"color: {COLORS['graph_strength']}; font-size: 13px; font-weight: bold;")
        row_sensors.addWidget(self.lbl_live_force)

        row_sensors.addSpacing(6)

        lbl_t_title = QLabel("Shaft Torque:")
        lbl_t_title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_sensors.addWidget(lbl_t_title)

        self.lbl_live_torque = QLabel("0.0 lbf·in")
        self.lbl_live_torque.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 13px; font-weight: bold;")
        row_sensors.addWidget(self.lbl_live_torque)

        row_sensors.addSpacing(6)

        lbl_pk_title = QLabel("Peak Torque:")
        lbl_pk_title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        row_sensors.addWidget(lbl_pk_title)

        self.lbl_peak_torque = QLabel("0.0 lbf·in")
        self.lbl_peak_torque.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px; font-weight: bold;")
        row_sensors.addWidget(self.lbl_peak_torque)

        btn_reset_pk = QPushButton("Reset Peak")
        btn_reset_pk.setFixedHeight(22)
        btn_reset_pk.setCursor(Qt.PointingHandCursor)
        btn_reset_pk.setStyleSheet(self._secondary_btn_style(COLORS['text_muted']))
        btn_reset_pk.clicked.connect(self._reset_curl_peak)
        row_sensors.addWidget(btn_reset_pk)

        row_sensors.addStretch()
        layout.addLayout(row_sensors)

        # Row 2: Auto-latch peak checkbox + Capture Point Button
        row_cap = QHBoxLayout()
        row_cap.setSpacing(8)

        self.chk_auto_peak = QCheckBox("Auto-Latch Peak Torque")
        self.chk_auto_peak.setChecked(True)
        self.chk_auto_peak.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 11px;")
        row_cap.addWidget(self.chk_auto_peak)

        self.btn_capture_pt = QPushButton("📍 Capture Point (Curr Pos -> Peak Torque)")
        self.btn_capture_pt.setFixedHeight(28)
        self.btn_capture_pt.setCursor(Qt.PointingHandCursor)
        self.btn_capture_pt.setStyleSheet(self._primary_btn_style())
        self.btn_capture_pt.clicked.connect(self._capture_current_point)
        row_cap.addWidget(self.btn_capture_pt, stretch=1)

        layout.addLayout(row_cap)

        # Row 3: Table of Captured Points (Pos, Force, Torque, Action)
        self.table_lut = QTableWidget()
        self.table_lut.setColumnCount(4)
        self.table_lut.setHorizontalHeaderLabels(["Pos (mm)", "Force (lbs)", "Torque (lbf·in)", "Action"])
        self.table_lut.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_lut.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_lut.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_lut.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_lut.setFixedHeight(105)
        self.table_lut.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                gridline-color: {COLORS['border']};
                font-size: 11px;
                color: {COLORS['text_primary']};
            }}
            QHeaderView::section {{
                background-color: {COLORS['bg_input']};
                color: {COLORS['text_secondary']};
                font-weight: bold;
                border: none;
                padding: 3px;
                font-size: 10px;
            }}
        """)
        layout.addWidget(self.table_lut)

        # Row 4: Action Buttons (Fit & Export LUT, Clear Points, Rebuild FW)
        row_lut_acts = QHBoxLayout()
        row_lut_acts.setSpacing(6)

        self.btn_fit_lut = QPushButton("⚡ Fit && Export LUT to Firmware")
        self.btn_fit_lut.setFixedHeight(28)
        self.btn_fit_lut.setCursor(Qt.PointingHandCursor)
        self.btn_fit_lut.setStyleSheet(self._primary_btn_style())
        self.btn_fit_lut.clicked.connect(self._fit_and_export_lut)
        row_lut_acts.addWidget(self.btn_fit_lut, stretch=2)

        self.btn_clear_pts = QPushButton("Clear Points")
        self.btn_clear_pts.setFixedHeight(28)
        self.btn_clear_pts.setCursor(Qt.PointingHandCursor)
        self.btn_clear_pts.setStyleSheet(self._secondary_btn_style(COLORS['danger']))
        self.btn_clear_pts.clicked.connect(self._clear_captured_points)
        row_lut_acts.addWidget(self.btn_clear_pts, stretch=1)

        self.btn_rebuild_fw = QPushButton("Rebuild FW (pio)")
        self.btn_rebuild_fw.setFixedHeight(28)
        self.btn_rebuild_fw.setCursor(Qt.PointingHandCursor)
        self.btn_rebuild_fw.setStyleSheet(self._secondary_btn_style(COLORS['info']))
        self.btn_rebuild_fw.clicked.connect(self._rebuild_firmware)
        row_lut_acts.addWidget(self.btn_rebuild_fw, stretch=1)

        layout.addLayout(row_lut_acts)

        return grp

    # ─────────────────────────────────────────────────────────
    # Sub-Panels: Right Column
    # ─────────────────────────────────────────────────────────
    def _build_plot_panel(self):
        """PyQtGraph visualization of calibrated Torque LUT curve with live carriage cursor."""
        grp = QGroupBox("Torque Calibration Curve: Commanded Position vs. Shaft Braking Torque")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        pg.setConfigOption("background", COLORS["bg_card"])
        pg.setConfigOption("foreground", COLORS["text_secondary"])

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setLabel("left", "Shaft Braking Torque (lbf·in)", color=COLORS["text_secondary"])
        self.plot_widget.setLabel("bottom", "Stepper Carriage Position (mm)", color=COLORS["text_secondary"])
        self.plot_widget.setXRange(-10, 25)
        self.plot_widget.setYRange(0, 350)

        # Model curve item (fitted polynomial / exponential)
        pen_curve = pg.mkPen(color=COLORS["accent_cyan"], width=2)
        self.curve_model = self.plot_widget.plot([], [], pen=pen_curve, name="Torque LUT Model")

        # Measured calibration points item
        self.scatter_points = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen(COLORS["warning"], width=1.5),
            brush=pg.mkBrush(COLORS["warning"]),
            symbol="o"
        )
        self.plot_widget.addItem(self.scatter_points)

        # Realtime carriage position cursor (vertical cyan line)
        pen_cursor = pg.mkPen(color=COLORS["accent"], width=1.5, style=Qt.DashLine)
        self.line_curr_pos = pg.InfiniteLine(pos=0.0, angle=90, pen=pen_cursor, movable=False)
        self.plot_widget.addItem(self.line_curr_pos)

        layout.addWidget(self.plot_widget)

        # Readout bar under plot: System gain and Sensitivity
        row_gain = QHBoxLayout()
        row_gain.setSpacing(12)

        self.lbl_system_gain = QLabel("System Gain (K_tau): -- lbf·in/mm")
        self.lbl_system_gain.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; font-size: 11px;")
        row_gain.addWidget(self.lbl_system_gain)

        self.lbl_sensitivity = QLabel("Sensitivity: -- mm/(lbf·in)")
        self.lbl_sensitivity.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-weight: bold; font-size: 11px;")
        row_gain.addWidget(self.lbl_sensitivity)

        lbl_kin = QLabel("Transmission Ratio: ~30:1 (5:1 lever x 6:1 hyd)")
        lbl_kin.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        row_gain.addWidget(lbl_kin)

        row_gain.addStretch()
        layout.addLayout(row_gain)

        # Render nominal curve initially
        self._update_plot_curve()

        return grp

    def _build_stripchart_panel(self):
        """Real-time scrolling stripchart of live curl exertion force vs time."""
        grp = QGroupBox("Real-Time Curl Force Monitor (Live Exertion)")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        self.plot_strip = pg.PlotWidget()
        self.plot_strip.showGrid(x=True, y=True, alpha=0.15)
        self.plot_strip.setLabel("left", "Curl Force (lbs)", color=COLORS["graph_strength"])
        self.plot_strip.setLabel("bottom", "Time (s)", color=COLORS["text_muted"])
        self.plot_strip.setXRange(0, 3.0, padding=0)
        self.plot_strip.setYRange(0, 25.0, padding=0)
        self.plot_strip.setFixedHeight(125)

        pen_force = pg.mkPen(color=COLORS["graph_strength"], width=2.0)
        self.curve_strip_force = self.plot_strip.plot([], [], pen=pen_force)

        # Real-time peak marker line
        pen_peak = pg.mkPen(color=COLORS["warning"], width=1.5, style=Qt.DashLine)
        self.line_strip_peak = pg.InfiniteLine(pos=0.0, angle=0, pen=pen_peak, movable=False)
        self.plot_strip.addItem(self.line_strip_peak)

        layout.addWidget(self.plot_strip)
        return grp

    def _build_terminal_panel(self):
        """Serial command terminal and live hardware activity monitor."""
        grp = QGroupBox("Serial Terminal (VCP / USB CDC)")
        grp.setStyleSheet(self._group_box_style())
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(4)

        self.txt_terminal = QTextEdit()
        self.txt_terminal.setReadOnly(True)
        self.txt_terminal.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-family: monospace;
                font-size: 10px;
            }}
        """)
        layout.addWidget(self.txt_terminal)

        row_in = QHBoxLayout()
        row_in.setSpacing(5)

        self.input_cmd = QLineEdit()
        self.input_cmd.setPlaceholderText("Enter command (e.g. POS 5.0, RES 10, TORQ 120, ARM 12, HOME)...")
        self.input_cmd.setStyleSheet(self._input_style())
        self.input_cmd.returnPressed.connect(self._on_cmd_enter)
        row_in.addWidget(self.input_cmd, stretch=1)

        btn_send = QPushButton("Send")
        btn_send.setFixedHeight(26)
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.setStyleSheet(self._primary_btn_style())
        btn_send.clicked.connect(self._on_cmd_enter)
        row_in.addWidget(btn_send)

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(26)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(self._secondary_btn_style(COLORS['text_muted']))
        btn_clear.clicked.connect(self.txt_terminal.clear)
        row_in.addWidget(btn_clear)

        layout.addLayout(row_in)
        return grp

    # ─────────────────────────────────────────────────────────
    # Stepper Control Logic
    # ─────────────────────────────────────────────────────────
    def _command_stepper_pos(self):
        target_pos = self.spin_stepper_pos.value()
        self.commanded_pos_mm = target_pos
        self.peak_curl_force = 0.0
        self.peak_curl_torque = 0.0

        cmd_str = f"POS {target_pos:.2f}"
        self._send_raw_command(cmd_str)
        self._log_terminal(f"Commanded Stepper: POS {target_pos:.2f} mm")

    def _zero_motor_pos(self):
        """Zero the physical stepper carriage tracking reference in firmware and GUI without homing."""
        self._send_raw_command("ZEROPOS")
        self.spin_stepper_pos.setValue(0.0)
        self.slider_stepper_pos.setValue(0)
        self.lbl_curr_pos.setText("0.0 mm")
        self.lbl_hud_pos_val.setText("0.0 mm")
        self.line_curr_pos.setValue(0.0)
        self._log_terminal("Sent ZEROPOS: Reset carriage step counter and position to 0.0 mm")

    def _jog_stepper(self, delta_mm: float):
        cur = self.spin_stepper_pos.value()
        new_val = round(max(-25.0, min(35.0, cur + delta_mm)), 2)
        self.spin_stepper_pos.setValue(new_val)
        self._command_stepper_pos()

    def _set_preset_position(self, pos_mm: float):
        self.spin_stepper_pos.setValue(pos_mm)
        self._command_stepper_pos()

    def _on_pos_spin_changed(self, val):
        self.slider_stepper_pos.blockSignals(True)
        self.slider_stepper_pos.setValue(int(val * 10))
        self.slider_stepper_pos.blockSignals(False)

    def _on_pos_slider_changed(self, val):
        pos_mm = val / 10.0
        self.spin_stepper_pos.blockSignals(True)
        self.spin_stepper_pos.setValue(pos_mm)
        self.spin_stepper_pos.blockSignals(False)

    # ─────────────────────────────────────────────────────────
    # Target Resistance & Torque Control Logic
    # ─────────────────────────────────────────────────────────
    def _on_forearm_changed(self, idx):
        self.forearm_length_in = float(self.combo_forearm.currentData() or 12.0)
        self._send_raw_command(f"ARM {self.forearm_length_in:.1f}")
        self._update_torque_and_displacement_preview()

    def _set_preset_load(self, val: float):
        self.spin_cmd_load.setValue(val)
        self._command_load_resistance()

    def _on_cmd_load_changed(self, val: float):
        self._update_torque_and_displacement_preview()

    def _update_torque_and_displacement_preview(self):
        val = self.spin_cmd_load.value()
        torque = val * self.forearm_length_in
        self.commanded_torque_lbf_in = torque
        self.lbl_target_torque.setText(f"Target Torque: {torque:.1f} lbf·in")

        est_pos = 0.0
        if torque > 0:
            est_pos = 8.586 + (torque / 72.39)
        self.lbl_lut_feedforward.setText(f"LUT Displacement: ~{est_pos:.1f} mm")

    def _command_load_resistance(self):
        val = self.spin_cmd_load.value()
        torque = val * self.forearm_length_in
        self._update_torque_and_displacement_preview()

        # Transmit forearm length first, then commanded resistance
        self._send_raw_command(f"ARM {self.forearm_length_in:.1f}")
        self._send_raw_command(f"RES {val:.1f}")
        if self.hw and self.hw.is_connected:
            self.hw.set_resistance(val)
        self._log_terminal(f"Commanded Load: {val:.1f} lbs @ {self.forearm_length_in:.0f}\" (Torque: {torque:.1f} lbf·in)")

    # ─────────────────────────────────────────────────────────
    # Homing & Driver Control Logic
    # ─────────────────────────────────────────────────────────
    def _emergency_stop_clicked(self):
        self._send_raw_command("STOP")
        if self.hw and self.hw.is_connected:
            self.hw.send_command("STOP")
            self.hw.is_streaming = False
        self._log_terminal("🛑 EMERGENCY STOP: Sent STOP to STM32. Motor driver disabled immediately.")

    def _toggle_motor_dir(self):
        self._send_raw_command("INVERT")

    def _home_stepper(self):
        slack = self.spin_homing_slack.value()
        self._send_raw_command(f"HOMESLACK {slack:.1f}")
        self._send_raw_command("HOME")
        self.spin_stepper_pos.setValue(0.0)
        self.slider_stepper_pos.setValue(0)
        self.lbl_homing_status.setText(f"Last Homing: Searching PB13 switch (Slack backoff: {slack:.1f} mm)...")
        self.lbl_homing_status.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold; font-size: 11px;")
        self._log_terminal(f"Commanded Carriage HOME (Searching PB13, Backoff Slack: {slack:.1f} mm)")

    # ─────────────────────────────────────────────────────────
    # Single-Curl Torque Calibration Workflow
    # ─────────────────────────────────────────────────────────
    def _reset_curl_peak(self):
        self.peak_curl_force = 0.0
        self.peak_curl_torque = 0.0
        self.lbl_peak_force.setText("0.0 lbs")
        self.lbl_peak_torque.setText("0.0 lbf·in")
        self.line_strip_peak.setValue(0.0)
        self._log_terminal("Reset peak curl force & torque latch to 0.0.")

    def _capture_current_point(self):
        pos = round(self.live_carriage_mm, 2)
        force = round(self.peak_curl_force if self.chk_auto_peak.isChecked() else self.live_force, 2)
        torque = round(force * self.forearm_length_in, 2)

        # Replace existing point at exact position if already present
        self.captured_lut_points = [p for p in self.captured_lut_points if abs(p[0] - pos) > 0.05]
        self.captured_lut_points.append((pos, force, torque))
        self.captured_lut_points.sort(key=lambda x: x[0])

        self._refresh_lut_table()
        self._update_plot_curve()
        self._log_terminal(f"Captured Point: Pos={pos:.2f} mm -> Force={force:.2f} lbs -> Torque={torque:.1f} lbf·in")

    def _refresh_lut_table(self):
        self.table_lut.setRowCount(len(self.captured_lut_points))
        for row, (pos, force, torque) in enumerate(self.captured_lut_points):
            item_pos = QTableWidgetItem(f"{pos:.2f}")
            item_pos.setTextAlignment(Qt.AlignCenter)
            self.table_lut.setItem(row, 0, item_pos)

            item_force = QTableWidgetItem(f"{force:.2f}")
            item_force.setTextAlignment(Qt.AlignCenter)
            self.table_lut.setItem(row, 1, item_force)

            item_torque = QTableWidgetItem(f"{torque:.1f}")
            item_torque.setTextAlignment(Qt.AlignCenter)
            self.table_lut.setItem(row, 2, item_torque)

            btn_del = QPushButton("Delete")
            btn_del.setFixedHeight(22)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet(self._secondary_btn_style(COLORS['danger']))
            btn_del.clicked.connect(lambda checked=False, r=row: self._delete_lut_point(r))
            self.table_lut.setCellWidget(row, 3, btn_del)

    def _delete_lut_point(self, row_idx):
        if 0 <= row_idx < len(self.captured_lut_points):
            del self.captured_lut_points[row_idx]
            self._refresh_lut_table()
            self._update_plot_curve()
            self._log_terminal(f"Deleted calibration point at row {row_idx + 1}")

    def _clear_captured_points(self):
        self.captured_lut_points.clear()
        self._refresh_lut_table()
        self._update_plot_curve()
        self._log_terminal("Cleared all captured LUT calibration points.")

    def _update_plot_curve(self):
        pts = self.captured_lut_points
        xs = np.linspace(-10.0, 25.0, 150)

        if len(pts) >= 2:
            p_arr = np.array([p[0] for p in pts])
            tau_arr = np.array([p[2] for p in pts])

            self.scatter_points.setData(p_arr, tau_arr)

            # Fit cubic polynomial with monotonicity enforcement
            try:
                poly = np.polyfit(p_arr, tau_arr, min(3, len(pts) - 1))
                ys = np.polyval(poly, xs)
                ys = np.maximum(0.0, ys)

                # Estimate stiffness / system gain in lbf·in/mm above 6 mm
                mask = (p_arr >= 6.0)
                if np.sum(mask) >= 2:
                    slope, _ = np.polyfit(p_arr[mask], tau_arr[mask], 1)
                    k_sys = max(1.0, slope)
                else:
                    k_sys = max(1.0, (tau_arr[-1] - tau_arr[0]) / max(1.0, (p_arr[-1] - p_arr[0])))

                self.lbl_system_gain.setText(f"System Gain (K_tau): {k_sys:.1f} lbf·in/mm")
                self.lbl_sensitivity.setText(f"Sensitivity: {1.0 / k_sys:.3f} mm/(lbf·in)")
            except Exception:
                ys = np.zeros_like(xs)
        else:
            self.scatter_points.setData([], [])
            # Nominal torque model: 0 below 6 mm, ramps up to 300 lbf·in at 13 mm
            ys = np.zeros_like(xs)
            mask = xs > 6.0
            ys[mask] = 30.0 * (xs[mask] - 6.0) ** 1.3
            ys = np.clip(ys, 0.0, 325.0)

            k_plant = 72.39
            self.lbl_system_gain.setText(f"System Gain (K_tau): {k_plant:.1f} lbf·in/mm (Nominal)")
            self.lbl_sensitivity.setText(f"Sensitivity: {1.0 / k_plant:.3f} mm/(lbf·in) (Nominal)")

        self.curve_model.setData(xs, ys)

    def _fit_and_export_lut(self):
        """Fit captured torque points, format C array, and write to brake_lut.h."""
        if len(self.captured_lut_points) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Points",
                "Please capture at least 2 calibration points across carriage displacement."
            )
            return

        pts = sorted(self.captured_lut_points, key=lambda x: x[0])
        p_arr = np.array([p[0] for p in pts])
        tau_arr = np.array([p[2] for p in pts])

        # Generate 66-point LUT for target torque [0.0, 325.0 lbf*in in 5.0 steps]
        lut_torques = np.linspace(0.0, 325.0, 66)
        try:
            # Anchor 0 torque to 0.0 mm
            tau_anchor = np.concatenate(([0.0], tau_arr))
            pos_anchor = np.concatenate(([0.0], p_arr))
            fitted_pos = np.interp(lut_torques, tau_anchor, pos_anchor)
        except Exception as e:
            QMessageBox.critical(self, "Fitting Error", f"Interpolation failed: {e}")
            return

        c_lines = []
        for i in range(0, len(fitted_pos), 6):
            chunk = fitted_pos[i:i+6]
            c_lines.append("    " + ", ".join(f"{v:6.3f}f" for v in chunk) + ",")
        c_code = "\n".join(c_lines)

        lut_file_path = os.path.join(REPO_ROOT, "firmware", "Core", "Inc", "brake_lut.h")
        try:
            header_content = f"""/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** FlexSense - Calibrated Shaft Torque Kinematics & Look-Up Table (LUT)
** Auto-generated from Dev & Calibration Workstation
*/

#ifndef BRAKE_LUT_H
#define BRAKE_LUT_H

#ifdef __cplusplus
extern "C" {{
#endif

#include <stdint.h>

#define BRAKE_SYSTEM_GAIN_LBF_IN_PER_MM   72.39f
#define BRAKE_SLACK_TAKEUP_MM             2.50f
#define BRAKE_LUT_MIN_TORQUE_LBF_IN       0.0f
#define BRAKE_LUT_MAX_TORQUE_LBF_IN       325.0f
#define BRAKE_LUT_STEP_TORQUE_LBF_IN      5.0f
#define BRAKE_LUT_NUM_ENTRIES             66

static const float s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES] = {{
{c_code}
}};

static inline float Brake_LUT_TorqueToPositionMm(float target_torque_lbf_in)
{{
  if ( target_torque_lbf_in <= 0.0f ) return 0.0f;
  if ( target_torque_lbf_in >= BRAKE_LUT_MAX_TORQUE_LBF_IN ) return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  float idx_float = target_torque_lbf_in / BRAKE_LUT_STEP_TORQUE_LBF_IN;
  int idx = (int)idx_float;
  if ( idx >= (BRAKE_LUT_NUM_ENTRIES - 1) ) return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  float frac = idx_float - (float)idx;
  return s_brake_torque_to_pos_mm[idx] + frac * (s_brake_torque_to_pos_mm[idx + 1] - s_brake_torque_to_pos_mm[idx]);
}}

static inline float Brake_LUT_ForceToPositionMm(float target_force_lbs)
{{
  return Brake_LUT_TorqueToPositionMm(target_force_lbs * 12.0f);
}}

#ifdef __cplusplus
}}
#endif

#endif /* BRAKE_LUT_H */
"""
            with open(lut_file_path, "w") as f:
                f.write(header_content)

            self._log_terminal(f"Exported calibrated Torque LUT (66 entries) to {lut_file_path}")
            QMessageBox.information(
                self,
                "LUT Exported",
                f"Successfully generated calibrated Torque LUT header!\nPath: {lut_file_path}\nClick 'Rebuild FW (pio)' to flash."
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to write header: {e}")

    def _rebuild_firmware(self):
        self._log_terminal("Running PlatformIO build: pio run -d firmware...")
        try:
            res = subprocess.run(
                ["pio", "run", "-d", os.path.join(REPO_ROOT, "firmware")],
                capture_output=True,
                text=True,
                timeout=45
            )
            if res.returncode == 0:
                self._log_terminal("SUCCESS: PlatformIO build succeeded!")
                QMessageBox.information(self, "Build Complete", "PlatformIO firmware build succeeded!")
            else:
                self._log_terminal(f"ERROR: Build failed:\n{res.stderr}")
                QMessageBox.critical(self, "Build Failed", f"PlatformIO build failed:\n{res.stderr[:500]}")
        except Exception as e:
            self._log_terminal(f"ERROR: Failed to run pio: {e}")
            QMessageBox.critical(self, "Execution Error", f"Could not launch PlatformIO: {e}")

    # ─────────────────────────────────────────────────────────
    # Telemetry & Hardware Communication
    # ─────────────────────────────────────────────────────────
    def _setup_telemetry_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(20)  # 50 Hz UI refresh
        self.timer.timeout.connect(self._update_telemetry)
        self.timer.start()

    def _probe_hardware(self):
        if not self.hw.is_connected:
            success, msg = self.hw.connect()
            if success:
                port_name = getattr(self.hw, 'port', None) or "/dev/ttyACM0"
                self._log_terminal(f"Hardware probe: Connected to {port_name}")
                self.hw.start_streaming()
                # Query MCU direction state, TMC status, and sync forearm setting
                self._send_raw_command("DIR?")
                self._send_raw_command("TMC")
                self._send_raw_command(f"ARM {self.forearm_length_in:.1f}")
            else:
                self._log_terminal("Hardware probe: No device found on serial ports.")

    def _update_telemetry(self):
        # Update connection badge
        if self.hw.is_connected:
            port_name = getattr(self.hw, 'port', None) or "/dev/ttyACM0"
            self.lbl_hw_status.setText(f"ONLINE: {port_name}")
            self.lbl_hw_status.setStyleSheet(f"""
                background-color: #0f382a;
                color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            """)
        else:
            self.lbl_hw_status.setText("OFFLINE / SIM")
            self.lbl_hw_status.setStyleSheet(f"""
                background-color: #38280f;
                color: {COLORS['warning']};
                border: 1px solid {COLORS['warning']};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            """)

        # Poll hardware packets
        if self.hw.is_connected:
            samples = self.hw.read_samples()
            if samples:
                last_s = samples[-1]
                self.live_timestamp_ms = int(last_s[0])
                self.live_angle = float(last_s[2])
                self.live_speed = float(last_s[3])
                self.live_force = max(0.0, float(last_s[4]))
                self.live_carriage_mm = float(last_s[5])
                self.live_spo2 = float(last_s[6]) if len(last_s) > 6 else 98.0

            # Process incoming ASCII lines
            if hasattr(self.hw, 'read_text_lines'):
                text_lines = self.hw.read_text_lines()
                for line in text_lines:
                    self._log_terminal(f"RX <- {line}")
                    self._handle_mcu_response(line)

        # Compute live shaft torque from load cell force and current forearm setting
        self.live_torque = self.live_force * self.forearm_length_in
        if self.chk_auto_peak.isChecked() and self.live_torque > self.peak_curl_torque:
            self.peak_curl_torque = self.live_torque
            self.peak_curl_force = self.live_force

        # Update Top Sensor HUD
        self.lbl_hud_angle_val.setText(f"{self.live_angle:.1f}°")
        self.lbl_hud_vel_val.setText(f"{self.live_speed:.1f} °/s")
        self.lbl_hud_force_val.setText(f"{self.live_force:.1f} lbs")
        self.lbl_hud_force_sub.setText(f"{self.live_torque:.1f} lbf·in ({self.forearm_length_in:.0f}\")")
        self.lbl_hud_pos_val.setText(f"{self.live_carriage_mm:.1f} mm")
        if self.live_spo2 > 0:
            self.lbl_hud_spo2_val.setText(f"{self.live_spo2:.0f}%")
        else:
            self.lbl_hud_spo2_val.setText("-- %")

        # Update controls
        self.lbl_curr_pos.setText(f"{self.live_carriage_mm:.1f} mm")
        self.lbl_live_force.setText(f"{self.live_force:.1f} lbs")
        self.lbl_live_torque.setText(f"{self.live_torque:.1f} lbf·in")
        self.lbl_peak_torque.setText(f"{self.peak_curl_torque:.1f} lbf·in")

        # Update live carriage cursor line on plot
        self.line_curr_pos.setValue(self.live_carriage_mm)

        # Update real-time curl force stripchart
        now_t = time.time() - self._strip_start_t
        self._strip_time.append(now_t)
        self._strip_force.append(self.live_force)

        t_list = list(self._strip_time)
        f_list = list(self._strip_force)
        if t_list:
            min_t = max(0.0, t_list[-1] - 3.0)
            max_t = max(3.0, t_list[-1])
            self.plot_strip.setXRange(min_t, max_t, padding=0)
            self.curve_strip_force.setData(t_list, f_list)
            self.line_strip_peak.setValue(self.peak_curl_force)

    def _send_raw_command(self, cmd_str):
        self._log_terminal(f"TX -> {cmd_str}")
        if self.hw and self.hw.is_connected:
            self.hw.send_command(cmd_str)
            if cmd_str == "START":
                self.hw.is_streaming = True
            elif cmd_str == "STOP":
                self.hw.is_streaming = False
        else:
            self._log_terminal(f"[SIMULATION] Mocking response for: {cmd_str}")

    def _handle_mcu_response(self, line: str):
        if "ALERT:DESCENT_ARREST" in line:
            self.lbl_arrest_banner.setVisible(True)
            self.lbl_arrest_banner.setText(f"🛑 DESCENT DROP ARREST ENGAGED: Rapid drop detected! Brake locked forward to halt handle.")
            self._log_terminal(f"⚠️ [SAFETY ALERT] {line.strip()} - Descent drop arrest triggered! Brake locked.")
        elif "ACK:DESCENT_ARREST:RELEASED" in line or "ACK:RESET_ARREST" in line:
            self.lbl_arrest_banner.setVisible(False)
            self._log_terminal("[SAFETY] Descent drop arrest released - normal control restored.")
        elif "ACK:DIR:" in line:
            is_inv = "1" in line
            self.lbl_dir_status.setText(f"DIR: {'Standard (+mm Tightens)' if is_inv else 'Inverted (-mm Tightens)'}")
            self.lbl_dir_status.setStyleSheet(f"color: {COLORS['accent'] if is_inv else COLORS['warning']}; font-weight: bold; font-size: 11px;")
        elif "ACK:HOME:" in line:
            diag = line[9:]
            is_ok = ("SUCCESS" in diag) or ("OK" in diag and "TIMEOUT" not in diag and "FAILED" not in diag)
            self.lbl_homing_status.setText(f"Last Homing: {'SUCCESS' if is_ok else 'FAILED'} {diag}")
            self.lbl_homing_status.setStyleSheet(f"color: {COLORS['accent'] if is_ok else COLORS['danger']}; font-weight: bold; font-size: 11px;")
        elif "ACK:HOMETHR:" in line:
            self._log_terminal(f"[TMC2209] StallGuard Threshold set to {line[12:]}")
        elif "ACK:HOMECURR:" in line:
            self._log_terminal(f"[TMC2209] Homing Current set to {line[13:]} mA")
        elif "ACK:HOMESPEED:" in line:
            self._log_terminal(f"[TMC2209] Homing Speed set to {line[14:]} us")
        elif "ACK:HOMESLACK:" in line:
            self._log_terminal(f"[MCU] Homing Standoff Slack set to {line[14:].strip()} mm")
        elif "ACK:POS:" in line:
            self._log_terminal(f"[MCU] Position acknowledged: {line[8:]} mm")
        elif "ACK:ZEROPOS" in line:
            self._log_terminal("[MCU] Carriage Motor Position zeroed to 0.0 mm")
            self.lbl_curr_pos.setText("0.0 mm")
            self.lbl_hud_pos_val.setText("0.0 mm")
        elif "ACK:RES:" in line:
            self._log_terminal(f"[MCU] Target Load Acknowledged: {line[8:].strip()} lbs")
        elif "ACK:TORQUE:" in line:
            self._log_terminal(f"[MCU] Target Torque Acknowledged: {line[11:].strip()} lbf·in")
        elif "ACK:ARM:" in line:
            self._log_terminal(f"[MCU] Forearm Lever Setting Acknowledged: {line[8:].strip()} inches")
        elif "ACK:ARRESTTHR:" in line:
            self._log_terminal(f"[MCU] Descent Drop Threshold set to {line[14:].strip()} deg/s")
        elif "ACK:STOP" in line:
            self.lbl_homing_status.setText("● EMERGENCY STOPPED")
            self.lbl_homing_status.setStyleSheet(f"color: {COLORS['danger']}; font-weight: bold; font-size: 11px;")
        elif "ACK:TMC:" in line:
            self._log_terminal(f"[TMC2209 Status] {line[8:]}")
            if "ONLINE=1" in line:
                sg_val = "---"
                if "SG=" in line:
                    try:
                        sg_val = line.split("SG=")[1].split(",")[0]
                    except Exception:
                        pass
                self.lbl_hud_tmc_val.setText(f"ONLINE (SG: {sg_val})")
                self.lbl_hud_tmc_val.setStyleSheet(f"color: {COLORS['accent']}; font-size: 13px; font-weight: bold; border: none;")
                self.lbl_hud_tmc_sub.setText("UART 115.2k | StealthChop")
            else:
                self.lbl_hud_tmc_val.setText("OFFLINE")
                self.lbl_hud_tmc_val.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px; font-weight: bold; border: none;")
                self.lbl_hud_tmc_sub.setText("Check 12V/24V Motor Bus")
        elif "ACK:STATUS:" in line:
            self._log_terminal(f"[NAU7802 Health] {line[11:]}")
        elif "ACK:SPO2:" in line:
            self._log_terminal(f"[MAX30102 Diagnostic] {line[9:]}")

    def _on_cmd_enter(self):
        cmd_text = self.input_cmd.text().strip()
        if cmd_text:
            self._send_raw_command(cmd_text)
            self.input_cmd.clear()

    def _log_terminal(self, msg):
        timestamp = time.strftime("[%H:%M:%S] ")
        self.txt_terminal.append(timestamp + msg)
        sb = self.txt_terminal.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    # ─────────────────────────────────────────────────────────
    # Styles
    # ─────────────────────────────────────────────────────────
    def _group_box_style(self):
        return f"""
            QGroupBox {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
                font-size: 11px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: {COLORS['accent']};
            }}
        """

    def _input_style(self):
        return f"""
            QDoubleSpinBox, QLineEdit, QComboBox {{
                background-color: {COLORS['bg_input']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: bold;
            }}
            QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {{
                border-color: {COLORS['accent']};
            }}
        """

    def _slider_style(self):
        return f"""
            QSlider::groove:horizontal {{
                height: 5px;
                background: {COLORS['bg_input']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS['accent']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {COLORS['accent_cyan']};
            }}
        """

    def _primary_btn_style(self):
        return f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: {COLORS['bg_dark']};
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 8px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_cyan']};
            }}
            QPushButton:pressed {{
                background-color: #1b7c5b;
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
                color: {COLORS['text_muted']};
            }}
        """

    def _secondary_btn_style(self, color=None):
        c = color or COLORS['border_focus']
        return f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {c};
                border: 1px solid {c};
                border-radius: 5px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: {c};
                color: {COLORS['bg_dark']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['bg_input']};
            }}
        """
