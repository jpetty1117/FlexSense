# FlexSense

FlexSense is an active physical therapy and rehabilitation device for upper-limb strength training (specifically bicep curls). The machine uses a torque actuator to impose controlled resistance on the user while logging biomechanical and physiological telemetry in real time to a desktop GUI on a connected laptop.

---

## System Architecture Overview

The FlexSense platform consists of three integrated software layers working together over real-time communication protocols:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Desktop Clinical GUI (PySide6)                     │
│  - Live 60 FPS Telemetry Plotting (PyQtGraph)   - SQLite Patient DB     │
│  - Actuator & Sensor Control (Start/Stop/Tare)  - Session History Replay│
└────────────────────────────────────▲────────────────────────────────────┘
                                     │ USB Serial (115200 Baud / 28B Packets)
┌────────────────────────────────────▼────────────────────────────────────┐
│                    Embedded Firmware (STM32F401RE)                      │
│  - 10ms Real-Time Control Scheduler             - Load Cell Force API   │
│  - TIM2 4X Encoder Kinematics (0.15° Res)       - MAX30102 SpO2 Vitals  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                Project Tracker Web Application (Flask/Docker)           │
│  - Agile Sprint & Task Management               - BOM & CAD Step Viewer │
│  - Password-Protected Workspace Portal          - Automated PPTX Deck   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Directory Structure

```text
squish-therapy/
├── README.md               # System architecture & technical documentation
├── .gitignore              # Git ignore rules for builds, database, & virtualenvs
├── run.sh                  # Top-level execution manager (GUI launcher & firmware flags)
├── firmware/               # Embedded C firmware (STM32F401RE / PlatformIO / CubeMX)
│   ├── platformio.ini      # Build environments, board targets, and framework settings
│   ├── encoder.ioc         # STM32CubeMX peripheral pinout & clock tree configuration
│   ├── monitor_binary.py   # CLI serial telemetry monitor & packet verifier
│   └── Core/
│       ├── Inc/            # Subsystem driver header files
│       │   ├── main.h      # CubeMX system definitions and HAL handles
│       │   ├── encoder.h   # Quadrature kinematics & 40ms EMA velocity filter API
│       │   ├── load_cell.h # Handle force acquisition, calibration & tare API
│       │   ├── motor.h     # Torque actuator driver HAL API
│       │   ├── spo2.h      # Pulse oximeter & heart rate biometric API
│       │   └── telemetry.h # 28-byte binary packet packing, CRC-16, & parser API
│       └── Src/
│           ├── main.c      # Executive state machine (IDLE/STREAMING) & 10ms control loop
│           ├── encoder.c   # TIM2 4X hardware decoding & windowed EMA filter
│           ├── load_cell.c # Load cell sensor driver implementation
│           ├── motor.c     # Torque actuator driver implementation
│           ├── spo2.c      # SpO2 pulse oximeter driver implementation
│           └── telemetry.c # Non-blocking UART parser, CRC-16, & transmitter
├── gui/                    # Desktop Rehabilitation Monitoring Application (PySide6)
│   ├── main.py             # Qt Application entry point, window routing, & dark theme
│   ├── database.py         # SQLite data access layer & patient history schema
│   ├── hardware_interface.py# Non-blocking Qt serial thread for 28-byte CRC-16 packets
│   ├── simulation.py       # Algorithmic sensor data generator for offline testing
│   ├── theme.py            # Global dark palette styling tokens & custom Qt widgets
│   ├── utils.py            # Shared utility functions and formatting helpers
│   ├── requirements.txt    # Python desktop dependencies (PySide6, pyqtgraph, pyserial)
│   ├── setup.sh            # Virtual environment initialization script
│   ├── run.sh              # Desktop GUI execution script
│   ├── data/
│   │   └── rehab_test.db   # Local SQLite database storing patients & workout sessions
│   └── screens/            # Application views
│       ├── client_dashboard.py # Active patient profile & quick session launch
│       ├── client_list.py      # Patient roster management & search
│       ├── create_client.py    # New patient registration form
│       ├── history_viewer.py   # Session replay, metrics analytics, & CSV export
│       └── live_test.py        # Real-time 60 FPS plotting & hardware control interface
└── tracker/                # Team Management & Planning Web Application (Flask)
    ├── app.py              # Flask server, password authentication, & API routes
    ├── tracker_core.py     # Task state, BOM management, & labor calculation engine
    ├── pptx_export.py      # Automated PowerPoint slide deck generator
    ├── Dockerfile          # Multi-stage production container build recipe
    ├── docker-compose.yml  # Container service definition & volume mapping
    ├── requirements.txt    # Web dependencies (Flask, openpyxl, python-pptx, gunicorn)
    ├── data/               # Persistent JSON storage (tasks, BOM, CAD versions)
    ├── static/             # CSS stylesheets, JS modules, & Three.js 3D CAD viewer
    └── templates/          # Jinja2 HTML templates (Tasks, BOM, CAD, Slides, Login)
```

