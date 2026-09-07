#!/home/jpetty/.virtualenvs/rehab_gui/bin/python3
"""
Texas A&M University
Electronic Systems Engineering Technology
ESET-469 Embedded Real Time Software Development
Author: Squish Therapy
File: monitor_binary.py
--------
Command-line terminal monitor for decoding and displaying live 100 Hz
24-byte binary telemetry packets from the STM32F401RE FlexSense encoder.
"""

import sys
import time
import struct
import glob

try:
    import serial
except ImportError:
    print("Error: pyserial is required.")
    print("Run using the GUI virtualenv:")
    print(f"  ~/.virtualenvs/rehab_gui/bin/python3 {sys.argv[0]}")
    print("Or activate the environment first:")
    print("  source ~/.virtualenvs/rehab_gui/bin/activate")
    sys.exit(1)


def compute_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def find_port():
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    return ports[0] if ports else None


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(f"Usage: {sys.argv[0]} [serial_port]")
        print("Example: ./monitor_binary.py /dev/ttyACM0")
        sys.exit(0)

    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("No STM32 serial port found (/dev/ttyACM*)")
        sys.exit(1)

    print(f"Opening {port} at 115200 baud...")
    ser = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(0.2)
    ser.reset_input_buffer()

    # Send START
    ser.write(b"START\r\n")
    print("Sent START. Streaming binary packets (Press Ctrl+C to stop)...\n")
    print(f"{'Time (ms)':<10} {'Angle (deg)':<14} {'Velocity (deg/s)':<18} {'Load':<8} {'Iq (A)':<8} {'CRC':<8}")
    print("-" * 70)

    buf = bytearray()
    try:
        while True:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf.extend(chunk)

            while len(buf) >= 24:
                idx = buf.find(b"\xAA\x55")
                if idx == -1:
                    del buf[:-1]
                    break
                if idx > 0:
                    del buf[:idx]
                if len(buf) < 24:
                    break

                pkt = bytes(buf[:24])
                del buf[:24]

                expected_crc = struct.unpack("<H", pkt[-2:])[0]
                if compute_crc16(pkt[:-2]) == expected_crc:
                    _, _, t_ms, angle, vel, load, iq, crc = struct.unpack("<BB I f f f f H", pkt)
                    print(f"{t_ms:<10} {angle:<14.2f} {vel:<18.1f} {load:<8.1f} {iq:<8.1f} {hex(crc):<8}")
                else:
                    buf.insert(0, pkt[1])
    except KeyboardInterrupt:
        print("\nStopping stream...")
        ser.write(b"STOP\r\n")
        time.sleep(0.1)
        ser.close()
        print("Done.")


if __name__ == "__main__":
    main()
