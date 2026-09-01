# 🦾 Physical Rehabilitation Software Suite (Capstone Project)

Welcome to the official repository for the **Physical Rehabilitation System Capstone Project**. This repository contains the complete software stack—including high-speed embedded microcontroller firmware for bio-feedback sensor decoding and a real-time Qt desktop graphical interface (GUI) for client management and analytics.

---

## 📐 System Architecture Overview

```mermaid
graph TD;
    SubGraph1["Embedded Hardware / Sensors"] -->|High-Speed Quadrature Signal| Hardware["LM324 Schmitt Trigger Conditioning"]
    Hardware -->|Port Manipulation / Interrupts| Firmware["Arduino Microcontroller (Firmware)"]
    Firmware -->|USB / Serial Protocol (115200 Baud)| DesktopGUI["PySide6 / PyQtGraph Desktop GUI"]
    DesktopGUI -->|CRUD Operations| Database[("SQLite Local Database (rehab_test.db)")]
    DesktopGUI -->|Real-Time Rendering| Dashboard["Client & Live Session Dashboard"]
```

---

## 📁 Repository Structure

```text
capstone/
├── README.md               # Project overview & documentation
├── .gitignore              # Git ignore rules for Python & build artifacts
├── firmware/               # Microcontroller / Embedded Systems Code
│   └── encoder/
│       └── test_encoder.cpp # High-speed 4X optical quadrature encoder decoder
└── gui/                    # Rehabilitation Test & Monitoring Desktop Application
    ├── main.py             # Qt Application Entrypoint & Navigation
    ├── database.py         # SQLite Data Access Layer
    ├── simulation.py       # Live & Historical Test Session Generators
    ├── theme.py            # Styling & Color Palette Tokens
    ├── utils.py            # Helper Functions & Formatting
    ├── requirements.txt    # Python Dependencies
    ├── setup.sh            # Automated Linux/WSL Environment Installer
    ├── run.sh              # One-Click Application Launcher
    ├── data/               # Persistent Data Storage
    │   └── rehab_test.db   # SQLite Database File
    └── screens/            # Application Screens & Views
        ├── client_dashboard.py
        ├── client_list.py
        ├── create_client.py
        ├── history_viewer.py
        └── live_test.py
```

---

## ⚡ Firmware Subsystem (`firmware/`)

The firmware directory contains low-level C++ drivers for sensor decoding and data acquisition.

### 🔬 Optical Encoder Reader (`firmware/encoder/test_encoder.cpp`)
* **Resolution:** 2400 Counts Per Revolution (CPR) ($0.15^\circ$ angular resolution).
* **Signal Conditioning:** Pre-filtered via LM324 Schmitt Triggers to eliminate contact bounce and optical noise.
* **Performance:** Implements **Direct AVR Port Manipulation (`PIND`)** and a 16-state quadrature state-lookup table inside hardware interrupt handlers (`CHANGE`) for sub-microsecond, zero-latency 4X state decoding.
* **Baud Rate:** `115200` bps.

---

## 💻 Graphical Interface Subsystem (`gui/`)

The GUI provides clinicians with real-time feedback, interactive graphing, and historical progression tracking for rehabilitation patients.

### 🚀 Quick Start (Setup & Execution)

#### 1. Automated Setup (Recommended)
From the root of the repository, execute the automated environment builder:
```bash
cd gui
chmod +x setup.sh run.sh
./setup.sh
```

#### 2. Running the Application
Launch the GUI using the quick-run script:
```bash
./run.sh
```
*Or manually activate the virtual environment:*
```bash
source ~/.virtualenvs/rehab_gui/bin/activate
python3 main.py
```

---

## 🛠️ Stack & Dependencies
* **Language:** Python 3.10+ / C++ (AVR-GCC / Arduino)
* **GUI Framework:** PySide6 (Qt for Python)
* **Real-time Plotting:** PyQtGraph & NumPy
* **Database:** SQLite3
