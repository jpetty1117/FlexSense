#!/home/jpetty/.virtualenvs/rehab_gui/bin/python3
"""
Load Cell Calibration Tool for NAU7802 on STM32F411
Calculates exact calibration factor (counts per lb or kg) using direct 24-bit raw ADC counts.
"""

import sys
import time
import re
import glob

try:
    import serial
except ImportError:
    print("Error: pyserial is required. Run in rehab_gui virtualenv.")
    sys.exit(1)


def find_port():
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    return ports[0] if ports else None


def read_average_raw(ser, sample_count=30):
    """Query real-time 24-bit raw ADC counts via STATUS command without taring."""
    samples = []
    ser.reset_input_buffer()
    
    start_time = time.time()
    while len(samples) < sample_count and (time.time() - start_time) < 6.0:
        ser.write(b"STATUS\r\n")
        time.sleep(0.04)  # ~25 Hz sampling of raw count
        line = ser.readline().decode("ascii", errors="replace").strip()
        m = re.search(r"RAW=(-?\d+)", line)
        if m:
            raw_val = int(m.group(1))
            samples.append(raw_val)

    if not samples:
        raise RuntimeError("No STATUS responses received. Is the firmware running?")
    return sum(samples) / len(samples)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("No STM32 serial port found (/dev/ttyACM*)")
        sys.exit(1)

    print("==================================================")
    print(" NAU7802 24-Bit ADC Direct Raw Calibration Tool")
    print("==================================================")
    print(f"Connecting to {port}...")
    ser = serial.Serial(port, 115200, timeout=0.2)
    time.sleep(0.3)

    try:
        # Step 1: Baseline / Unloaded Measurement
        input("\n[Step 1] Ensure NO weight/force is on the load cell.\nPress [Enter] to sample unloaded baseline...")
        print("Sampling unloaded baseline (30 raw readings)...")
        baseline_raw = read_average_raw(ser, sample_count=30)
        print(f"Baseline raw count: {baseline_raw:.1f}")

        # Step 2: Loaded Measurement
        weight_str = input("\n[Step 2] What weight are you placing on the load cell? (e.g. 1.0 or 5.0): ").strip()
        unit_str = input("What unit? [lb / kg] (default: lb): ").strip().lower() or "lb"
        known_weight = float(weight_str)

        input(f"\nPlace the {known_weight} {unit_str} weight on the load cell.\nPress [Enter] when stable...")
        print("Sampling loaded weight (30 raw readings)...")
        loaded_raw = read_average_raw(ser, sample_count=30)
        print(f"Loaded raw count  : {loaded_raw:.1f}")

        # Step 3: Compute
        delta_counts = abs(loaded_raw - baseline_raw)
        print(f"Raw delta counts  : {delta_counts:.1f} counts")

        if delta_counts < 100:
            print("\n[WARNING] Measured count difference is very small. Did you apply force or place the weight?")
            return

        counts_per_unit = delta_counts / known_weight
        cal_scale = 1.0 / counts_per_unit

        print("\n" + "=" * 50)
        print("CALIBRATION RESULTS:")
        print("=" * 50)
        print(f"Target Unit        : {unit_str}")
        print(f"Unloaded Baseline  : {baseline_raw:.1f} counts")
        print(f"Loaded Reading     : {loaded_raw:.1f} counts")
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
