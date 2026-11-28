"""
History Viewer screen - Clinical PT review matching Live Test layout:
6-card quantitative progress HUD + Side-by-side ROM and Handle Force Hero Plots
(Time, Force/Angle, Velocity, and Cross-Session Progress Trends).
"""

import re
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
import pyqtgraph as pg

from theme import COLORS
from screens.live_test import HeroPlotPanel


def compute_session_summary(session: dict, data_rows: list) -> dict:
    """Compute or reconstruct clinical rehab metrics from a saved session."""
    notes = session.get("notes", "") or ""
    arm_in = float(session.get("forearm_length_in") or 12.0)
    arm_m = arm_in * 0.0254
    target_r = float(session.get("target_resistance") or 0.0)

    def _note_num(pattern, default=None):
        m = re.search(pattern, notes)
        return float(m.group(1)) if m else default

    reps_match = re.search(r"Reps:\s*(\d+)/(\d+)", notes)
    reps_done = int(reps_match.group(1)) if reps_match else 0
    reps_goal = int(reps_match.group(2)) if reps_match else 10

    if not data_rows:
        return {
            "t": np.array([], dtype=np.float32),
            "rom": np.array([], dtype=np.float32),
            "speed": np.array([], dtype=np.float32),
            "force": np.array([], dtype=np.float32),
            "spo2": np.array([], dtype=np.float32),
            "work_j": _note_num(r"Work:\s*([0-9.]+)\s*J", 0.0) or 0.0,
            "mean_power_w": 0.0,
            "active_tut_s": 0.0,
            "peak_rom": float(session.get("target_angle") or 0.0),
            "peak_force": _note_num(r"Peak Force:\s*([0-9.]+)\s*lbs", 0.0) or 0.0,
            "mean_conc_force": _note_num(r"Mean Force:\s*([0-9.]+)\s*lbs", 0.0) or 0.0,
            "peak_torque": 0.0,
            "reps_done": reps_done,
            "reps_goal": reps_goal,
            "fatigue_pct": _note_num(r"Fatigue Index:\s*([0-9.]+)%", 100.0) or 100.0,
            "smoothness_pct": _note_num(r"Smoothness:\s*([0-9.]+)%", None),
            "avg_spo2": 0.0,
            "arm_in": arm_in,
            "target_r": target_r,
            "early_angle_bins": [],
            "recent_angle_bins": [],
        }

    t = np.asarray([r["timestamp_s"] for r in data_rows], dtype=np.float32)
    rom = np.asarray([r["rom_angle"] for r in data_rows], dtype=np.float32)
    speed = np.asarray([r["speed"] for r in data_rows], dtype=np.float32)
    force = np.maximum(0.0, np.asarray([r["strength"] for r in data_rows], dtype=np.float32))
    spo2 = np.asarray([r["spo2"] for r in data_rows], dtype=np.float32)

    # Reconstruct concentric mechanical work (Joules) and time-under-tension (s)
    work_j = 0.0
    active_tut_s = 0.0
    if len(t) >= 2:
        dt_arr = np.maximum(0.0, np.diff(t))
        d_rom = np.diff(rom)
        conc_step = (d_rom > 0.0) & (speed[1:] > 5.0)
        if np.any(conc_step):
            f_n = force[1:][conc_step] * 4.44822
            d_s = arm_m * (d_rom[conc_step] * np.pi / 180.0)
            work_j = float(np.sum(f_n * d_s))
        tut_step = (np.abs(speed[1:]) > 5.0) & (force[1:] >= 0.5)
        active_tut_s = float(np.sum(dt_arr[tut_step]))

    if work_j <= 0.1:
        note_work = _note_num(r"Work:\s*([0-9.]+)\s*J", None)
        if note_work is not None:
            work_j = note_work

    mean_power_w = (work_j / active_tut_s) if active_tut_s > 0.25 else 0.0

    # Concentric force metrics (ignore unloading / zero-speed rest gaps)
    conc_mask = speed > 10.0
    conc_forces = force[conc_mask]
    mean_conc_force = float(np.mean(conc_forces)) if len(conc_forces) > 0 else 0.0
    peak_force = float(np.max(force)) if len(force) > 0 else 0.0
    peak_torque = peak_force * arm_in

    # Peak ROM (clamped physiological range for clean legacy logs)
    peak_rom = float(np.max(rom)) if len(rom) > 0 else float(session.get("target_angle") or 0.0)

    # Reconstruct rep segments for Early vs Recent Force/Angle curves & Work Fatigue
    rep_curves = []
    rep_works = []
    state = "EXTENDED"
    baseline = float(rom[0]) if len(rom) > 0 else 0.0
    cur_r, cur_f, cur_w, cur_pk = [], [], 0.0, 0.0
    for i in range(len(t)):
        r_i, v_i, f_i = float(rom[i]), float(speed[i]), float(force[i])
        if state == "EXTENDED":
            if r_i < baseline:
                baseline = r_i
            if r_i > baseline + 25.0 and v_i > 10.0:
                state = "FLEXING"
                cur_pk = r_i
                cur_r = [r_i]
                cur_f = [f_i]
                cur_w = 0.0
        elif state == "FLEXING":
            if v_i > 8.0:
                cur_r.append(r_i)
                cur_f.append(f_i)
                if len(cur_r) >= 2 and cur_r[-1] > cur_r[-2]:
                    cur_w += (f_i * 4.44822) * (arm_m * (cur_r[-1] - cur_r[-2]) * np.pi / 180.0)
            if r_i > cur_pk:
                cur_pk = r_i
            if (cur_pk - baseline) >= 30.0 and v_i < -8.0:
                state = "EXTENDING"
        elif state == "EXTENDING":
            if r_i <= max(35.0, baseline + 15.0):
                rep_curves.append((np.asarray(cur_r, dtype=np.float32), np.asarray(cur_f, dtype=np.float32)))
                rep_works.append(cur_w)
                state = "EXTENDED"

    if reps_done == 0 and rep_curves:
        reps_done = len(rep_curves)

    # Fatigue index: prefer saved note, else compare late vs early rep work
    fatigue_pct = _note_num(r"Fatigue Index:\s*([0-9.]+)%", None)
    if fatigue_pct is None:
        if len(rep_works) >= 2 and np.mean(rep_works[:2]) > 0.5:
            fatigue_pct = max(10.0, min(100.0, float(np.mean(rep_works[-2:]) / np.mean(rep_works[:2]) * 100.0)))
        else:
            fatigue_pct = 100.0

    smoothness_pct = _note_num(r"Smoothness:\s*([0-9.]+)%", None)
    valid_spo2 = spo2[spo2 > 0.0]
    avg_spo2 = float(np.mean(valid_spo2)) if len(valid_spo2) > 0 else 0.0

    # Bin early vs recent reps into 10 deg increments (0..160)
    bin_centers = np.linspace(5.0, 155.0, 16, dtype=np.float32)
    early_bins = [[] for _ in range(16)]
    recent_bins = [[] for _ in range(16)]
    for rep_idx, (rr, ff) in enumerate(rep_curves):
        for r_pt, f_pt in zip(rr, ff):
            b = int(max(0.0, min(159.9, float(r_pt))) // 10.0)
            if rep_idx < 2:
                early_bins[b].append(float(f_pt))
            if rep_idx >= max(0, len(rep_curves) - 2):
                recent_bins[b].append(float(f_pt))

    return {
        "t": t,
        "rom": rom,
        "speed": speed,
        "force": force,
        "spo2": spo2,
        "bin_centers": bin_centers,
        "early_bins": early_bins,
        "recent_bins": recent_bins,
        "work_j": work_j,
        "mean_power_w": mean_power_w,
        "active_tut_s": active_tut_s,
        "peak_rom": peak_rom,
        "peak_force": peak_force,
        "mean_conc_force": mean_conc_force,
        "peak_torque": peak_torque,
        "reps_done": reps_done,
        "reps_goal": reps_goal,
        "fatigue_pct": fatigue_pct,
        "smoothness_pct": smoothness_pct,
        "avg_spo2": avg_spo2,
        "arm_in": arm_in,
        "target_r": target_r,
    }


class HistoryViewerScreen(QWidget):
    """Clinical Test History viewer matching Live Test layout and metrics."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.client_id = None
        self.sessions = []
        self._session_summaries = []  # Chronological cache across sessions for Progress Trends & deltas
        self._first_summary = None
        self._active_summary = None
        self.right_plot_mode = "TIME"  # "TIME", "FORCE_ANGLE", "VELOCITY", "TRENDS"

        self.current_time_data = np.array([])
        self.current_rom_data = np.array([])
        self.current_vel_data = np.array([])
        self.current_strength_data = np.array([])
        self.current_spo2_data = np.array([])
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ── Header ─────────────────────────────────────────
        header_layout = QHBoxLayout()
        self.title_label = QLabel("Test History")
        self.title_label.setObjectName("title")
        self.title_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {COLORS['text_primary']}; "
            f"border-bottom: 2px solid {COLORS['accent']}; padding-bottom: 4px;"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.title_label.setGraphicsEffect(shadow)
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        hint = QLabel("Drag axes to scale  |  Drag plot to pan  |  Scroll to zoom  |  Right-click or ↺ to reset")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        header_layout.addWidget(hint)
        layout.addLayout(header_layout)

        # ── Main Content (Left Sessions Drawer + Right Clinical HUD & Hero Plots) ─
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)

        # Left Session Selector Drawer
        self.left_panel = QFrame()
        self.left_panel.setObjectName("card")
        self.left_panel.setFixedWidth(265)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_sessions = QLabel("Recorded Sessions")
        lbl_sessions.setObjectName("section_header")
        left_layout.addWidget(lbl_sessions)

        self.session_list = QListWidget()
        self.session_list.setWordWrap(True)
        self.session_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self.session_list, stretch=2)

        self.lbl_session_info = QLabel("Select a session to inspect.")
        self.lbl_session_info.setWordWrap(True)
        self.lbl_session_info.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 11px;
            padding: 8px;
            background-color: {COLORS['bg_surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 6px;
        """)
        left_layout.addWidget(self.lbl_session_info, stretch=1)

        # Prescribed Target Card (kept concise at bottom of drawer)
        target_box = QFrame()
        target_box.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        tb_layout = QVBoxLayout(target_box)
        tb_layout.setContentsMargins(8, 6, 8, 6)
        tb_layout.setSpacing(2)
        lbl_t_hdr = QLabel("PRESCRIBED RESISTANCE")
        lbl_t_hdr.setAlignment(Qt.AlignCenter)
        lbl_t_hdr.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; font-weight: bold; border: none;")
        tb_layout.addWidget(lbl_t_hdr)

        self.lbl_strength = QLabel("-- lbs")
        self.lbl_strength.setAlignment(Qt.AlignCenter)
        self.lbl_strength.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['graph_strength']}; border: none;")
        tb_layout.addWidget(self.lbl_strength)
        left_layout.addWidget(target_box)

        content_layout.addWidget(self.left_panel)

        # Drawer Collapse Toggle
        self.btn_toggle_sessions = QPushButton("◀")
        self.btn_toggle_sessions.setFixedWidth(22)
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
                font-size: 13px;
                min-width: 0px;
                max-width: 22px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_dark']};
                color: {COLORS['accent']};
            }}
        """)
        self.btn_toggle_sessions.clicked.connect(self._toggle_sessions)
        content_layout.addWidget(self.btn_toggle_sessions)

        # Right Workspace: 6-Card Clinical HUD + Side-by-Side Hero Plots
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        # ── 6-Card PT Progress HUD Strip ──
        hud_frame = QFrame()
        hud_frame.setObjectName("hist_hud_strip")
        hud_frame.setStyleSheet(f"""
            QFrame#hist_hud_strip {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        hud_layout = QHBoxLayout(hud_frame)
        hud_layout.setContentsMargins(8, 6, 8, 6)
        hud_layout.setSpacing(6)

        hud_layout.addWidget(self._create_hud_card("TOTAL WORK", "lbl_hud_work", "lbl_hud_work_sub", "0 J", "Concentric Volume", COLORS['accent']), 1)
        hud_layout.addWidget(self._create_hud_card("ACTIVE ROM", "lbl_hud_rom", "lbl_hud_rom_sub", "0.0°", "Peak Angle", COLORS['graph_rom']), 1)
        hud_layout.addWidget(self._create_hud_card("CONCENTRIC FORCE", "lbl_hud_force", "lbl_hud_force_sub", "0.0 lbs", "Mean • Peak", COLORS['graph_strength']), 1)
        hud_layout.addWidget(self._create_hud_card("REPETITIONS", "lbl_hud_reps", "lbl_hud_reps_sub", "0 / 10", "Time Under Tension", COLORS['text_primary']), 1)
        hud_layout.addWidget(self._create_hud_card("ENDURANCE / FATIGUE", "lbl_hud_fatigue", "lbl_hud_fatigue_sub", "--%", "Rep Work Consistency", COLORS['accent']), 1)
        hud_layout.addWidget(self._create_hud_card("SMOOTHNESS / SPO2", "lbl_hud_smooth", "lbl_hud_smooth_sub", "--%", "Control & Vitals", COLORS.get('accent_cyan', '#00e5ff')), 1)

        right_layout.addWidget(hud_frame)

        # ── Side-by-Side Hero Plots (matches Live Test) ──
        pg.setConfigOptions(antialias=True)
        self.hero_splitter = QSplitter(Qt.Horizontal)
        self.hero_splitter.setChildrenCollapsible(False)

        # Left Hero Plot: ROM vs Time
        self.panel_rom = HeroPlotPanel(0, "Range of Motion (ROM)", COLORS['graph_rom'])
        self.plot_rom = self.panel_rom.plot_item
        self.plot_rom.disableAutoRange()
        self.plot_rom.setLabel('left', 'Joint Angle (°)', color=COLORS['graph_rom'])
        self.plot_rom.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
        self.plot_rom.showGrid(x=True, y=True, alpha=0.25)
        self.plot_rom.getAxis('left').setPen(pg.mkPen(COLORS['graph_rom']))
        self.plot_rom.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_rom']))
        self.curve_rom = self.plot_rom.plot(pen=pg.mkPen(COLORS['graph_rom'], width=2.2), name="ROM")
        self.line_first_rom = pg.InfiniteLine(
            pos=0.0, angle=0,
            pen=pg.mkPen(COLORS['text_muted'], style=Qt.DotLine, width=1.2)
        )
        self.plot_rom.addItem(self.line_first_rom)
        self.line_first_rom.setVisible(False)
        self.panel_rom.maximize_toggled.connect(self._toggle_maximize)
        self.hero_splitter.addWidget(self.panel_rom)

        # Right Hero Plot: Handle Force / Angle / Velocity / Trends
        self.panel_right = HeroPlotPanel(1, "Handle Force", COLORS['graph_strength'])
        self.plot_right = self.panel_right.plot_item
        self.plot_right.disableAutoRange()
        self.plot_right.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
        self.plot_right.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
        self.plot_right.showGrid(x=True, y=True, alpha=0.25)
        self.plot_right.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
        self.plot_right.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
        self.plot_right.getAxis('bottom').setPen(pg.mkPen(COLORS['text_secondary']))
        self.plot_right.getAxis('bottom').setTextPen(pg.mkPen(COLORS['text_secondary']))

        # Mode Toggle Pill Bar in Right Panel Header
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
        self.btn_mode_vel = QPushButton("Velocity")
        self.btn_mode_trends = QPushButton("Trends")
        for btn, mode in (
            (self.btn_mode_time, "TIME"),
            (self.btn_mode_force_angle, "FORCE_ANGLE"),
            (self.btn_mode_vel, "VELOCITY"),
            (self.btn_mode_trends, "TRENDS"),
        ):
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_right_plot_mode(m))
            t_layout.addWidget(btn)
        self.panel_right.add_header_widget(self.toggle_mode_frame)

        # Right plot curves & markers
        self.line_target_force = pg.InfiniteLine(
            pos=0.0, angle=0,
            pen=pg.mkPen(COLORS['warning'], style=Qt.DashLine, width=1.4)
        )
        self.plot_right.addItem(self.line_target_force, ignoreBounds=True)
        self.lbl_target_force = pg.TextItem("", color=COLORS['warning'], anchor=(1, 1), fill=pg.mkColor(13, 17, 23, 180))
        self.plot_right.addItem(self.lbl_target_force, ignoreBounds=True)
        self.lbl_trend_legend = pg.TextItem(
            "● Solid Green: Total Work (J)   |   ■ Dashed Cyan: Peak ROM (°)",
            color=COLORS['text_primary'], anchor=(0, 0), fill=pg.mkColor(13, 17, 23, 200)
        )
        self.plot_right.addItem(self.lbl_trend_legend, ignoreBounds=True)
        self.lbl_trend_legend.setVisible(False)

        self.curve_force = self.plot_right.plot(pen=pg.mkPen(COLORS['graph_strength'], width=2.2), name="Force")
        self.curve_force_early = self.plot_right.plot(pen=pg.mkPen(COLORS['accent'], style=Qt.DashLine, width=1.8), name="Early Reps")
        self.curve_vel = self.plot_right.plot(pen=pg.mkPen(COLORS['graph_speed'], width=2.0), name="Velocity")
        self.curve_trend_work = self.plot_right.plot(
            pen=pg.mkPen(COLORS['accent'], width=2.4), symbol='o', symbolSize=8, symbolBrush=COLORS['accent'], name="Work (J)"
        )
        self.curve_trend_rom = self.plot_right.plot(
            pen=pg.mkPen(COLORS.get('accent_cyan', '#00e5ff'), style=Qt.DashLine, width=2.0),
            symbol='s', symbolSize=7, symbolBrush=COLORS.get('accent_cyan', '#00e5ff'), name="Peak ROM (°)"
        )

        self.panel_right.maximize_toggled.connect(self._toggle_maximize)
        self.hero_splitter.addWidget(self.panel_right)
        self.hero_splitter.setSizes([600, 600])
        right_layout.addWidget(self.hero_splitter, stretch=1)

        content_layout.addWidget(right_panel, stretch=1)
        layout.addLayout(content_layout, stretch=1)

        self._setup_crosshair()
        self._set_right_plot_mode("TIME")

    def _create_hud_card(self, title, attr_name, sub_attr_name, default_val, default_sub, val_color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        v = QVBoxLayout(card)
        v.setContentsMargins(8, 5, 8, 5)
        v.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; font-weight: bold; letter-spacing: 0.4px; border: none;")
        v.addWidget(lbl_t)

        lbl_v = QLabel(default_val)
        lbl_v.setStyleSheet(f"color: {val_color}; font-size: 16px; font-weight: bold; border: none;")
        v.addWidget(lbl_v)

        lbl_s = QLabel(default_sub)
        lbl_s.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px; border: none;")
        v.addWidget(lbl_s)

        setattr(self, attr_name, lbl_v)
        setattr(self, sub_attr_name, lbl_s)
        return card

    def _toggle_maximize(self, idx):
        sizes = self.hero_splitter.sizes()
        if idx == 0:
            if sizes[1] > 0:
                self.hero_splitter.setSizes([1, 0])
                self.panel_rom.set_maximized(True)
            else:
                self.hero_splitter.setSizes([600, 600])
                self.panel_rom.set_maximized(False)
                self.panel_right.set_maximized(False)
        else:
            if sizes[0] > 0:
                self.hero_splitter.setSizes([0, 1])
                self.panel_right.set_maximized(True)
            else:
                self.hero_splitter.setSizes([600, 600])
                self.panel_rom.set_maximized(False)
                self.panel_right.set_maximized(False)

    def _toggle_sessions(self):
        if hasattr(self, '_anim') and self._anim is not None:
            self._anim.stop()
            self._anim_min.stop()

        if self.left_panel.width() > 0:
            target_width = 0
            self.btn_toggle_sessions.setText("▶")
        else:
            target_width = 265
            self.btn_toggle_sessions.setText("◀")

        self._anim = QPropertyAnimation(self.left_panel, b"maximumWidth")
        self._anim.setDuration(220)
        self._anim.setStartValue(self.left_panel.width())
        self._anim.setEndValue(target_width)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim_min = QPropertyAnimation(self.left_panel, b"minimumWidth")
        self._anim_min.setDuration(220)
        self._anim_min.setStartValue(self.left_panel.width())
        self._anim_min.setEndValue(target_width)
        self._anim_min.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim.start()
        self._anim_min.start()

    def _set_right_plot_mode(self, mode: str):
        self.right_plot_mode = mode
        for btn, m in (
            (self.btn_mode_time, "TIME"),
            (self.btn_mode_force_angle, "FORCE_ANGLE"),
            (self.btn_mode_vel, "VELOCITY"),
            (self.btn_mode_trends, "TRENDS"),
        ):
            active = (m == mode)
            accent_c = COLORS['graph_speed'] if mode == "VELOCITY" else (COLORS['accent'] if mode == "TRENDS" else COLORS['graph_strength'])
            if active:
                btn.setStyleSheet(f"QPushButton {{ background-color: {accent_c}; color: #0d1117; border: none; border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 10px; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background-color: transparent; color: {COLORS['text_muted']}; border: none; border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 10px; }} QPushButton:hover {{ color: {COLORS['text_primary']}; }}")

        # Hide all curves first, then show active mode cleanly
        for item in (
            self.curve_force, self.curve_force_early, self.curve_vel,
            self.curve_trend_work, self.curve_trend_rom,
            self.vLine_right, self.hLine_right, self.label_right,
        ):
            item.setVisible(False)
        self.line_target_force.setVisible(False)
        self.lbl_target_force.setVisible(False)
        self.lbl_trend_legend.setVisible(False)
        self.plot_right.getAxis('bottom').setTicks(None)

        if mode == "TIME":
            self.panel_right.set_title("Handle Force")
            self.plot_right.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
            self.plot_right.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
            self.plot_right.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_right.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_right.setXLink(self.plot_rom)
            self.curve_force.setVisible(True)
            self.line_target_force.setVisible(True)
            self.lbl_target_force.setVisible(True)
        elif mode == "FORCE_ANGLE":
            self.panel_right.set_title("Force vs Angle")
            self.plot_right.setLabel('left', 'Handle Force (lbs)', color=COLORS['graph_strength'])
            self.plot_right.setLabel('bottom', 'Joint Angle (°)', color=COLORS['text_secondary'])
            self.plot_right.getAxis('left').setPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_right.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_strength']))
            self.plot_right.setXLink(None)
            self.curve_force.setVisible(True)
            self.curve_force_early.setVisible(True)
            self.line_target_force.setVisible(True)
            self.lbl_target_force.setVisible(True)
        elif mode == "VELOCITY":
            self.panel_right.set_title("Angular Velocity")
            self.plot_right.setLabel('left', 'Velocity (°/s)', color=COLORS['graph_speed'])
            self.plot_right.setLabel('bottom', 'Time (s)', color=COLORS['text_secondary'])
            self.plot_right.getAxis('left').setPen(pg.mkPen(COLORS['graph_speed']))
            self.plot_right.getAxis('left').setTextPen(pg.mkPen(COLORS['graph_speed']))
            self.plot_right.setXLink(self.plot_rom)
            self.curve_vel.setVisible(True)
        elif mode == "TRENDS":
            self.panel_right.set_title("Session Trends")
            self.plot_right.setLabel('left', 'Work (J)  /  Peak ROM (°)', color=COLORS['accent'])
            self.plot_right.setLabel('bottom', 'Session # (Chronological)', color=COLORS['text_secondary'])
            self.plot_right.getAxis('left').setPen(pg.mkPen(COLORS['accent']))
            self.plot_right.getAxis('left').setTextPen(pg.mkPen(COLORS['accent']))
            self.plot_right.setXLink(None)
            self.curve_trend_work.setVisible(True)
            self.curve_trend_rom.setVisible(True)
            self.lbl_trend_legend.setVisible(True)

        self._render_right_plot()

    def _setup_crosshair(self):
        pen = pg.mkPen(COLORS['accent'], style=Qt.DashLine)
        self.vLine_rom = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_rom = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self.vLine_right = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.hLine_right = pg.InfiniteLine(angle=0, movable=False, pen=pen)

        self.plot_rom.addItem(self.vLine_rom, ignoreBounds=True)
        self.plot_rom.addItem(self.hLine_rom, ignoreBounds=True)
        self.plot_right.addItem(self.vLine_right, ignoreBounds=True)
        self.plot_right.addItem(self.hLine_right, ignoreBounds=True)

        bg_color = QColor(COLORS['bg_surface'])
        bg_color.setAlpha(200)
        self.label_rom = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_rom.addItem(self.label_rom, ignoreBounds=True)
        self.label_right = pg.TextItem(color=COLORS['text_primary'], fill=bg_color)
        self.plot_right.addItem(self.label_right, ignoreBounds=True)

        self.proxy_rom = pg.SignalProxy(self.panel_rom.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_rom)
        self.proxy_right = pg.SignalProxy(self.panel_right.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved_right)

    def _mouse_moved_rom(self, evt):
        if len(self.current_time_data) == 0:
            return
        pos = evt[0]
        if self.plot_rom.sceneBoundingRect().contains(pos):
            mp = self.plot_rom.vb.mapSceneToView(pos)
            self._update_crosshair(mp.x())

    def _mouse_moved_right(self, evt):
        if len(self.current_time_data) == 0 or self.right_plot_mode not in ("TIME", "VELOCITY"):
            return
        pos = evt[0]
        if self.plot_right.sceneBoundingRect().contains(pos):
            mp = self.plot_right.vb.mapSceneToView(pos)
            self._update_crosshair(mp.x())

    def _update_crosshair(self, x):
        t_arr = self.current_time_data
        if len(t_arr) == 0:
            return
        idx = int(np.searchsorted(t_arr, x))
        if idx >= len(t_arr):
            idx = len(t_arr) - 1
        elif idx > 0 and abs(x - t_arr[idx - 1]) < abs(x - t_arr[idx]):
            idx -= 1

        t_val = float(t_arr[idx])
        rom_val = float(self.current_rom_data[idx])
        self.vLine_rom.setPos(t_val)
        self.hLine_rom.setPos(rom_val)

        x_rng = self.plot_rom.viewRange()[0]
        y_rng_rom = self.plot_rom.viewRange()[1]
        ax = 1 if t_val > x_rng[0] + (x_rng[1] - x_rng[0]) / 2 else 0
        ay_rom = 1 if rom_val < y_rng_rom[0] + (y_rng_rom[1] - y_rng_rom[0]) / 2 else 0
        self.label_rom.setAnchor((ax, ay_rom))
        self.label_rom.setText(f"Time: {t_val:.1f} s\nROM: {rom_val:.1f}°")
        self.label_rom.setPos(t_val, rom_val)

        if self.right_plot_mode in ("TIME", "VELOCITY"):
            r_val = float(self.current_strength_data[idx]) if self.right_plot_mode == "TIME" else float(self.current_vel_data[idx])
            unit = "lbs" if self.right_plot_mode == "TIME" else "°/s"
            lbl = "Force" if self.right_plot_mode == "TIME" else "Vel"
            self.vLine_right.setVisible(True)
            self.hLine_right.setVisible(True)
            self.label_right.setVisible(True)
            self.vLine_right.setPos(t_val)
            self.hLine_right.setPos(r_val)
            y_rng_r = self.plot_right.viewRange()[1]
            ay_r = 1 if r_val < y_rng_r[0] + (y_rng_r[1] - y_rng_r[0]) / 2 else 0
            self.label_right.setAnchor((ax, ay_r))
            self.label_right.setText(f"Time: {t_val:.1f} s\n{lbl}: {r_val:.1f} {unit}")
            self.label_right.setPos(t_val, r_val)
        else:
            self.vLine_right.setVisible(False)
            self.hLine_right.setVisible(False)
            self.label_right.setVisible(False)

    def load_client(self, client_id):
        """Load session history and compute baseline progress deltas for a client."""
        self.client_id = client_id
        client = self.db.get_client(client_id)
        if client:
            self.title_label.setText(f"Test History: {client['name']}")

        self.sessions = self.db.get_sessions(client_id)
        self.session_list.clear()
        self._session_summaries = []

        # Compute summaries for all sessions (sessions list is newest-first; oldest = last)
        for s in self.sessions:
            rows = self.db.get_session_data(s["id"])
            self._session_summaries.append(compute_session_summary(s, rows))

        self._first_summary = self._session_summaries[-1] if self._session_summaries else None

        total = len(self.sessions)
        for i, session in enumerate(self.sessions):
            session_num = total - i
            date_str = session['date'][:10] if session['date'] else 'Unknown'
            sm = self._session_summaries[i]
            item_text = (
                f"Session #{session_num} • {date_str}\n"
                f"  {session['target_resistance']} lbs  •  {sm['peak_rom']:.0f}°  •  {sm['work_j']:.0f} J"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, session['id'])
            self.session_list.addItem(item)

        self._clear_view()
        if self.sessions:
            self.session_list.setCurrentRow(0)

    def _clear_view(self):
        self._active_summary = None
        for c in (self.curve_rom, self.curve_force, self.curve_force_early, self.curve_vel, self.curve_trend_work, self.curve_trend_rom):
            c.setData([], [])
        self.current_time_data = np.array([])
        self.current_rom_data = np.array([])
        self.current_vel_data = np.array([])
        self.current_strength_data = np.array([])
        self.current_spo2_data = np.array([])
        self.lbl_session_info.setText("Select a session to view its data.")
        self.lbl_strength.setText("-- lbs")

    def _render_right_plot(self):
        sm = self._active_summary
        if sm is None or len(sm["t"]) == 0:
            if self.right_plot_mode != "TRENDS":
                return

        if self.right_plot_mode == "TIME" and sm is not None:
            t = sm["t"]
            f = sm["force"]
            target_r = sm["target_r"]
            t_start = float(t[0])
            t_end = float(t[-1]) if float(t[-1]) > t_start else (t_start + 1.0)
            self.curve_force.setData(t, f)
            y_hi = max(10.0, target_r * 1.4, float(np.max(f)) * 1.2)
            self.line_target_force.setPos(target_r)
            self.line_target_force.setVisible(target_r > 0)
            self.lbl_target_force.setText(f"Target Load: {target_r:.1f} lbs")
            self.lbl_target_force.setPos(t_end, target_r)
            self.lbl_target_force.setVisible(target_r > 0)
            self.plot_rom.setXRange(t_start, t_end, padding=0)
            self.plot_right.setYRange(0.0, y_hi, padding=0)

        elif self.right_plot_mode == "FORCE_ANGLE" and sm is not None:
            centers = sm["bin_centers"]
            early_x, early_y = [], []
            rec_x, rec_y = [], []
            for b in range(len(centers)):
                if sm["early_bins"][b]:
                    early_x.append(float(centers[b]))
                    early_y.append(float(np.mean(sm["early_bins"][b])))
                if sm["recent_bins"][b]:
                    rec_x.append(float(centers[b]))
                    rec_y.append(float(np.mean(sm["recent_bins"][b])))
            self.curve_force_early.setData(early_x, early_y)
            if rec_x:
                self.curve_force.setData(rec_x, rec_y)
            else:
                # Fallback if single partial curl without full rep cycles
                mask = sm["speed"] > 10.0
                if np.any(mask):
                    r_p = sm["rom"][mask]
                    f_p = sm["force"][mask]
                    order = np.argsort(r_p)
                    self.curve_force.setData(r_p[order], f_p[order])
                else:
                    self.curve_force.setData([], [])
            target_r = sm["target_r"]
            y_hi = max(10.0, target_r * 1.4, sm["peak_force"] * 1.2)
            self.line_target_force.setPos(target_r)
            self.line_target_force.setVisible(target_r > 0)
            self.lbl_target_force.setText(f"Target: {target_r:.1f} lbs (Orange=Late, Green=Early)")
            self.lbl_target_force.setPos(155.0, target_r)
            self.lbl_target_force.setVisible(target_r > 0)
            self.plot_right.setXRange(0.0, 160.0, padding=0)
            self.plot_right.setYRange(0.0, y_hi, padding=0)

        elif self.right_plot_mode == "VELOCITY" and sm is not None:
            t = sm["t"]
            v = sm["speed"]
            t_start = float(t[0])
            t_end = float(t[-1]) if float(t[-1]) > t_start else (t_start + 1.0)
            v_abs = max(abs(float(np.min(v))), abs(float(np.max(v))), 20.0)
            self.curve_vel.setData(t, v)
            self.plot_rom.setXRange(t_start, t_end, padding=0)
            self.plot_right.setYRange(-v_abs * 1.15, v_abs * 1.15, padding=0)

        elif self.right_plot_mode == "TRENDS":
            if self._session_summaries:
                # Plot chronological oldest (#1) -> newest (#N)
                chron = list(reversed(self._session_summaries))
                xs = np.arange(1, len(chron) + 1, dtype=np.float32)
                works = np.asarray([c["work_j"] for c in chron], dtype=np.float32)
                roms = np.asarray([c["peak_rom"] for c in chron], dtype=np.float32)
                self.curve_trend_work.setData(xs, works)
                self.curve_trend_rom.setData(xs, roms)
                y_hi = max(50.0, float(np.max(works)) * 1.28, float(np.max(roms)) * 1.28)
                x_lo = 0.6
                x_hi = max(2.2, float(len(chron)) + 0.4)
                ticks = [[(i + 1, f"#{i + 1}") for i in range(len(chron))]]
                self.plot_right.getAxis('bottom').setTicks(ticks)
                self.lbl_trend_legend.setPos(x_lo + 0.08, y_hi * 0.96)
                self.lbl_trend_legend.setVisible(True)
                self.plot_right.setXRange(x_lo, x_hi, padding=0)
                self.plot_right.setYRange(0.0, y_hi, padding=0)

    def _on_session_selected(self, row):
        """Load and display metrics and synchronized graphs for selected session."""
        if row < 0 or row >= len(self.sessions):
            return

        session = self.sessions[row]
        sm = self._session_summaries[row]
        self._active_summary = sm
        first_sm = self._first_summary

        # Update left detail box & target card
        notes_raw = session.get('notes', '') or 'N/A'
        notes_clean = re.sub(r"\s*\|\s*Deficit:\s*Stall at [0-9.]+° \(0\.0 lbs\)", "", notes_raw).replace(' | ', '\n')
        forearm_info = f"Forearm: Pin {session['forearm_pin']} ({sm['arm_in']:.0f}\")\n" if session.get('forearm_pin') else ""
        dur_s = float(sm["t"][-1] - sm["t"][0]) if len(sm["t"]) >= 2 else 0.0
        self.lbl_session_info.setText(
            f"Date: {session['date'][:19]}\n"
            f"Duration: {dur_s:.1f} s  •  Active TUT: {sm['active_tut_s']:.1f} s\n"
            f"{forearm_info}"
            f"Status: {session.get('status', 'completed')}\n\n"
            f"[Saved Summary]\n{notes_clean}"
        )
        self.lbl_strength.setText(f"{sm['target_r']:.1f} lbs")

        # Update 6-Card Clinical HUD (with progression deltas vs Client Session #1!)
        # 1. Total Work
        self.lbl_hud_work.setText(f"{sm['work_j']:.0f} J")
        work_delta_txt = ""
        if first_sm and first_sm is not sm and first_sm["work_j"] > 1.0:
            pct_diff = ((sm["work_j"] - first_sm["work_j"]) / first_sm["work_j"]) * 100.0
            sign = "+" if pct_diff >= 0 else ""
            work_delta_txt = f" • {sign}{pct_diff:.0f}% vs #1"
        self.lbl_hud_work_sub.setText(f"{sm['mean_power_w']:.1f} W avg power{work_delta_txt}")

        # 2. Active ROM
        self.lbl_hud_rom.setText(f"{sm['peak_rom']:.1f}°")
        if first_sm and first_sm is not sm:
            d_rom = sm["peak_rom"] - first_sm["peak_rom"]
            sign = "+" if d_rom >= 0 else ""
            self.lbl_hud_rom_sub.setText(f"{sign}{d_rom:.1f}° vs Session #1")
        else:
            self.lbl_hud_rom_sub.setText("Session #1 Baseline" if first_sm is sm else "Peak Excursion")

        # 3. Concentric Force (Mean • Peak) & Target Attainment
        attain_pct = (sm["mean_conc_force"] / sm["target_r"] * 100.0) if sm["target_r"] > 0.1 else 0.0
        self.lbl_hud_force.setText(f"{sm['mean_conc_force']:.1f} lbs")
        self.lbl_hud_force_sub.setText(f"Peak {sm['peak_force']:.1f} lbs ({sm['peak_torque']:.0f} in·lb) • {attain_pct:.0f}% Tgt")

        # 4. Repetitions
        self.lbl_hud_reps.setText(f"{sm['reps_done']} / {sm['reps_goal']} Reps")
        self.lbl_hud_reps_sub.setText(f"Active TUT: {sm['active_tut_s']:.1f} s @ Pin {session.get('forearm_pin', 4)}")

        # 5. Endurance / Fatigue
        fat = sm["fatigue_pct"]
        self.lbl_hud_fatigue.setText(f"{fat:.0f}%")
        fat_color = COLORS['accent'] if fat >= 90 else (COLORS['warning'] if fat >= 75 else COLORS['danger'])
        fat_status = "● Good Endurance" if fat >= 90 else ("● Mild Fatigue" if fat >= 75 else "● High Fatigue")
        self.lbl_hud_fatigue.setStyleSheet(f"color: {fat_color}; font-size: 16px; font-weight: bold; border: none;")
        self.lbl_hud_fatigue_sub.setText(fat_status)

        # 6. Smoothness & SpO2
        sm_pct = sm["smoothness_pct"]
        spo2_txt = f"SpO2 {sm['avg_spo2']:.0f}%" if sm["avg_spo2"] > 0 else "SpO2 --"
        if sm_pct is not None:
            self.lbl_hud_smooth.setText(f"{sm_pct:.0f}%")
            self.lbl_hud_smooth_sub.setText(f"Motion Fluidity • {spo2_txt}")
        else:
            self.lbl_hud_smooth.setText(f"{sm['avg_spo2']:.0f}%" if sm["avg_spo2"] > 0 else "--%")
            self.lbl_hud_smooth_sub.setText("Pulse Ox Avg" if sm["avg_spo2"] > 0 else "No SpO2 Signal")

        # Update Left Hero Plot (ROM vs Time)
        t = sm["t"]
        rom = sm["rom"]
        self.current_time_data = t
        self.current_rom_data = rom
        self.current_vel_data = sm["speed"]
        self.current_strength_data = sm["force"]
        self.current_spo2_data = sm["spo2"]

        if len(t) == 0:
            self.curve_rom.setData([], [])
            self.line_first_rom.setVisible(False)
            self._render_right_plot()
            return

        t_start = float(t[0])
        t_end = float(t[-1]) if float(t[-1]) > t_start else (t_start + 1.0)
        self.curve_rom.setData(t, rom)
        self.plot_rom.setXRange(t_start, t_end, padding=0)
        self.plot_rom.setYRange(-10.0, max(30.0, float(np.max(rom)) + 15.0), padding=0)

        if first_sm and first_sm is not sm and first_sm["peak_rom"] > 0:
            self.line_first_rom.setPos(first_sm["peak_rom"])
            self.line_first_rom.setVisible(True)
        else:
            self.line_first_rom.setVisible(False)

        self._render_right_plot()

    def showEvent(self, event):
        super().showEvent(event)
        sm = getattr(self, "_active_summary", None)
        if sm is not None and len(sm.get("t", [])) > 0:
            t_start = float(sm["t"][0])
            t_end = float(sm["t"][-1]) if float(sm["t"][-1]) > t_start else (t_start + 1.0)
            self.plot_rom.setXRange(t_start, t_end, padding=0)
            self._render_right_plot()
