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

## Hardware Architecture

- **Microcontroller:** STM32F401RE Nucleo
- **Encoder Interface:** 
  - Phase A: `PA0` (TIM2_CH1)
  - Phase B: `PA1` (TIM2_CH2)
  - Mode: 4X Hardware Quadrature Counter (`__HAL_TIM_GET_COUNTER`)
- **Telemetry Stream:** 100 Hz binary packets over ST-Link USB CDC-ACM at 115200 baud
- **Packet Structure (24 Bytes):**
  - Magic Header: `0xAA 0x55`
  - Payload: Timestamp (`uint32`), Joint Angle (`float`), Angular Velocity (`float`), Handle Force (`float`), Motor Current Iq (`float`)
  - Checksum: CRC-16-CCITT across header and payload

---

## Quick Start

### 1. Desktop GUI (Laptop)

Requires Python 3.10+ (dependencies: `PySide6`, `pyqtgraph`, `pyserial`, `numpy`).

```bash
cd gui

# First-time setup (creates virtual environment and installs dependencies)
./setup.sh

# Run the app
./run.sh
```

### 2. Firmware (STM32F401RE)

Built and uploaded using PlatformIO with the STM32Cube framework:

```bash
cd firmware/encoder

# Build and flash via USB ST-Link
~/.platformio/penv/bin/pio run -t upload
```

### 3. CLI Telemetry Monitor

To verify live sensor packets in the terminal without opening the full GUI:

```bash
./firmware/encoder/monitor_binary.py
```
