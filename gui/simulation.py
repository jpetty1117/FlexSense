"""
Data simulation module for generating live and historical test data.
Modeled around isotonic bicep curl rehabilitation testing.

Bicep curl kinematics:
- ROM: 0° (arm extended) → 160° (fully flexed) → 0°
- One rep period: 1-3 seconds
- Position modeled as raised cosine: θ(t) = (θ_max/2)(1 - cos(2πt/T))
- Velocity = dθ/dt = (πθ_max/T) sin(2πt/T)
  → bell-shaped velocity profile (fast in middle, slow at ends)
"""

import numpy as np
import random
from collections import deque


class LiveDataGenerator:
    """Generates simulated live sensor data for bicep curl isotonic tests."""

    def __init__(self, target_resistance=10.0, target_angle=160.0, freq_range=(1.0, 2.0)):
        # Rep period between 1-3 seconds
        self.rep_period = random.uniform(1.0, 3.0)
        self.target_resistance = target_resistance
        self.target_angle = target_angle   # max ROM in degrees (0 to target_angle)
        self.spo2 = 97.0  # Starting SpO2

        # Injury simulation parameters
        self.injury_angle = random.uniform(50.0, 110.0)
        self.injury_severity = random.uniform(5.0, 12.0)  # Amplitude of the dip
        self.injury_width = random.uniform(12.0, 18.0)    # Width of the dip

    def next_sample(self, t):
        """
        Generate the next data sample at time t (seconds).
        Returns (rom_angle, speed, spo2).
        Strength is constant (isotonic) = target_resistance.
        """
        T = self.rep_period
        omega = 2.0 * np.pi / T

        # Raised cosine: smooth 0 → target_angle → 0
        # θ(t) = (target_angle/2) * (1 - cos(ωt))
        ideal_rom = (self.target_angle / 2.0) * (1.0 - np.cos(omega * t))
        ideal_speed = (self.target_angle / 2.0) * omega * np.sin(omega * t)
        
        # Apply localized injury dip (creates a stall/wobble in ROM, dropping velocity)
        dip = self.injury_severity * np.exp(-((ideal_rom - self.injury_angle)**2) / (2 * self.injury_width**2))
        dip_derivative = -dip * ((ideal_rom - self.injury_angle) / (self.injury_width**2)) * ideal_speed
        
        rom_angle = ideal_rom - dip
        rom_angle += random.gauss(0, 0.3)  # sensor noise

        speed = ideal_speed - dip_derivative
        speed += random.gauss(0, 5.0)  # sensor noise on velocity

        # SpO2: slow random walk, clamped to 94-99%
        self.spo2 += random.gauss(0, 0.05)
        self.spo2 = max(94.0, min(99.0, self.spo2))

        return rom_angle, speed, self.spo2


def generate_historical_session(duration=30.0, sample_rate=50, session_index=0):
    """
    Generate a full historical bicep curl test session of dummy data.

    Args:
        duration: session length in seconds
        sample_rate: samples per second
        session_index: used to vary parameters between sessions

    Returns:
        dict with keys: timestamps, rom_angle, speed, strength, spo2,
                        target_resistance, target_angle
    """
    # Vary parameters per session
    rep_periods = [3, 3.5, 4]  # seconds per rep
    resistances = [8.0, 12.0, 15.0]
    max_roms = [140.0, 155.0, 160.0]  # degrees

    T = rep_periods[session_index % len(rep_periods)]
    target_resistance = resistances[session_index % len(resistances)]
    target_angle = max_roms[session_index % len(max_roms)]

    n_samples = int(duration * sample_rate)
    timestamps = np.linspace(0, duration, n_samples)
    omega = 2.0 * np.pi / T

    # Injury simulation parameters (randomized per session)
    injury_angle = np.random.uniform(50.0, 110.0)
    injury_severity = np.random.uniform(5.0, 12.0)
    injury_width = np.random.uniform(12.0, 18.0)

    # Raised cosine ROM: 0→target_angle→0, bell-shaped velocity
    ideal_rom = (target_angle / 2.0) * (1.0 - np.cos(omega * timestamps))
    ideal_speed = (target_angle / 2.0) * omega * np.sin(omega * timestamps)
    
    # Apply localized injury dip
    dip = injury_severity * np.exp(-((ideal_rom - injury_angle)**2) / (2 * injury_width**2))
    dip_derivative = -dip * ((ideal_rom - injury_angle) / (injury_width**2)) * ideal_speed
    
    rom_angle = ideal_rom - dip
    rom_angle += np.random.normal(0, 0.3, n_samples)  # sensor noise

    speed = ideal_speed - dip_derivative
    speed += np.random.normal(0, 5.0, n_samples)  # sensor noise

    # Strength is constant (isotonic)
    strength = np.full(n_samples, target_resistance)

    # SpO2: slow drift + noise, clamped 94-99%
    base_spo2 = 96.5 + 0.5 * session_index
    spo2_drift = np.cumsum(np.random.normal(0, 0.01, n_samples))
    spo2 = base_spo2 + spo2_drift + np.random.normal(0, 0.1, n_samples)
    spo2 = np.clip(spo2, 94.0, 99.0)

    return {
        "timestamps": timestamps,
        "rom_angle": rom_angle,
        "speed": speed,
        "strength": strength,
        "target_resistance": target_resistance,
        "target_angle": target_angle,
        "spo2": spo2,
    }