---

## Firmware Architecture ([firmware/](file:///home/jpetty/squish-therapy/firmware))

The embedded firmware runs on an **STM32F401RE Nucleo** board, structured around an executive state machine and encapsulated subsystem drivers.

### Module Responsibilities

| Module | Files | Responsibility |
| :--- | :--- | :--- |
| **Executive** | `main.c` | Top-level state machine (`IDLE`, `STREAMING`), subsystem initialization, and 10ms periodic control scheduler. |
| **Encoder** | `encoder.c`, `encoder.h` | TIM2 4X hardware decoding, $0.15^\circ$ resolution, 40ms circular windowed velocity filter, and EMA low-pass filtering. |
| **Telemetry** | `telemetry.c`, `telemetry.h` | Non-blocking command parsing (`START`, `STOP`, `ZERO`, `STATUS`), CRC-16-CCITT integrity checks, and 28-byte packed binary packet transmission. |
| **Load Cell** | `load_cell.c`, `load_cell.h` | Calibration, tare offsets, and instantaneous handle contact force acquisition (lbs / Newtons). |
| **Torque Actuator** | `motor.c`, `motor.h` | Isotonic resistance torque commands, actuator effort feedback, and emergency braking HAL. |
| **SpO2 Vitals** | `spo2.c`, `spo2.h` | Blood oxygen saturation (%) and heart rate (BPM) biometric acquisition via I2C (MAX30102). |

---

## Desktop Clinical GUI ([gui/](file:///home/jpetty/squish-therapy/gui))

The desktop monitoring application is built in Python using **PySide6** and **PyQtGraph**. It provides clinicians with real-time feedback during exercise sessions and persists patient historical data locally in SQLite.

### Key Capabilities

- **Real-Time 60 FPS Telemetry:** Multi-channel live graph displaying elbow angle ($^\circ$), angular velocity ($^\circ/\text{s}$), grip force ($\text{lbs}$), and SpO2 / heart rate vitals.
- **Non-Blocking Serial Engine (`hardware_interface.py`):** Runs on a dedicated Qt background thread to ingest 100 Hz binary telemetry packets, verify CRC-16 checksums, and emit Qt signals to update UI plots without frame drops.
- **Hardware Controls:** Direct software triggers for sensor zeroing, load cell taring, session start/stop streaming, and resistance commands.
- **Patient Database (`database.py`):** Local SQLite storage (`rehab_test.db`) managing patient metadata, test session history, and peak performance metrics.
- **Offline Simulation Mode (`simulation.py`):** Algorithmic telemetry generator allowing UI testing and feature development without physical STM32 hardware attached.

---

## Project Tracker Web Application ([tracker/](file:///home/jpetty/squish-therapy/tracker))

A containerized Flask web application providing the team with centralized sprint planning, Bill of Materials (BOM) tracking, CAD assembly version management, and automated slide generation.

### Key Features

- **Password Protection:** Secure workspace authentication guarding team management data.
- **Interactive Gantt & Task Planning:** Tracks task statuses, owners, labor hours, and milestone schedules.
- **BOM & Inventory Management:** Part numbers, supplier links, pricing, and cost accumulation.
- **CAD Version Viewer:** Integrated Three.js 3D canvas for reviewing STEP models directly in the web browser.
- **Automated PPTX Generation:** Exports formatted slide decks summarizing labor status and project milestones directly for team reviews.

---

## Quick Start Guide

### 1. Unified Launcher (Root Directory)

The top-level [`run.sh`](file:///home/jpetty/squish-therapy/run.sh) script handles GUI execution and firmware flashing automatically:

```bash
# Launch the Desktop GUI (default)
./run.sh

# Build & flash STM32 firmware over ST-Link USB, then launch GUI
./run.sh --flash    # (or ./run.sh -f)

# Compile-check firmware only (PlatformIO)
./run.sh --build-fw # (or ./run.sh -b)
```

### 2. Desktop GUI (Manual Startup)

```bash
cd gui

# First-time setup (creates virtual environment and installs dependencies)
./setup.sh

# Launch application
./run.sh
```

### 3. Firmware Compilation & Flashing

```bash
cd firmware

# Build firmware binary
pio run

# Upload to STM32F401RE Nucleo board via ST-Link
pio run -t upload
```

### 4. CLI Telemetry Monitor

To verify raw binary packets directly over USB serial without running the GUI:

```bash
./firmware/monitor_binary.py
```

### 5. Project Tracker Container (Docker)

```bash
cd tracker

# Build and start container in detached mode
docker compose up -d --build
```
