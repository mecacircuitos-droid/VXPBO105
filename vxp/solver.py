import math
from typing import Dict

from .types import Measurement

BLADES = ["BLU", "GRN", "YEL", "RED"]

# Keep in sync with vxp.sim.REGIMES
REGIMES = ["GROUND", "HOVER", "HORIZ"]

# Clock positions (legacy convention used by the simulator)
BLADE_CLOCK_DEG = {"YEL": 0.0, "RED": 90.0, "BLU": 180.0, "GRN": 270.0}

# Tracking sensitivities
PITCHLINK_MM_PER_TURN = 10.0
TRIMTAB_MMTRACK_PER_MM = 15.0
TRIMTAB_MAX_MM = 5.0

# Operational limits (BO105)
TRACK_SPLIT_LIMIT_MM = {
    "GROUND": 10.0,
    "HOVER": 5.0,
    "HORIZ": 5.0,  # Horizontal (forward flight) target in this simplified workflow
}
BALANCE_LIMIT_IPS = {
    "GROUND": 0.40,
    "HOVER": 0.05,
    "HORIZ": 0.05,
}

# Balance-chart scaling (G vs H axes)
# User-provided: 0.5 IPS ≈ 200 g (Ground) and 0.5 IPS ≈ 500 g (Hover)
IPS_PER_GRAM = {
    "GROUND": 0.0025,
    "HOVER": 0.0010,
    "HORIZ": 0.0010,
}

WEIGHT_STEP_G = 10.0
WEIGHT_MAX_G = 600.0  # allow hover-scale corrections


def track_limit(regime: str) -> float:
    return float(TRACK_SPLIT_LIMIT_MM.get(regime, TRACK_SPLIT_LIMIT_MM["GROUND"]))


def balance_limit(regime: str) -> float:
    return float(BALANCE_LIMIT_IPS.get(regime, BALANCE_LIMIT_IPS["GROUND"]))


def _vec_from_clock_deg(theta_deg: float) -> tuple[float, float]:
    """Unit vector for a clock angle (0°=12 o'clock)."""
    phi = math.radians(90.0 - float(theta_deg))
    return (math.cos(phi), math.sin(phi))


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(a[0] * b[0] + a[1] * b[1])


def _round_step(x: float, step: float) -> float:
    return round(x / step) * step

def _round_quarter(x: float) -> float:
    return round(x * 4.0) / 4.0





def suggest_pitchlink(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest rotating pitch-link turns based on Ground + Hover track.

    Uses average deviation (mm rel. YEL) across available regimes.
    Positive output = lengthen/CCW (increase lift / raise blade), negative = shorten/CW.
    """
    used = [r for r in ("GROUND", "HOVER") if r in meas]
    if not used:
        return {b: 0.0 for b in BLADES}

    out: Dict[str, float] = {}
    for b in BLADES:
        avg = sum(float(meas[r].track_mm[b]) for r in used) / len(used)
        out[b] = _round_quarter((-avg) / PITCHLINK_MM_PER_TURN)

    # Keep reference blade pinned
    out["YEL"] = 0.0
    return out


def suggest_trimtabs(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest trim-tab bending (mm) from Horizontal Flight tracking.

    Positive output = bend UP (raise blade); negative = bend DOWN (lower blade).
    """
    if "HORIZ" not in meas:
        return {b: 0.0 for b in BLADES}

    out: Dict[str, float] = {}
    for b in BLADES:
        dev = float(meas["HORIZ"].track_mm[b])
        mm = (-dev) / TRIMTAB_MMTRACK_PER_MM
        mm = max(-TRIMTAB_MAX_MM, min(TRIMTAB_MAX_MM, mm))
        out[b] = _round_quarter(mm)

    out["YEL"] = 0.0
    return out


def suggest_weight(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest bolt weights (g) using a 2-bolt (max) decomposition.

    We treat the measured (amp, phase) as a vector. Adding weight on a blade-bolt
    produces a corrective 1/rev vector at that blade's clock angle.

    Output is a dict with up to two non-zero blades (rounded to WEIGHT_STEP_G).
    """
    if not meas:
        return {b: 0.0 for b in BLADES}

    # Prefer using the most relevant balancing regimes
    preferred = [r for r in ("GROUND", "HOVER") if r in meas]
    if preferred:
        worst_r = max(preferred, key=lambda r: float(meas[r].balance.amp_ips))
    else:
        worst_r = max(meas.keys(), key=lambda r: float(meas[r].balance.amp_ips))

    m = meas[worst_r]
    amp = float(m.balance.amp_ips)
    phase = float(m.balance.phase_deg) % 360.0

    k = float(IPS_PER_GRAM.get(worst_r, IPS_PER_GRAM["GROUND"]))
    # Weight-vector magnitude (grams) that would cancel the measured imbalance
    ux, uy = _vec_from_clock_deg(phase)
    wvx, wvy = (ux * amp / k, uy * amp / k)

    # Choose the adjacent 90° pair (quadrant) that contains the phase.
    # 0-90: YEL+RED, 90-180: RED+BLU, 180-270: BLU+GRN, 270-360: GRN+YEL
    if 0.0 <= phase < 90.0:
        b1, b2 = "YEL", "RED"
    elif 90.0 <= phase < 180.0:
        b1, b2 = "RED", "BLU"
    elif 180.0 <= phase < 270.0:
        b1, b2 = "BLU", "GRN"
    else:
        b1, b2 = "GRN", "YEL"

    u1 = _vec_from_clock_deg(BLADE_CLOCK_DEG[b1])
    u2 = _vec_from_clock_deg(BLADE_CLOCK_DEG[b2])

    # Because u1/u2 are orthonormal, components are simple dot-products.
    w1 = _dot((wvx, wvy), u1)
    w2 = _dot((wvx, wvy), u2)

    # Ensure non-negative (stay within the chosen quadrant).
    w1 = max(0.0, w1)
    w2 = max(0.0, w2)

    # If very large imbalance, the AMM-style rule is "change only one weight first".
    # We'll mimic that by picking the larger component if amp >= 0.50 IPS.
    if amp >= 0.50:
        if w1 >= w2:
            w2 = 0.0
        else:
            w1 = 0.0

    # Round + clamp
    w1 = min(WEIGHT_MAX_G, max(0.0, _round_step(w1, WEIGHT_STEP_G)))
    w2 = min(WEIGHT_MAX_G, max(0.0, _round_step(w2, WEIGHT_STEP_G)))

    out = {b: 0.0 for b in BLADES}
    out[b1] = float(w1)
    out[b2] = float(w2)

    # In this simulator we keep the reference blade free of weights by default.
    # (You can remove this if you want to allow weights everywhere.)
    out["YEL"] = out.get("YEL", 0.0)

    return out
