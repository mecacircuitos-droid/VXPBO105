import math
import random
from typing import Any, Dict, Optional

import numpy as np

from .types import BalanceReading, Measurement

BLADES = ["BLU", "GRN", "YEL", "RED"]

# BO105 procedure set (training / simulator)
REGIMES = ["GROUND", "HOVER", "HORIZ"]

REGIME_LABEL = {
    "GROUND": "100% Ground",
    "HOVER": "Hover Flight",
    "HORIZ": "Horizontal Flight",
}

# Clock positions (legacy convention)
BLADE_CLOCK_DEG = {"YEL": 0.0, "RED": 90.0, "BLU": 180.0, "GRN": 270.0}

# BO105 — reference RPM used by the simulator
BO105_DISPLAY_RPM = 424.0

FLATS_PER_TURN = 6.0

# 1 full turn of the pitch link ≈ 10 mm at blade tip
PITCHLINK_MM_PER_TURN = 10.0

# Trim tab: 1 mm bend ≈ 15 mm track change at tip
TRIMTAB_MMTRACK_PER_MM = 15.0

# Balance chart scaling (user-provided)
# 0.5 IPS ≈ 200 g in Ground, 0.5 IPS ≈ 500 g in Hover.
IPS_PER_GRAM = {"GROUND": 0.0025, "HOVER": 0.0010, "HORIZ": 0.0010}

# -----------------------------
# Baseline helicopter condition
# -----------------------------
# Track values are shown as mm relative to YEL (reference blade).
BASE_TRACK = {
    "GROUND": {"BLU": +5.6, "GRN": -2.3, "YEL": 0.0, "RED": -4.4},
    "HOVER": {"BLU": +7.1, "GRN": -3.8, "YEL": 0.0, "RED": -4.7},
    "HORIZ": {"BLU": +4.9, "GRN": -2.3, "YEL": 0.0, "RED": -3.9},
}

# Balance baseline: (amplitude IPS, phase degrees where 0° = 12 o'clock).
# These match the example screenshot values:
#  - GND 0.45 @ 11:30  -> 345°
#  - HOV 0.25 @ 06:00  -> 180°
#  - HOR 0.18 @ 05:00  -> 150°
BASE_BAL = {"GROUND": (0.45, 345.0), "HOVER": (0.25, 180.0), "HORIZ": (0.18, 150.0)}


def default_adjustments() -> Dict[str, Dict[str, Dict[str, float]]]:
    """Global settings (apply to all runs)"""
    return {
        r: {
            "pitch_flats": {b: 0.0 for b in BLADES},
            "trim_mm": {b: 0.0 for b in BLADES},
            "bolt_g": {b: 0.0 for b in BLADES},
        }
        for r in REGIMES
    }


def _vec_from_clock_deg(theta_deg: float) -> np.ndarray:
    phi = math.radians(90.0 - theta_deg)
    return np.array([math.cos(phi), math.sin(phi)], dtype=float)


def _clock_deg_from_vec(v: np.ndarray) -> float:
    x, y = float(v[0]), float(v[1])
    phi = math.degrees(math.atan2(y, x))
    return (90.0 - phi) % 360.0


def _apply_weight_effect_on_hover(track: Dict[str, float], aircraft: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Approximate the note: hover track spread usually increases as gross mass decreases.

    We keep it subtle so it doesn't fight the student's corrections.
    """
    if not aircraft:
        return track
    w = float(aircraft.get("weight", 0.0) or 0.0)
    if w <= 0:
        return track

    # Choose a gentle reference and cap the effect to ±15%.
    ref = 2500.0
    delta = (ref - w) / ref
    factor = 1.0 + max(-0.15, min(0.15, 0.15 * delta))

    out = track.copy()
    # Scale only the non-reference blades (YEL stays 0).
    for b in BLADES:
        if b == "YEL":
            continue
        out[b] = float(out[b] * factor)
    out["YEL"] = 0.0
    return out


def simulate_measurement(run: int, regime: str, adjustments: dict, aircraft: Optional[Dict[str, Any]] = None) -> Measurement:
    """Generate a synthetic measurement.

    Run number is stored for reporting, but the measurement is driven by:
      - baseline helicopter condition (BASE_TRACK / BASE_BAL)
      - current SETTINGS (pitch links / trim tabs / weights)
      - small noise (repeatability)
    """
    adj = adjustments[regime]
    base_track = BASE_TRACK[regime].copy()
    base_amp, base_phase = BASE_BAL[regime]

    # -----------------
    # Track simulation
    # -----------------
    track: Dict[str, float] = {}
    for b in BLADES:
        # Pitch links affect all regimes. Settings are in FLATS; convert to turns.
        turns = float(adj["pitch_flats"][b]) / FLATS_PER_TURN
        pitch_effect = PITCHLINK_MM_PER_TURN * turns

        # Trim tabs affect forward flight mostly, and can slightly influence hover.
        trim_mm = float(adj["trim_mm"][b])
        trim_effect = 0.0
        if regime == "HORIZ":
            trim_effect = TRIMTAB_MMTRACK_PER_MM * trim_mm
        elif regime == "HOVER":
            trim_effect = 0.25 * TRIMTAB_MMTRACK_PER_MM * trim_mm

        noise = random.gauss(0.0, 0.35)
        track[b] = float(base_track[b] + pitch_effect + trim_effect + noise)

    # Normalize: track is always shown relative to YEL
    yel0 = float(track["YEL"])
    for b in BLADES:
        track[b] = float(track[b] - yel0)
    track["YEL"] = 0.0

    if regime == "HOVER":
        track = _apply_weight_effect_on_hover(track, aircraft)

    # -----------------
    # Balance simulation
    # -----------------
    v = _vec_from_clock_deg(base_phase) * float(base_amp)
    k = float(IPS_PER_GRAM.get(regime, IPS_PER_GRAM["GROUND"]))
    for b in BLADES:
        grams = float(adj["bolt_g"][b])
        # Adding weight produces a corrective vector (sign chosen to reduce amp).
        v += (-k * grams) * _vec_from_clock_deg(BLADE_CLOCK_DEG[b])

    v += np.array([random.gauss(0.0, 0.004), random.gauss(0.0, 0.004)], dtype=float)

    amp = float(np.linalg.norm(v))
    phase = float(_clock_deg_from_vec(v)) if amp > 1e-6 else 0.0

    return Measurement(regime=regime, balance=BalanceReading(amp, phase, BO105_DISPLAY_RPM), track_mm=track)
