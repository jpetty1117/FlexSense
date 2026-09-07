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

import time
import glob
import struct

try:
    import serial
except ImportError:
    serial = None


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
    PACKET_SIZE = 24  # 2 preamble + 4 time + 4 angle + 4 vel + 4 load + 4 iq + 2 crc
    PACKET_FORMAT = "<BB I f f f f H"

    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.is_connected = False
        self.is_streaming = False

        self.rx_buffer = bytearray()

        self.last_timestamp_ms = 0
        self.last_angle = 0.0
        self.last_velocity = 0.0
        self.last_load_cell = 0.0
        self.last_motor_iq = 0.0

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

        try:
            self.ser = serial.Serial(target_port, self.baudrate, timeout=0.05)
            self.port = target_port
            self.is_connected = True
            self.rx_buffer.clear()
            time.sleep(0.1)
            self.ser.reset_input_buffer()
            # Send STOP to ensure it starts in IDLE
            self.send_command("STOP")
            return True, f"Connected to {target_port}"
        except Exception as e:
            self.is_connected = False
            self.ser = None
            return False, f"Connection failed: {e}"

    def disconnect(self):
        """Close serial connection."""
        if self.ser and self.ser.is_open:
            try:
                self.send_command("STOP")
            except Exception:
                pass
            self.ser.close()
        self.ser = None
        self.is_connected = False
        self.is_streaming = False
        self.rx_buffer.clear()

    def send_command(self, cmd):
        """Send an ASCII text command (e.g. 'START', 'STOP', 'ZERO', '?') to the STM32."""
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write((cmd.strip() + "\r\n").encode("ascii"))
            self.ser.flush()
            return True
        except Exception:
            return False

    def start_streaming(self):
        """Zero the encoder and command the STM32 to begin 50 Hz binary telemetry stream."""
        if not self.is_connected:
            ok, _ = self.connect()
            if not ok:
                return False
        self.rx_buffer.clear()
        self.send_command("ZERO")
        time.sleep(0.02)
        self.send_command("START")
        self.is_streaming = True
        return True

    def stop_streaming(self):
        """Command the STM32 to stop streaming telemetry."""
        if self.is_connected:
            self.send_command("STOP")
        self.is_streaming = False
        self.rx_buffer.clear()

    def zero(self):
        """Reset encoder position to 0."""
        if self.is_connected:
            self.send_command("ZERO")
            self.last_angle = 0.0
            self.last_velocity = 0.0

    def read_samples(self):
        """
        Non-blocking read and unpack of all newly arrived 24-byte binary packets.
        Returns a list of tuples: [(time_ms, ticks, angle_deg, vel_deg_s, load_cell, motor_iq), ...]
        """
        if not self.is_connected or not self.ser:
            return []

        samples = []
        try:
            bytes_waiting = self.ser.in_waiting
            if bytes_waiting > 0:
                chunk = self.ser.read(bytes_waiting)
                if chunk:
                    self.rx_buffer.extend(chunk)

            # Slide window to find 0xAA 0x55 preamble and extract packets
            while len(self.rx_buffer) >= self.PACKET_SIZE:
                idx = self.rx_buffer.find(self.PACKET_PREAMBLE)
                if idx == -1:
                    # Keep last byte in case it's 0xAA of a split preamble
                    del self.rx_buffer[:-1]
                    break

                if idx > 0:
                    # Drop any leading garbage bytes before preamble
                    del self.rx_buffer[:idx]

                if len(self.rx_buffer) < self.PACKET_SIZE:
                    break

                # Extract candidate 24-byte packet
                pkt_bytes = bytes(self.rx_buffer[:self.PACKET_SIZE])
                del self.rx_buffer[:self.PACKET_SIZE]

                # Verify CRC16-CCITT across bytes 0..21
                expected_crc = struct.unpack("<H", pkt_bytes[-2:])[0]
                calculated_crc = compute_crc16(pkt_bytes[:-2])

                if calculated_crc == expected_crc:
                    p0, p1, t_ms, angle, vel, load, iq, crc = struct.unpack(
                        self.PACKET_FORMAT, pkt_bytes
                    )

                    self.last_timestamp_ms = t_ms
                    self.last_angle = angle
                    self.last_velocity = vel
                    self.last_load_cell = load
                    self.last_motor_iq = iq

                    # Return formatted sample tuple
                    samples.append((t_ms, 0, angle, vel, load, iq))
                else:
                    # CRC error: preamble was a false positive, advance by 1 to re-sync
                    self.rx_buffer.insert(0, pkt_bytes[1])

        except Exception:
            self.is_connected = False

        return samples
