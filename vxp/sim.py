import math
import random
import numpy as np

from .types import BalanceReading, Measurement

BLADES = ["BLU", "GRN", "YEL", "RED"]

REGIMES = ["GROUND", "HOVER", "HORIZ"]

REGIME_LABEL = {
    "GROUND": "100% Ground",
    "HOVER": "Hover Flight",
    "HORIZ": "Horizontal Flight",
}

# 12 o'clock = 0°, 3 o'clock = 90°, 6 o'clock = 180°, 9 o'clock = 270°
BLADE_CLOCK_DEG = {"YEL": 0.0, "RED": 90.0, "BLU": 180.0, "GRN": 270.0}

BO105_DISPLAY_RPM = 424.0

PITCHLINK_MM_PER_TURN = 10.0
TRIMTAB_MMTRACK_PER_MM = 15.0

# Tabla polar confirmada (0.5 IPS):
# Ground: 0.5 IPS -> 200 g => 0.0025 IPS/g
# Hover : 0.5 IPS -> 500 g => 0.0010 IPS/g
IPS_PER_GRAM = {
    "GROUND": 0.0025,
    "HOVER": 0.0010,
    "HORIZ": 0.0010,
}

# --------- ESCENARIO DIDÁCTICO (constante en los 3 runs) ----------
# Tracking dentro de tolerancia para centrar la práctica en BALANCE
BASE_TRACK = {
    "GROUND": {"BLU": +1.2, "GRN": -0.8, "YEL": 0.0, "RED": -0.6},
    "HOVER":  {"BLU": +1.5, "GRN": -1.0, "YEL": 0.0, "RED": -0.5},
    "HORIZ":  {"BLU": +1.0, "GRN": -0.7, "YEL": 0.0, "RED": -0.3},
}

# Balance (base): run1 muestra algo “jugoso”, y tú lo bajas con pesos
# (mantener constante entre runs para que dependa solo de tu ajuste)
BASE_BAL = {
    "GROUND": (0.45, 315.0),  # ~10:30
    "HOVER":  (0.18, 180.0),  # ~06:00 (más moderado para evitar STOP en hover)
    "HORIZ":  (0.14, 150.0),
}
# ---------------------------------------------------------------


def default_adjustments():
    return {
        r: {
            "pitch_turns": {b: 0.0 for b in BLADES},
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


def simulate_measurement(run: int, regime: str, adjustments: dict) -> Measurement:
    # COHERENCIA FÍSICA: los ajustes reales (pitch links y pesos) son globales
    master = adjustments.get("GROUND") or adjustments[regime]
    pitch_turns = master["pitch_turns"]
    bolt_g = master["bolt_g"]

    base_track = BASE_TRACK[regime].copy()
    base_amp, base_phase = BASE_BAL[regime]

    # -------------------------
    # TRACK model
    # -------------------------
    track = {}
    for b in BLADES:
        pitch_effect = PITCHLINK_MM_PER_TURN * float(pitch_turns[b])

        trim_effect = 0.0
        if regime == "HORIZ":
            # Trim tabs solo afectan en vuelo horizontal en este modelo
            trim_effect = TRIMTAB_MMTRACK_PER_MM * float(master["trim_mm"][b])

        noise = random.gauss(0.0, 0.25)
        track[b] = float(base_track[b] + pitch_effect + trim_effect + noise)

    # Relative to YEL
    y0 = float(track["YEL"])
    for b in BLADES:
        track[b] = float(track[b] - y0)
    track["YEL"] = 0.0

    # -------------------------
    # 1/rev BALANCE vector model
    # -------------------------
    v = _vec_from_clock_deg(base_phase) * float(base_amp)
    ips_per_gram = float(IPS_PER_GRAM.get(regime, IPS_PER_GRAM["GROUND"]))

    for b in BLADES:
        grams = float(bolt_g[b])
        v += (-ips_per_gram * grams) * _vec_from_clock_deg(BLADE_CLOCK_DEG[b])

    # ruido de medida
    v += np.array([random.gauss(0.0, 0.0025), random.gauss(0.0, 0.0025)], dtype=float)

    amp = float(np.linalg.norm(v))
    phase = float(_clock_deg_from_vec(v)) if amp > 1e-6 else 0.0

    return Measurement(
        regime=regime,
        balance=BalanceReading(amp, phase, BO105_DISPLAY_RPM),
        track_mm=track,
    )
