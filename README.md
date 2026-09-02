# Squish Therapy: FlexSense

## Overview

The **FlexSense** is a comprehensive physical rehabilitation and bio-feedback platform developed as a Senior Capstone Project by Squish Therapy Systems. The system integrates the custom FlexSense hardware sensor device with a real-time desktop graphical user interface (GUI) designed for clinical monitoring, data analytics, and patient progress tracking.

The architecture is divided into two primary subsystems:
1. **Firmware (`firmware/`)**: High-performance microcontroller software for zero-latency sensor decoding.
2. **Graphical Interface (`gui/`)**: A PySide6 desktop application for real-time visualization and historical database management.

## System Architecture

The software suite operates over a 115200 baud serial connection, translating raw mechanical input into clinical metrics.

- **Hardware Layer**: Utilizes an LM324 Schmitt Trigger for signal conditioning to eliminate optical noise and hardware bounce.
- **Embedded Layer**: STM32 C++ implementations utilizing direct port manipulation (`GPIOA->IDR`) and interrupt-driven state machines for 4X quadrature optical encoder decoding (2400 CPR).
- **Application Layer**: Python-based Qt interface utilizing PyQtGraph for hardware-accelerated rendering and SQLite for persistent, localized storage of patient records.

## Directory Structure

```text
squish-therapy/
├── README.md               # Technical documentation and setup guide
├── .gitignore              # Ignored build artifacts and environments
├── firmware/               # Embedded systems and microcontroller code
│   └── encoder/
│       └── test_encoder.cpp # High-speed 4X optical encoder decoding firmware
└── gui/                    # Rehabilitation Test Desktop Application
    ├── main.py             # Qt Application entry point
    ├── database.py         # SQLite data access layer and schema
    ├── simulation.py       # Algorithmic test session data generation
    ├── theme.py            # Global UI styling tokens
    ├── utils.py            # Shared utility functions
    ├── requirements.txt    # Python package dependencies
    ├── setup.sh            # Environment initialization script
    ├── run.sh              # Application execution script
    ├── data/               # Local database storage
    │   └── rehab_test.db   # SQLite patient database
    └── screens/            # Application views and routing
        ├── client_dashboard.py
        ├── client_list.py
        ├── create_client.py
        ├── history_viewer.py
        └── live_test.py
```

## Installation & Deployment

### Prerequisites
- Python 3.10 or higher
- Linux/Unix environment (WSL supported)
- STM32CubeIDE / Arduino IDE with STM32duino (for firmware deployment)

### Application Setup

The graphical interface can be initialized and executed via the provided shell scripts:

1. **Initialize the Environment**:
   Executes the dependency installation and establishes a local virtual environment.
   ```bash
   cd gui
   chmod +x setup.sh run.sh
   ./setup.sh
   ```

2. **Launch the Application**:
   ```bash
   ./run.sh
   ```

Alternatively, the application can be executed manually:
```bash
source ~/.virtualenvs/rehab_gui/bin/activate
python3 main.py
```
