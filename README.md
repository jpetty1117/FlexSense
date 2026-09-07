# FlexSense

FlexSense is an active physical therapy and rehabilitation device for upper-limb strength training (specifically bicep curls). The machine uses a motor to impose controlled resistance torques on the user while logging biomechanical and physiological telemetry in real time to a desktop GUI on a connected laptop.

---

## System Overview

The benchtop test device integrates mechanical resistance actuation with multi-modal patient monitoring:

1. **Active Torque Actuation (Motor / FOC):**
   Imposes programmable resistive torque on the exercise arm against the patient's bicep curl motion.
2. **Handle Force Sensing (Load Cell):**
   A load cell mounted at the user grip handle measures the physical force exerted by the user throughout the curl.
3. **Range of Motion & Kinematics (Rotary Encoder):**
   A 600 PPR optical quadrature encoder (2400 CPR at 4X mode) on the pivot axis measures instantaneous elbow joint angle (degrees) and angular velocity (deg/s).
4. **Biometric Monitoring (SpO2 Finger Sensor):**
   A pulse oximeter finger sensor monitors patient blood oxygen saturation and pulse rate during the workout to guard against clinical overexertion.
5. **Desktop Clinical GUI (Laptop):**
   A PySide6/PyQtGraph application connected over USB serial that handles live 60 FPS plotting, session controls (Start / Stop / Zero / Tare), patient profiles, and SQLite test logging.

---

## Firmware Architecture ([firmware/](file:///home/jpetty/squish-therapy/firmware))

The embedded firmware runs on an **STM32F401RE Nucleo** board, structured around an executive state machine and encapsulated subsystem drivers complying with **Texas A&M ESET-469 Rev 3.0** coding standards.

### Directory Layout

```
firmware/
├── platformio.ini          # PlatformIO build and flash configuration
├── encoder.ioc             # STM32CubeMX peripheral & clock tree configuration
├── .mxproject              # CubeMX project metadata
├── monitor_binary.py       # Terminal CLI telemetry monitor
├── Core/
│   ├── Inc/
│   │   ├── main.h          # CubeMX system definitions and HAL handles
│   │   ├── encoder.h       # Rotary encoder kinematics & velocity filter API
│   │   ├── telemetry.h     # 24-byte packed binary packet, CRC-16, command parser API
│   │   ├── load_cell.h     # Handle load cell force acquisition & tare API
│   │   ├── motor.h         # Motor resistance torque & FOC current API
│   │   └── spo2.h          # Pulse oximeter & heart rate biometric API
│   └── Src/
│       ├── main.c          # Executive state machine & 10ms real-time control loop
│       ├── encoder.c       # TIM2 4X quadrature decoder, 40ms sliding window EMA filter
│       ├── telemetry.c     # Non-blocking UART command parser, CRC-16, binary transmitter
│       ├── load_cell.c     # Handle load cell driver skeleton
│       ├── motor.c         # Motor resistance torque driver skeleton
│       └── spo2.c          # SpO2 pulse oximeter driver skeleton
└── Drivers/                # STM32 HAL and CMSIS library drivers
```

### Module Responsibilities

| Module | Files | Responsibility |
| :--- | :--- | :--- |
| **Executive** | `main.c` | Top-level state machine (`IDLE`, `STREAMING`), subsystem initialization, and 10ms periodic control scheduler. |
| **Encoder** | `encoder.c`, `encoder.h` | TIM2 4X hardware decoding, $0.15^\circ$ resolution, 40ms circular windowed velocity filter, and EMA low-pass filtering. |
| **Telemetry** | `telemetry.c`, `telemetry.h` | Non-blocking command parsing (`START`, `STOP`, `ZERO`, `STATUS`), CRC-16-CCITT integrity checks, and 24-byte packed binary packet transmission. |
| **Load Cell** | `load_cell.c`, `load_cell.h` | Calibration, tare offsets, and instantaneous handle contact force acquisition (lbs / Newtons). |
| **Motor Drive** | `motor.c`, `motor.h` | Isotonic resistance torque commands, quadrature current feedback ($I_q$), and emergency braking. |
| **SpO2 Vitals** | `spo2.c`, `spo2.h` | Blood oxygen saturation (%) and heart rate (BPM) biometric acquisition via I2C (MAX30102). |

### CubeMX & PlatformIO Integration

- **STM32CubeMX:** Used for pinout, clock tree, and peripheral HAL generation (`encoder.ioc`). Custom files in `Core/Inc` and `Core/Src` are preserved across code re-generations.
- **PlatformIO:** Automatically compiles all `.c` files in `Core/Src` and includes `Core/Inc`. No separate file list configuration is needed.

---

## Quick Start

### Unified Runner (Root Directory)

The top-level [`run.sh`](file:///home/jpetty/squish-therapy/run.sh) manages both GUI startup and firmware flashing:

```bash
# Launch the Desktop GUI immediately (default)
./run.sh

# Build & flash STM32 firmware over ST-Link USB, then launch GUI
./run.sh --flash    # (or ./run.sh -f)

# Compile-check firmware only (PlatformIO)
./run.sh --build-fw # (or ./run.sh -b)
```

### 1. Desktop GUI (Manual / Subdirectory)

Requires Python 3.10+ (dependencies: `PySide6`, `pyqtgraph`, `pyserial`, `numpy`).

```bash
cd gui

# First-time setup (creates virtual environment and installs dependencies)
./setup.sh

# Run the app directly
./run.sh
```

### 2. Firmware (STM32F401RE)

Built and uploaded using PlatformIO with the STM32Cube framework:

```bash
cd firmware

# Build firmware
~/.platformio/penv/bin/pio run

# Flash to Nucleo board via ST-Link USB
~/.platformio/penv/bin/pio run -t upload
```

### 3. CLI Telemetry Monitor

To verify live sensor packets in the terminal without opening the full GUI:

```bash
./firmware/monitor_binary.py
```
