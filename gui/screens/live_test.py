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

import time
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QComboBox, QFrame, QFormLayout, QSplitter,
    QGraphicsDropShadowEffect, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QTimer
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
        self.btn_reset = QPushButton("⟲ Reset")
        self.btn_reset.setToolTip("Reset view (autorange)")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFixedHeight(24)
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 1px 7px;
                font-size: 11px;
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
        self.btn_maximize = QPushButton("Maximize")
        self.btn_maximize.setToolTip("Maximize panel")
        self.btn_maximize.setCursor(Qt.PointingHandCursor)
        self.btn_maximize.setFixedHeight(24)
        self.btn_maximize.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 1px 7px;
                font-size: 11px;
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
            self.btn_maximize.setText("Restore")
            self.btn_maximize.setToolTip("Restore side-by-side view")
            self.btn_maximize.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['accent_dark']};
                    color: {COLORS['accent']};
                    border: 1px solid {COLORS['accent']};
                    border-radius: 4px;
                    padding: 1px 7px;
                    font-size: 11px;
                    min-width: 0px;
                }}
            """)
        else:
            self.btn_maximize.setText("Maximize")
            self.btn_maximize.setToolTip("Maximize panel")
            self.btn_maximize.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_surface']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    padding: 1px 7px;
                    font-size: 11px;
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

        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.force_data = []
        self.spo2_data = []
        self.ticks = 0

        # Physical Therapy Clinical Metrics
        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self._angle_zero_offset = 0.0

        # Repetition state machine
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.session_baseline_rom = 0.0

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

        # ── Action Controls Toolbar (Single Integrated Row) ─
        controls = QFrame()
        controls.setObjectName("card")
        controls.setStyleSheet(f"""
            QFrame#card {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 8, 14, 8)
        controls_layout.setSpacing(12)

        # Target Load Parameter
        load_box = QHBoxLayout()
        load_box.setSpacing(8)
        lbl_load = QLabel("Target Load:")
        lbl_load.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        load_box.addWidget(lbl_load)

        self.spin_resistance = QDoubleSpinBox()
        self.spin_resistance.setRange(0.0, 25.0)
        self.spin_resistance.setValue(10.0)
        self.spin_resistance.setSingleStep(0.5)
        self.spin_resistance.setDecimals(1)
        self.spin_resistance.setSuffix(" lbs")
        self.spin_resistance.setMinimumHeight(34)
        self.spin_resistance.setKeyboardTracking(False)
        self.spin_resistance.valueChanged.connect(self._on_resistance_value_changed)
        if self.spin_resistance.lineEdit():
            self.spin_resistance.lineEdit().returnPressed.connect(self._submit_resistance)
        load_box.addWidget(self.spin_resistance)

        self.btn_submit_resistance = QPushButton("✓ Submit")
        self.btn_submit_resistance.setToolTip("Transmit target load to NEMA stepper motor")
        self.btn_submit_resistance.setCursor(Qt.PointingHandCursor)
        self.btn_submit_resistance.setMinimumHeight(34)
        self.btn_submit_resistance.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['accent']};
                border: 1px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: {COLORS['accent_dark']};
            }}
        """)
        self.btn_submit_resistance.clicked.connect(self._submit_resistance)
        load_box.addWidget(self.btn_submit_resistance)
        controls_layout.addLayout(load_box)

        # Forearm Length Parameter (Pin 1: 9" to Pin 5: 13")
        forearm_box = QHBoxLayout()
        forearm_box.setSpacing(8)
        lbl_forearm = QLabel("Forearm Length:")
        lbl_forearm.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        forearm_box.addWidget(lbl_forearm)

        self.combo_forearm = QComboBox()
        self.combo_forearm.setMinimumHeight(34)
        self.combo_forearm.setMinimumWidth(165)
        self.combo_forearm.setCursor(Qt.PointingHandCursor)
        for pin_num in range(1, 6):
            length_in = float(pin_num + 8)  # Pin 1=9", Pin 2=10", Pin 3=11", Pin 4=12", Pin 5=13"
            cm = length_in * 2.54
            self.combo_forearm.addItem(
                f"Pin {pin_num} — {length_in:.0f}\" ({cm:.1f} cm)",
                userData={"pin": pin_num, "inches": length_in, "meters": length_in * 0.0254}
            )
        self.combo_forearm.setCurrentIndex(3)  # Default Pin 4 (12 in)
        self.combo_forearm.currentIndexChanged.connect(self._on_forearm_changed)
        forearm_box.addWidget(self.combo_forearm)
        controls_layout.addLayout(forearm_box)

        # Zero / Tare Encoder & Load Cell Button
        self.btn_zero = QPushButton("⟲ Home && Tare")
        self.btn_zero.setToolTip("Home NEMA stepper carriage (forward to end, back off 5 mm) and tare sensors")
        self.btn_zero.setCursor(Qt.PointingHandCursor)
        self.btn_zero.setMinimumHeight(38)
        self.btn_zero.setMinimumWidth(130)
        self.btn_zero.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_surface']};
                color: {COLORS['info']};
                border: 1px solid {COLORS['info']};
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['info']};
                color: white;
            }}
        """)
        self.btn_zero.clicked.connect(self._zero_encoder)
        controls_layout.addWidget(self.btn_zero)

        controls_layout.addStretch()

        # Start / Stop Button
        self.btn_start_stop = QPushButton("▶  Start Test")
        self.btn_start_stop.setObjectName("primary")
        self.btn_start_stop.setCursor(Qt.PointingHandCursor)
        self.btn_start_stop.setMinimumHeight(44)
        self.btn_start_stop.setMinimumWidth(150)
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
        controls_layout.addWidget(self.btn_start_stop)

        # Save to Database Button
        self.btn_save = QPushButton("✓ Save to Database")
        self.btn_save.setObjectName("primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setMinimumHeight(44)
        self.btn_save.setMinimumWidth(160)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
        controls_layout.addWidget(self.btn_save)

        # Discard Button
        self.btn_discard = QPushButton("✕ Discard")
        self.btn_discard.setObjectName("danger")
        self.btn_discard.setCursor(Qt.PointingHandCursor)
        self.btn_discard.setMinimumHeight(44)
        self.btn_discard.setMinimumWidth(100)
        self.btn_discard.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
        controls_layout.addWidget(self.btn_discard)

        # Session Timer Readout Card
        timer_box = QFrame()
        timer_box.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        tb_layout = QHBoxLayout(timer_box)
        tb_layout.setContentsMargins(10, 4, 12, 4)
        tb_layout.setSpacing(6)
        lbl_timer_icon = QLabel("⏱")
        lbl_timer_icon.setStyleSheet(f"font-size: 15px; color: {COLORS['text_muted']};")
        tb_layout.addWidget(lbl_timer_icon)

        self.lbl_timer = QLabel("0.0 s")
        self.lbl_timer.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 20px; font-weight: bold; font-family: monospace;")
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        self.lbl_timer.setMinimumWidth(75)
        tb_layout.addWidget(self.lbl_timer)
        controls_layout.addWidget(timer_box)

        layout.addWidget(controls)

        # ── Physical Therapy Quantitative HUD Strip ────────
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
        hud_layout.setContentsMargins(12, 8, 12, 8)
        hud_layout.setSpacing(10)

        # 1. Repetitions Card
        hud_layout.addWidget(self._create_hud_card(
            title="REPETITIONS",
            attr_name="lbl_hud_reps",
            sub_attr_name="lbl_hud_reps_sub",
            default_val="0 Reps",
            default_sub="Target: 10 Reps",
            val_color=COLORS['accent'],
        ))

        # 2. Active ROM Card
        hud_layout.addWidget(self._create_hud_card(
            title="ACTIVE ROM",
            attr_name="lbl_hud_rom",
            sub_attr_name="lbl_hud_rom_sub",
            default_val="0.0°",
            default_sub="Current: 0.0°",
            val_color=COLORS['graph_rom'],
        ))

        # 3. Handle Force / Strength Card
        hud_layout.addWidget(self._create_hud_card(
            title="HANDLE FORCE",
            attr_name="lbl_hud_force",
            sub_attr_name="lbl_hud_force_sub",
            default_val="0.0 lbs",
            default_sub="Peak: 0.0 lbs • Target: 10.0 lbs",
            val_color=COLORS['graph_strength'],
        ))

        # 4. Therapy Work Done Card
        hud_layout.addWidget(self._create_hud_card(
            title="THERAPY WORK",
            attr_name="lbl_hud_work",
            sub_attr_name="lbl_hud_work_sub",
            default_val="0 J",
            default_sub="Cumulative Energy",
            val_color=COLORS['graph_strength'],
        ))

        # 5. SpO2 Vitals Card
        hud_layout.addWidget(self._create_hud_card(
            title="PULSE OXIMETRY (VITALS)",
            attr_name="lbl_hud_spo2",
            sub_attr_name="lbl_hud_spo2_sub",
            default_val="98%",
            default_sub="● Normal Saturation",
            val_color=COLORS['graph_spo2'],
        ))

        layout.addWidget(hud_frame)

        # ── Two Hero Plots (Side-by-Side Horizontal QSplitter)
        pg.setConfigOptions(antialias=True)
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
            pen=pg.mkPen(COLORS['graph_rom'], width=2.8), name="ROM"
        )
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

        self.btn_mode_time = QPushButton("⏱ Time")
        self.btn_mode_angle = QPushButton("📐 Angle")
        for btn in (self.btn_mode_time, self.btn_mode_angle):
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
        self.btn_mode_time.clicked.connect(lambda: self._set_force_plot_mode("TIME"))
        self.btn_mode_angle.clicked.connect(lambda: self._set_force_plot_mode("ANGLE"))
        t_layout.addWidget(self.btn_mode_time)
        t_layout.addWidget(self.btn_mode_angle)
        self.panel_force.add_header_widget(self.toggle_mode_frame)

        # Dashed Target Resistance Reference Line
        self.line_target_force = pg.InfiniteLine(
            pos=10.0, angle=0,
            pen=pg.mkPen(COLORS['warning'], style=Qt.DashLine, width=1.5)
        )
        self.plot_force.addItem(self.line_target_force)
        self.lbl_target_force_line = pg.TextItem("Target Load: 10.0 lbs", color=COLORS['warning'], anchor=(1, 1))
        self.lbl_target_force_line.setPos(self.time_window - 0.4, 10.0)
        self.plot_force.addItem(self.lbl_target_force_line)

        # Live Force Curve
        self.curve_force_live = self.plot_force.plot(
            pen=pg.mkPen(COLORS['graph_strength'], width=2.8), name="Live Force"
        )

        # Deficit Callout & Marker (active in Angle mode)
        self.deficit_marker = pg.ScatterPlotItem(
            size=14, pen=pg.mkPen(COLORS['danger'], width=2), brush=pg.mkBrush(COLORS['warning'])
        )
        self.plot_force.addItem(self.deficit_marker)
        self.deficit_callout = pg.TextItem("", color=COLORS['warning'], anchor=(0.5, 1.2))
        self.plot_force.addItem(self.deficit_callout)

        self.panel_force.maximize_toggled.connect(self._toggle_maximize)
        self.hero_splitter.addWidget(self.panel_force)

        # 50/50 Initial Split
        self.hero_splitter.setSizes([600, 600])
        layout.addWidget(self.hero_splitter, stretch=1)

        self._set_force_plot_mode("TIME")
        self._setup_crosshair()

    def _create_hud_card(self, title, attr_name, sub_attr_name, default_val, default_sub, val_color):
        """Builds a single quantitative physical therapy card."""
        card = QFrame()
        card.setObjectName("hud_card")
        card.setStyleSheet(f"""
            QFrame#hud_card {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(10, 6, 10, 6)
        c_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        c_layout.addWidget(lbl_title)

        lbl_val = QLabel(default_val)
        lbl_val.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {val_color};")
        setattr(self, attr_name, lbl_val)
        c_layout.addWidget(lbl_val)

        lbl_sub = QLabel(default_sub)
        lbl_sub.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
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

        self.proxy_1 = pg.SignalProxy(self.panel_rom.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_rom)
        self.proxy_2 = pg.SignalProxy(self.panel_force.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_force)

    def _mouse_moved_rom(self, evt):
        if not self.time_data:
            return
        pos = evt[0]
        if self.plot_rom.sceneBoundingRect().contains(pos):
            mousePoint = self.plot_rom.vb.mapSceneToView(pos)
            x_val = mousePoint.x()
            t_arr = np.array(self.time_data)
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
        """Toggle Hero Plot 2 between Force vs Time and Force vs Angle."""
        self.force_plot_mode = mode
        active_style = f"""
            QPushButton {{
                font-size: 11px;
                font-weight: bold;
                padding: 2px 8px;
                border: none;
                border-radius: 4px;
                color: #0d1117;
                background-color: {COLORS['graph_strength']};
                min-width: 0px;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                font-size: 11px;
                padding: 2px 8px;
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
            self.btn_mode_time.setStyleSheet(active_style)
            self.btn_mode_angle.setStyleSheet(inactive_style)
            self.panel_force.set_title("Handle Force")
            self.plot_force.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
            self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_secondary']))
            self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_secondary']))
            self.deficit_marker.setVisible(False)
            self.deficit_callout.setVisible(False)
            current_t = self.time_data[-1] if self.time_data else 0.0
            if current_t > self.time_window:
                x_min = current_t - self.time_window
                x_max = current_t
            else:
                x_min = 0.0
                x_max = self.time_window
            self.plot_force.setXRange(x_min, x_max, padding=0)
            self.lbl_target_force_line.setPos(x_max - 0.4, target_r)
            if self.time_data and self.force_data:
                self.curve_force_live.setData(np.array(self.time_data), np.array(self.force_data))
        else:
            self.btn_mode_time.setStyleSheet(inactive_style)
            self.btn_mode_angle.setStyleSheet(active_style)
            self.panel_force.set_title("Handle Force")
            self.plot_force.setLabel('bottom', 'Joint Angle (°)', color=COLORS['text_primary'])
            self.plot_force.getAxis('bottom').setPen(pg.mkPen(COLORS['text_primary']))
            self.plot_force.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_primary']))
            self.deficit_marker.setVisible(True)
            self.deficit_callout.setVisible(True)
            self.plot_force.setXRange(0, 160, padding=0)
            self.lbl_target_force_line.setPos(155, target_r)
            if self.rom_data and self.force_data:
                recent_pts = min(len(self.rom_data), 300)
                self.curve_force_live.setData(np.array(self.rom_data[-recent_pts:]), np.array(self.force_data[-recent_pts:]))

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
                t_arr = np.array(self.time_data)
                idx = np.searchsorted(t_arr, x_val)
                if idx >= len(t_arr):
                    idx = len(t_arr) - 1
                t_pt = t_arr[idx]
                f_pt = self.force_data[idx]
                self.vLine_force.setPos(t_pt)
                self.hLine_force.setPos(f_pt)
                self.label_force_hover.setText(f"Time: {t_pt:.1f}s\nForce: {f_pt:.1f} lbs")
                self.label_force_hover.setPos(t_pt, f_pt)
            else:
                self.vLine_force.setPos(x_val)
                self.hLine_force.setPos(y_val)
                self.label_force_hover.setText(f"Angle: {x_val:.1f}°\nForce: {y_val:.1f} lbs")
                self.label_force_hover.setPos(x_val, y_val)

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

    def _on_resistance_value_changed(self, val):
        self.line_target_force.setPos(val)
        if self.force_plot_mode == "TIME":
            current_t = self.time_data[-1] if self.time_data else self.time_window
            self.lbl_target_force_line.setPos(max(self.time_window, current_t) - 0.4, val)
        else:
            self.lbl_target_force_line.setPos(155, val)
        self.lbl_target_force_line.setText(f"Target Load: {val:.1f} lbs")
        self.plot_force.setYRange(0, max(25.0, val * 1.6), padding=0)
        if self.last_deficit_angle is None:
            self.lbl_hud_force_sub.setText(f"Peak: {getattr(self, 'max_session_force', 0.0):.1f} lbs • Target: {val:.1f} lbs")

    def _submit_resistance(self):
        """Transmit commanded target resistance to STM32 NEMA stepper controller."""
        val = self.spin_resistance.value()
        if getattr(self, 'generator', None):
            self.generator.target_resistance = val
        if getattr(self, 'hw', None):
            if not self.hw.is_connected:
                self.hw.connect()
            if self.hw.is_connected:
                self.hw.set_resistance(val)
                self.lbl_status.setText(f"● RESISTANCE SUBMITTED: {val:.1f} LBS (NEMA Position Commanded)")
                self.lbl_status.setStyleSheet(
                    f"color: {COLORS['success']}; font-size: 14px; font-weight: bold; "
                    f"padding: 4px 10px; background-color: {COLORS['bg_surface']}; "
                    f"border-radius: 6px; border: 1px solid {COLORS['success']};"
                )
                if hasattr(self, 'btn_submit_resistance'):
                    self.btn_submit_resistance.setText("✓ Sent")
                    QTimer.singleShot(1000, lambda: self.btn_submit_resistance.setText("✓ Submit") if hasattr(self, 'btn_submit_resistance') else None)

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
            self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['warning']};")
            QApplication.processEvents()
            self.hw.home()
            self.hw.zero()
        self.current_rom = 0.0
        self.current_force = 0.0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        if not self.is_running:
            self.time_data = []
            self.rom_data = []
            self.speed_data = []
            self.force_data = []
            self.spo2_data = []
            self.preview_time = 0.0
            self.curve_rom.setData([], [])
            self.curve_force_live.setData([], [])
        self.lbl_hud_rom.setText("0.0°")
        self.lbl_hud_rom_sub.setText("Live Angle: 0.0°")
        self.lbl_hud_force.setText("0.0 lbs")
        self.lbl_hud_force_sub.setText(f"Live Sensor • Target: {self.spin_resistance.value():.1f} lbs")
        self.lbl_status.setText("● NEMA HOMED & SENSORS TARED")
        self.lbl_status.setStyleSheet(f"color: {COLORS['info']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['info']};")

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
        if self.hw.is_connected:
            self.hw.start_streaming(target_resistance=None)
            self.lbl_status.setText("● LIVE PREVIEW (Hardware Ready — Click 'Submit' to Set Load or 'Start Test')")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.generator = LiveDataGenerator(target_resistance=self.spin_resistance.value())
            self.lbl_status.setText("● LIVE PREVIEW (Simulated — Click 'Start Test' to Record)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
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
        """Reset test session state while maintaining real-time sensor preview."""
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

        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.force_data = []
        self.spo2_data = []

        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.session_baseline_rom = self.current_rom

        self.curve_rom.setData([], [])
        self.curve_force_live.setData([], [])
        self.deficit_marker.setData([], [])
        self.deficit_callout.setText("")

        # Reset plot viewports cleanly back to 0.0s
        self.plot_rom.setXRange(0.0, self.time_window, padding=0)
        if self.force_plot_mode == "TIME":
            self.plot_force.setXRange(0.0, self.time_window, padding=0)
        else:
            self.plot_force.setXRange(0.0, 160.0, padding=0)

        self.lbl_hud_reps.setText("0 Reps")
        self.lbl_hud_reps_sub.setText("Target: 10 Reps")
        self.lbl_hud_rom.setText(f"{self.current_rom:.1f}°")
        self.lbl_hud_rom_sub.setText(f"Live Angle: {self.current_rom:.1f}°")
        self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
        self.lbl_hud_force.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {COLORS['graph_strength']};")
        self.lbl_hud_force_sub.setText(f"Live Sensor • Target: {self.spin_resistance.value():.1f} lbs")
        self.lbl_hud_force_sub.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['text_muted']};")
        self.lbl_hud_work.setText("0 J")
        if self.current_spo2 > 0:
            self.lbl_hud_spo2.setText(f"{self.current_spo2:.0f}%")
        else:
            self.lbl_hud_spo2.setText("---%")

        self.lbl_timer.setText("Ready (0.0 s)")
        if self.hw.is_connected:
            self.lbl_status.setText("● LIVE PREVIEW (Hardware Ready — Click 'Start Test' to Record)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.lbl_status.setText("● LIVE PREVIEW (Simulated — Click 'Start Test' to Record)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")

        self.btn_start_stop.setText("▶  Start Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
        self.generator = LiveDataGenerator(target_resistance=target_resistance)
        self._on_resistance_changed(target_resistance)

        self.is_running = True
        self.spin_resistance.setEnabled(True)
        self.btn_zero.setEnabled(False)
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)

        # Clear session buffers for the new recording
        self.full_time_data = []
        self.full_rom_data = []
        self.full_speed_data = []
        self.full_force_data = []
        self.full_spo2_data = []

        self.time_data = []
        self.rom_data = []
        self.speed_data = []
        self.force_data = []
        self.spo2_data = []

        self.reps_count = 0
        self.max_session_rom = 0.0
        self.max_session_force = 0.0
        self.therapy_work_j = 0.0
        self.last_deficit_angle = None
        self.last_deficit_force = None
        self.rep_state = "EXTENDED"
        self.rep_rom_buf = []
        self.rep_force_buf = []
        self.session_baseline_rom = self.current_rom

        # Clear curves and reset plot viewports cleanly to 0.0s for the new test
        self.curve_rom.setData([], [])
        self.curve_force_live.setData([], [])
        self.deficit_marker.setData([], [])
        self.deficit_callout.setText("")

        self.plot_rom.setXRange(0.0, self.time_window, padding=0)
        if self.force_plot_mode == "TIME":
            self.plot_force.setXRange(0.0, self.time_window, padding=0)
        else:
            self.plot_force.setXRange(0.0, 160.0, padding=0)

        self.lbl_timer.setText("0.0 s")

        self._start_time = time.time()
        self.elapsed_time = 0.0
        self.ticks = 0
        self._hw_start_ms = None

        self.btn_start_stop.setText("⏹  Stop Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
            if not self.hw.is_streaming:
                self.hw.start_streaming(target_resistance=target_resistance)
            else:
                self.hw.set_resistance(target_resistance)
            self.lbl_status.setText("● RECORDING (Live)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")
        else:
            self.lbl_status.setText("● RECORDING (Simulated)")
            self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")

        if not self.timer.isActive():
            self.timer.start()

    def _stop_test(self):
        self.is_running = False

        if self.hw.is_connected:
            self.hw.set_resistance(0.0)

        self.lbl_status.setText("● COMPLETE — Save or Discard?")
        self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['warning']};")

        self.btn_start_stop.setVisible(True)
        self.btn_start_stop.setText("▶  Start New Test")
        self.btn_start_stop.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
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
        notes = f"Reps: {self.reps_count} | Peak ROM: {observed_max_rom:.1f}° | Peak Force: {observed_max_force:.1f} lbs ({peak_torque_in_lb:.1f} in-lb) | Forearm: Pin {forearm_pin} ({forearm_inches:.0f}\") | Deficit: {deficit_str} | Work: {self.therapy_work_j:.0f} J"

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
        self.lbl_status.setText("● SAVED TO DATABASE — Live Preview Ready")
        self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")

    def _discard_test(self):
        self._reset()
        self.lbl_status.setText("● DISCARDED — Live Preview Ready")
        self.lbl_status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['danger']};")

    def _append_preview_sample(self, t_val, rom, speed, force, spo2):
        """Append rolling live sensor sample for pre-test and post-test visual preview."""
        self.time_data.append(t_val)
        self.rom_data.append(rom)
        self.speed_data.append(speed)
        self.force_data.append(force)
        self.spo2_data.append(spo2)
        if len(self.time_data) > self.MAX_POINTS:
            self.time_data = self.time_data[-self.MAX_POINTS:]
            self.rom_data = self.rom_data[-self.MAX_POINTS:]
            self.speed_data = self.speed_data[-self.MAX_POINTS:]
            self.force_data = self.force_data[-self.MAX_POINTS:]
            self.spo2_data = self.spo2_data[-self.MAX_POINTS:]

    def _append_sample(self, t_val, rom, speed, force, spo2):
        self.full_time_data.append(t_val)
        self.full_rom_data.append(rom)
        self.full_speed_data.append(speed)
        self.full_force_data.append(force)
        self.full_spo2_data.append(spo2)

        self.time_data.append(t_val)
        self.rom_data.append(rom)
        self.speed_data.append(speed)
        self.force_data.append(force)
        self.spo2_data.append(spo2)
        self.ticks += 1
        self.current_spo2 = spo2

        # Rolling window for time plot
        if len(self.time_data) > self.MAX_POINTS:
            self.time_data = self.time_data[-self.MAX_POINTS:]
            self.rom_data = self.rom_data[-self.MAX_POINTS:]
            self.speed_data = self.speed_data[-self.MAX_POINTS:]
            self.force_data = self.force_data[-self.MAX_POINTS:]
            self.spo2_data = self.spo2_data[-self.MAX_POINTS:]

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

                # Analyze concentric buffer for force deficit valley
                if self.rep_rom_buf:
                    r_arr = np.array(self.rep_rom_buf)
                    f_arr = np.array(self.rep_force_buf)
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
        if self.is_running:
            self.elapsed_time = time.time() - self._start_time
        target_r = self.spin_resistance.value()
        new_data = False

        # Continuously poll samples and auto-reconnect if MCU was reset via NRST
        samples = self.hw.read_samples()

        if self.hw.is_connected:
            if "RECONNECTING" in self.lbl_status.text() and not self.is_running and not self.btn_save.isVisible():
                self.lbl_status.setText("● LIVE PREVIEW (Hardware Ready — Click 'Start Test' to Record)")
                self.lbl_status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['accent']};")

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

                    if self.is_running:
                        if self._hw_start_ms is None:
                            self._hw_start_ms = t_ms
                        sample_time = max(0.0, (t_ms - self._hw_start_ms) / 1000.0)
                        self._append_sample(sample_time, rom, speed, force_val, spo2)
                    elif not self.btn_save.isVisible():
                        self.preview_time += (1.0 / 50.0)
                        self._append_preview_sample(self.preview_time, rom, speed, force_val, spo2)
                new_data = True
            elif not self.time_data and not self.is_running and not self.btn_save.isVisible():
                self.preview_time += self.dt
                self._append_preview_sample(self.preview_time, self.hw.last_angle, self.hw.last_velocity,
                                            max(0.0, float(self.hw.last_load_cell)),
                                            getattr(self.hw, 'last_spo2', 0.0))
                new_data = True
        else:
            if not self.is_running and not self.btn_save.isVisible() and "RECONNECTING" not in self.lbl_status.text() and "HOMING" not in self.lbl_status.text():
                self.lbl_status.setText("● RECONNECTING TO HARDWARE (Push NRST or Plug USB)...")
                self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 14px; font-weight: bold; padding: 4px 10px; background-color: {COLORS['bg_surface']}; border-radius: 6px; border: 1px solid {COLORS['warning']};")
            if self.generator:
                self.preview_time += self.dt
                sample_clock = (time.time() - self._start_time) if self.is_running else self.preview_time
                rom, speed, force_val, spo2 = self.generator.next_sample(sample_clock)
                self.current_rom = rom
                self.current_speed = speed
                self.current_force = force_val
                self.current_spo2 = spo2

                if self.is_running:
                    sample_time = max(0.0, time.time() - self._start_time)
                    self._append_sample(sample_time, rom, speed, force_val, spo2)
                elif not self.btn_save.isVisible():
                    self._append_preview_sample(self.preview_time, rom, speed, force_val, spo2)
                new_data = True

        if new_data and self.time_data and (self.is_running or not self.btn_save.isVisible()):
            t = np.array(self.time_data)
            rom_arr = np.array(self.rom_data)
            force_arr = np.array(self.force_data)

            # Auto-scale force Y axis if force approaches or exceeds max
            y_max = max(25.0, target_r * 1.5, self.max_session_force * 1.25)
            self.plot_force.setYRange(0, y_max, padding=0)

            # 1. Update Hero Plot 1: ROM vs. Time
            if self.panel_rom.isVisible():
                self.curve_rom.setData(t, rom_arr)
                current_t = self.time_data[-1]
                if current_t > self.time_window:
                    x_min = current_t - self.time_window
                    x_max = current_t
                else:
                    x_min = 0.0
                    x_max = self.time_window
                self.plot_rom.setXRange(x_min, x_max, padding=0)

            # 2. Update Hero Plot 2: Force (Time or Angle Mode)
            if self.panel_force.isVisible():
                if self.force_plot_mode == "TIME":
                    self.curve_force_live.setData(t, force_arr)
                    current_t = self.time_data[-1]
                    if current_t > self.time_window:
                        x_min = current_t - self.time_window
                        x_max = current_t
                    else:
                        x_min = 0.0
                        x_max = self.time_window
                    self.plot_force.setXRange(x_min, x_max, padding=0)
                    self.lbl_target_force_line.setPos(x_max - 0.4, target_r)
                    self.deficit_marker.setData([], [])
                    self.deficit_callout.setText("")
                else:
                    recent_pts = min(len(rom_arr), 300)
                    self.curve_force_live.setData(rom_arr[-recent_pts:], force_arr[-recent_pts:])
                    self.plot_force.setXRange(0.0, 160.0, padding=0)
                    self.lbl_target_force_line.setPos(155, target_r)
                    if self.is_running and self.last_deficit_angle is not None:
                        self.deficit_marker.setData([self.last_deficit_angle], [self.last_deficit_force])
                        self.deficit_callout.setPos(self.last_deficit_angle, self.last_deficit_force)
                        self.deficit_callout.setText(f"Stall: {self.last_deficit_angle:.1f}° ({self.last_deficit_force:.1f} lbs)")
                    else:
                        self.deficit_marker.setData([], [])
                        self.deficit_callout.setText("")

        # Update HUD Cards
        if self.is_running:
            self.lbl_hud_reps.setText(f"{self.reps_count} Reps")
            self.lbl_hud_rom.setText(f"{self.max_session_rom:.1f}°")
            self.lbl_hud_rom_sub.setText(f"Current: {self.current_rom:.1f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
            if self.last_deficit_angle is not None:
                self.lbl_hud_force_sub.setText(f"Stall: {self.last_deficit_angle:.1f}° ({self.last_deficit_force:.1f} lbs)")
                self.lbl_hud_force_sub.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['warning']};")
            else:
                peak_torque_in_lb = self.max_session_force * self.get_forearm_inches()
                self.lbl_hud_force_sub.setText(f"Peak: {self.max_session_force:.1f} lbs ({peak_torque_in_lb:.1f} in-lb) • Target: {target_r:.1f} lbs")
                self.lbl_hud_force_sub.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['text_muted']};")
            self.lbl_hud_work.setText(f"{self.therapy_work_j:.0f} J")
            self.lbl_hud_work_sub.setText(f"Pin {self.get_forearm_pin()} ({self.get_forearm_inches():.0f}\") Energy")
            if self.time_data:
                self.lbl_timer.setText(f"{self.time_data[-1]:.1f} s")
        elif not self.btn_save.isVisible():
            # Preview mode before test
            self.lbl_hud_reps.setText("0 Reps")
            self.lbl_hud_rom.setText(f"{self.current_rom:.1f}°")
            self.lbl_hud_rom_sub.setText(f"Live Angle: {self.current_rom:.1f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")
            self.lbl_hud_force_sub.setText(f"Live Sensor • Target: {target_r:.1f} lbs")
            self.lbl_hud_work.setText("0 J")
            self.lbl_timer.setText("Ready (0.0 s)")
        else:
            # Post-test review mode (Save/Discard visible)
            self.lbl_hud_rom_sub.setText(f"Live: {self.current_rom:.1f}°")
            self.lbl_hud_force.setText(f"{self.current_force:.1f} lbs")

        # SpO2 Vitals Display (always updates)
        if self.current_spo2 > 0.0:
            self.lbl_hud_spo2.setText(f"{self.current_spo2:.0f}%")
            self.lbl_hud_spo2.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {COLORS.get('accent_cyan', '#00e5ff')};")
            self.lbl_hud_spo2_sub.setText("● Sensor Active")
            self.lbl_hud_spo2_sub.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['accent']};")
        else:
            self.lbl_hud_spo2.setText("---%")
            self.lbl_hud_spo2.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {COLORS['text_muted']};")
            self.lbl_hud_spo2_sub.setText("Place Finger on Sensor")
            self.lbl_hud_spo2_sub.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['text_muted']};")
