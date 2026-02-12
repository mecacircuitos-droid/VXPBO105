import math
from typing import Dict, Optional

from .types import Measurement

BLADES = ["BLU", "GRN", "YEL", "RED"]

# Keep in sync with vxp.sim.REGIMES
REGIMES = ["GROUND", "HOVER", "HORIZ"]

# Clock positions (legacy convention used by the simulator)
BLADE_CLOCK_DEG = {"YEL": 0.0, "RED": 90.0, "BLU": 180.0, "GRN": 270.0}

# -----------------------------
# Tracking / balance sensitivity
# -----------------------------
FLATS_PER_TURN = 6.0

# 1 full turn of the pitch link ≈ 10 mm at blade tip
PITCHLINK_MM_PER_TURN = 10.0

# Trim tab: 1 mm bend ≈ 15 mm track change at tip (BO105 training / AMM notes)
TRIMTAB_MMTRACK_PER_MM = 15.0
TRIMTAB_MAX_MM = 5.0

# -----------------------------
# Operational / training limits
# -----------------------------
# Track spread (max - min) limits for the three simulator regimes.
TRACK_SPLIT_LIMIT_MM = {
    "GROUND": 10.0,
    "HOVER": 5.0,
    "HORIZ": 5.0,  # Forward flight target (120 KIAS) in this simplified workflow
}

# Balance limits:
# - "WARN": highlighted in the COLLECT list (green "!") but not blocking
# - "STOP": red octagon (simulates a "do not continue" situation)
BALANCE_WARN_IPS = {"GROUND": 0.20, "HOVER": 0.20, "HORIZ": 0.20}
BALANCE_STOP_IPS = {"GROUND": 0.50, "HOVER": 0.50, "HORIZ": 0.50}

# Balance-chart scaling (G vs H axes)
# User-provided: 0.5 IPS ≈ 200 g (Ground) and 0.5 IPS ≈ 500 g (Hover)
IPS_PER_GRAM = {"GROUND": 0.0025, "HOVER": 0.0010, "HORIZ": 0.0010}

WEIGHT_STEP_G = 10.0
WEIGHT_MAX_G = 600.0  # allow hover-scale corrections


def track_limit(regime: str) -> float:
    return float(TRACK_SPLIT_LIMIT_MM.get(regime, TRACK_SPLIT_LIMIT_MM["GROUND"]))


def balance_warn(regime: str) -> float:
    return float(BALANCE_WARN_IPS.get(regime, BALANCE_WARN_IPS["GROUND"]))


def balance_stop(regime: str) -> float:
    return float(BALANCE_STOP_IPS.get(regime, BALANCE_STOP_IPS["GROUND"]))


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


def track_split_mm(m: Measurement) -> float:
    vals = [float(m.track_mm[b]) for b in BLADES]
    return float(max(vals) - min(vals))


def regime_status(regime: str, m: Optional[Measurement]) -> Optional[str]:
    """Return legacy-like status for a collected regime.

    Returns:
      - None: not collected
      - "OK": within limits
      - "WARN": exceeds a training limit (green exclamation)
      - "STOP": exceeds a stop limit (red octagon)
    """
    if m is None:
        return None

    # TRACK
    split = track_split_mm(m)
    t_lim = track_limit(regime)
    track_stat = "OK" if split <= t_lim else "WARN"

    # BALANCE
    amp = float(m.balance.amp_ips)
    if amp > balance_stop(regime):
        bal_stat = "STOP"
    elif amp > balance_warn(regime):
        bal_stat = "WARN"
    else:
        bal_stat = "OK"

    # Combine
    if bal_stat == "STOP":
        return "STOP"
    if track_stat == "WARN" or bal_stat == "WARN":
        return "WARN"
    return "OK"


def all_ok(meas_by_regime: Dict[str, Measurement]) -> bool:
    """True if all required regimes exist and are within limits."""
    for r in REGIMES:
        if r not in meas_by_regime:
            return False
        if regime_status(r, meas_by_regime.get(r)) != "OK":
            return False
    return True


# -----------------------------
# Solution helpers
# -----------------------------

def suggest_pitchlink(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest pitch-link correction in *flats* based on Ground + Hover track.

    Positive output = lengthen/CCW (increase lift / raise blade), negative = shorten/CW.
    1 full turn = 6 flats.
    """
    used = [r for r in ("GROUND", "HOVER") if r in meas]
    if not used:
        return {b: 0.0 for b in BLADES}

    out: Dict[str, float] = {}
    for b in BLADES:
        avg = sum(float(meas[r].track_mm[b]) for r in used) / len(used)
        flats = (-avg) / PITCHLINK_MM_PER_TURN * FLATS_PER_TURN
        out[b] = _round_quarter(flats)

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

    # AMM-style rule: when amplitude is high, change one weight first.
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
    return out
