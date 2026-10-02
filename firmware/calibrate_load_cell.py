#!/home/jpetty/.virtualenvs/rehab_gui/bin/python3
"""
Load Cell Calibration Tool for NAU7802 on STM32F411
Calculates exact calibration factor (counts per lb or kg) using a 2-point measurement.
"""

import sys
import time
import struct
import glob

try:
    import serial
except ImportError:
    print("Error: pyserial is required. Run in rehab_gui virtualenv.")
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


def read_average_load(ser, sample_count=50):
    samples = []
    buf = bytearray()
    ser.reset_input_buffer()
    ser.write(b"START\r\n")

    start_time = time.time()
    while len(samples) < sample_count and (time.time() - start_time) < 5.0:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)

        while len(buf) >= 28:
            idx = buf.find(b"\xAA\x55")
            if idx == -1:
                del buf[:-1]
                break
            if idx > 0:
                del buf[:idx]
            if len(buf) < 28:
                break

            pkt = bytes(buf[:28])
            del buf[:28]

            expected_crc = struct.unpack("<H", pkt[-2:])[0]
            if compute_crc16(pkt[:-2]) == expected_crc:
                _, _, t_ms, angle, vel, load, iq, spo2, crc = struct.unpack("<BB I f f f f f H", pkt)
                samples.append(load)
            else:
                buf.insert(0, pkt[1])

    ser.write(b"STOP\r\n")
    if not samples:
        raise RuntimeError("No telemetry packets received. Is the firmware streaming?")
    return sum(samples) / len(samples)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("No STM32 serial port found (/dev/ttyACM*)")
        sys.exit(1)

    print("==================================================")
    print(" NAU7802 24-Bit ADC Load Cell Calibration Tool")
    print("==================================================")
    print(f"Connecting to {port}...")
    ser = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(0.3)

    try:
        # Step 1: Baseline / Tare
        input("\n[Step 1] Ensure NO weight/force is on the load cell.\nPress [Enter] to tare and measure baseline...")
        print("Sampling baseline (50 packets)...")
        baseline_nominal = read_average_load(ser, sample_count=50)
        # Convert back from current nominal scale (1/15000) to raw ADC delta
        baseline_raw_delta = baseline_nominal * 15000.0
        print(f"Baseline raw delta: {baseline_raw_delta:.1f}")

        # Step 2: Loaded measurement
        weight_str = input("\n[Step 2] What weight are you placing on the load cell? (e.g. 1.0 or 5.0): ").strip()
        unit_str = input("What unit? [lb / kg] (default: lb): ").strip().lower() or "lb"
        known_weight = float(weight_str)

        input(f"\nPlace the {known_weight} {unit_str} weight on the load cell.\nPress [Enter] when stable...")
        print("Sampling loaded weight (50 packets)...")
        loaded_nominal = read_average_load(ser, sample_count=50)
        loaded_raw_delta = loaded_nominal * 15000.0
        print(f"Loaded raw delta: {loaded_raw_delta:.1f}")

        # Step 3: Compute
        delta_counts = abs(loaded_raw_delta - baseline_raw_delta)
        if delta_counts < 100:
            print("\n[WARNING] Measured count difference is very small. Did you apply force?")
            return

        counts_per_unit = delta_counts / known_weight
        cal_scale = 1.0 / counts_per_unit

        print("\n" + "=" * 50)
        print("CALIBRATION RESULTS:")
        print("=" * 50)
        print(f"Target Unit        : {unit_str}")
        print(f"Delta Raw Counts   : {delta_counts:.1f} counts")
        print(f"Counts per {unit_str}    : {counts_per_unit:.2f} counts/{unit_str}")
        print(f"Scale Factor       : {cal_scale:.8f} (or 1.0f / {counts_per_unit:.1f}f)")
        print("\nTo apply this to firmware:")
        print(f"Update Core/Src/load_cell.c line 48 with:")
        print(f"    static float s_cal_scale = (1.0f / {counts_per_unit:.1f}f); /* {unit_str} */")
        print("=" * 50)

    except KeyboardInterrupt:
        print("\nCalibration cancelled.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
