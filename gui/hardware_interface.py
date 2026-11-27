"""
Texas A&M University
Electronic Systems Engineering Technology
ESET-469 Embedded Real Time Software Development
Author: Squish Therapy
File: hardware_interface.py
--------
USB serial interface and sliding-window binary telemetry parser
for the STM32F401RE FlexSense encoder subsystem.
"""

import os
import json
import time
import glob
import struct

try:
    import serial
except ImportError:
    serial = None

CALIBRATION_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calibration"))
DEV_CONFIG_PATH = os.path.join(CALIBRATION_DIR, "dev_config.json")
DEFAULT_DEV_CONFIG = {
    "run_curr_ma": 1500,
    "homing_curr_ma": 800,
    "homing_speed_us": 350,
    "homing_slack_mm": 30.0,
    "dir_inverted": True,
}


def load_dev_config() -> dict:
    """Load persistent Dev & Calibration parameters shared with Live Test."""
    cfg = dict(DEFAULT_DEV_CONFIG)
    try:
        if os.path.exists(DEV_CONFIG_PATH):
            with open(DEV_CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k in cfg:
                    if k in raw:
                        cfg[k] = raw[k]
    except Exception:
        pass
    return cfg


def save_dev_config(updates: dict) -> dict:
    """Merge and persist Dev & Calibration parameters to calibration/dev_config.json."""
    cfg = load_dev_config()
    for k, v in updates.items():
        if k in DEFAULT_DEV_CONFIG:
            cfg[k] = v
    try:
        os.makedirs(CALIBRATION_DIR, exist_ok=True)
        with open(DEV_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    return cfg


def compute_crc16(data: bytes) -> int:
    """
    Compute CRC-16-CCITT (poly 0x1021, init 0xFFFF). Matches STM32 firmware.

    Parameters:
        data (bytes): Input byte sequence to checksum.

    Returns:
        int: Calculated 16-bit CRC checksum.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class STM32EncoderInterface:
    """Manages serial communication and binary packet framing with the STM32."""

    PACKET_PREAMBLE = b"\xAA\x55"
    PACKET_SIZE = 28  # 2 preamble + 4 time + 4 angle + 4 vel + 4 load + 4 iq + 4 spo2 + 2 crc
    PACKET_FORMAT = "<BB I f f f f f H"

    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.is_connected = False
        self.is_streaming = False
        self.auto_reconnect = True
        self._last_reconnect_attempt = 0.0

        self.rx_buffer = bytearray()
        self.rx_text_lines = []
        self.packets_received = 0
        self.crc_errors = 0

        self.last_timestamp_ms = 0
        self.last_angle = 0.0
        self.last_velocity = 0.0
        self.last_load_cell = 0.0
        self.last_motor_iq = 0.0
        self.last_spo2 = 98.0

    @staticmethod
    def find_serial_port():
        """Auto-detect ST-Link Virtual COM Port."""
        acm_ports = glob.glob("/dev/ttyACM*")
        if acm_ports:
            return acm_ports[0]
        usb_ports = glob.glob("/dev/ttyUSB*")
        if usb_ports:
            return usb_ports[0]
        return None

    def connect(self, port=None):
        """Open the serial connection."""
        if serial is None:
            return False, "pyserial is not installed"

        target_port = port or self.port or self.find_serial_port()
        if not target_port:
            return False, "No serial port found (/dev/ttyACM*)"

        # Avoid reopening if already connected and open on the target port
        if self.ser and self.ser.is_open and self.is_connected and (self.port == target_port):
            return True, f"Already connected to {target_port}"

        # Cleanly close previous handle if open
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass

        try:
            self.ser = serial.Serial(target_port, self.baudrate, timeout=0.05)
            self.ser.dtr = True
            self.ser.rts = True
            self.port = target_port
            self.is_connected = True
            self.rx_buffer.clear()
            self.rx_text_lines.clear()
            self.packets_received = 0
            self.crc_errors = 0
            time.sleep(0.05)
            self.ser.reset_input_buffer()
            # Send STOP to ensure it starts in IDLE, then sync shared Dev settings
            self.send_command("STOP")
            time.sleep(0.02)
            self.apply_dev_config()
            return True, f"Connected to {target_port}"
        except Exception as e:
            self.is_connected = False
            self.ser = None
            return False, f"Connection failed: {e}"

    def disconnect(self):
        """Close serial connection and reset interface state."""
        if self.ser:
            try:
                if self.ser.is_open:
                    self.send_command("STOP")
            except Exception:
                pass
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.is_connected = False
        self.is_streaming = False
        self.rx_buffer.clear()
        self.rx_text_lines.clear()

    def send_command(self, cmd):
        """Send an ASCII text command (e.g. 'START', 'STOP', 'ZERO', 'RES 10.0', '?') to the STM32."""
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write((cmd.strip() + "\r\n").encode("ascii"))
            self.ser.flush()
            return True
        except Exception:
            return False

    def set_resistance(self, resistance_lbs: float) -> bool:
        """
        Send commanded resistance to the STM32 Series Elastic Actuator controller.

        Parameters:
            resistance_lbs (float): Target brake resistance in pounds (0.0 to 25.0 lbf).

        Returns:
            bool: True if transmitted successfully.
        """
        if not self.is_connected:
            return False
        return self.send_command(f"RES {float(resistance_lbs):.2f}")

    def set_driver_current(self, current_a: float = 1.5) -> bool:
        """
        Configure TMC2209 coil current limit over UART (e.g. 1.5 A or 1500 mA).

        Parameters:
            current_a (float): Current limit in Amperes (e.g. 1.5) or mA (1500).

        Returns:
            bool: True if transmitted successfully.
        """
        if not self.is_connected:
            return False
        ma = int(current_a * 1000) if current_a < 10.0 else int(current_a)
        return self.send_command(f"CURR {ma}")

    def apply_dev_config(self, cfg: dict = None) -> bool:
        """Apply shared Dev & Calibration settings to the MCU so Dev and Live Test stay in sync."""
        if not self.is_connected:
            return False
        c = cfg if cfg is not None else load_dev_config()
        self.send_command(f"CURR {int(c['run_curr_ma'])}")
        self.send_command(f"HOMECURR {int(c['homing_curr_ma'])}")
        self.send_command(f"HOMESPEED {int(c['homing_speed_us'])}")
        self.send_command(f"HOMESLACK {float(c['homing_slack_mm']):.1f}")
        self.send_command(f"DIR {1 if c['dir_inverted'] else 0}")
        return True

    def start_streaming(self, target_resistance: float = None):
        """Zero/tare via START, configure resistance, and begin 100 Hz binary telemetry stream."""
        if not self.is_connected:
            ok, _ = self.connect()
            if not ok:
                return False
        # Clear stale RX bytes before starting, without dropping just-sent TX commands (e.g. ARM)
        if self.ser and self.ser.is_open:
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
        self.rx_buffer.clear()
        self.rx_text_lines.clear()
        self.last_timestamp_ms = 0
        if target_resistance is not None:
            self.set_resistance(target_resistance)
        self.send_command("START")
        self.is_streaming = True
        return True

    def stop_streaming(self):
        """Command the STM32 to stop streaming telemetry."""
        if self.is_connected:
            self.send_command("STOP")
            time.sleep(0.02)
            if self.ser and self.ser.is_open:
                try:
                    self.ser.reset_input_buffer()
                except Exception:
                    pass
        self.is_streaming = False
        self.rx_buffer.clear()

    def zero(self):
        """Reset encoder position to 0 and tare load cell."""
        if not self.is_connected:
            self.connect()
        if self.is_connected:
            self.send_command("ZERO")
            self.last_angle = 0.0
            self.last_velocity = 0.0
            self.last_load_cell = 0.0

    def home(self):
        """Execute forward limit switch search and 5 mm standoff on the STM32."""
        if not self.is_connected:
            self.connect()
        if self.is_connected:
            return self.send_command("HOME")
        return False

    def _extract_ascii_from_bytes(self, raw: bytes):
        """Validate and extract complete printable ASCII lines without leaking binary noise."""
        if not raw:
            return
        for raw_line in raw.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if all(32 <= b <= 126 or b == 9 for b in stripped):
                text = stripped.decode("ascii").strip()
                if text and any(c.isalnum() for c in text):
                    self.rx_text_lines.append(text)
                continue
            # Recover a clean ACK/ALERT suffix if pre-sync binary noise preceded it
            for prefix in (b"ACK:", b"ALERT:"):
                pidx = stripped.rfind(prefix)
                if pidx != -1:
                    suffix = stripped[pidx:]
                    if all(32 <= b <= 126 or b == 9 for b in suffix):
                        self.rx_text_lines.append(suffix.decode("ascii").strip())
                        break

    def read_text_lines(self):
        """Return and clear newly arrived ASCII lines from MCU."""
        lines = list(self.rx_text_lines)
        self.rx_text_lines.clear()
        return lines

    def read_samples(self):
        """
        Non-blocking read and unpack of all newly arrived 28-byte binary packets.
        Automatically reconnects if the MCU was reset (NRST) or USB dropped.
        Returns a list of tuples: [(time_ms, ticks, angle_deg, vel_deg_s, load_cell, motor_iq, spo2), ...]
        """
        now = time.time()
        # If disconnected and auto-reconnect is enabled, probe for newly re-enumerated port
        if not self.is_connected or not self.ser or not self.ser.is_open:
            if self.auto_reconnect and (now - self._last_reconnect_attempt > 0.5):
                self._last_reconnect_attempt = now
                detected_port = self.find_serial_port()
                if detected_port:
                    ok, _ = self.connect(detected_port)
                    if ok:
                        # Re-enable streaming so preview & telemetry resume immediately
                        self.send_command("STOP")
                        time.sleep(0.01)
                        self.send_command("START")
                        self.is_streaming = True
                        self.rx_buffer.clear()
            if not self.is_connected or not self.ser:
                return []

        samples = []
        try:
            bytes_waiting = self.ser.in_waiting
            if bytes_waiting > 0:
                chunk = self.ser.read(bytes_waiting)
                if chunk:
                    self.rx_buffer.extend(chunk)

            # Strict left-to-right framing: wait on torn lines/packets, never re-inject parsed bytes
            while self.rx_buffer:
                pkt_idx = self.rx_buffer.find(self.PACKET_PREAMBLE)
                nl_idx = self.rx_buffer.find(b"\n")

                if pkt_idx == -1 and nl_idx == -1:
                    if len(self.rx_buffer) > 512:
                        # Preserve final byte in case 0xAA arrived alone before 0x55
                        del self.rx_buffer[:-1]
                    break

                # Complete '\n'-delimited ASCII line precedes any 0xAA 0x55 packet preamble
                if nl_idx != -1 and (pkt_idx == -1 or nl_idx < pkt_idx):
                    raw_line = bytes(self.rx_buffer[:nl_idx + 1])
                    del self.rx_buffer[:nl_idx + 1]
                    self._extract_ascii_from_bytes(raw_line)
                    continue

                # Misaligned/pre-sync bytes precede 0xAA 0x55 with no '\n'; discard to align packet
                if pkt_idx > 0:
                    del self.rx_buffer[:pkt_idx]
                    continue

                # Preamble 0xAA 0x55 is at index 0: wait for all 28 bytes before unpacking
                if len(self.rx_buffer) < self.PACKET_SIZE:
                    break

                pkt_bytes = bytes(self.rx_buffer[:self.PACKET_SIZE])
                expected_crc = struct.unpack("<H", pkt_bytes[-2:])[0]
                calculated_crc = compute_crc16(pkt_bytes[:-2])

                if calculated_crc == expected_crc:
                    del self.rx_buffer[:self.PACKET_SIZE]
                    self.packets_received += 1
                    p0, p1, t_ms, angle, vel, load, iq, spo2, crc = struct.unpack(
                        self.PACKET_FORMAT, pkt_bytes
                    )

                    self.last_timestamp_ms = t_ms
                    self.last_angle = angle
                    self.last_velocity = vel
                    self.last_load_cell = load
                    self.last_motor_iq = iq
                    self.last_spo2 = spo2

                    samples.append((t_ms, 0, angle, vel, load, iq, spo2))
                else:
                    # CRC error: advance by 1 byte in-place to re-sync past false preamble
                    self.crc_errors += 1
                    del self.rx_buffer[:1]

        except Exception:
            # Device reset (NRST) or USB disconnected: cleanly close file descriptor to allow re-enumeration
            self.disconnect()
            self._last_reconnect_attempt = time.time()

        return samples
