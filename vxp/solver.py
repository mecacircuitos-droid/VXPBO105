import math
from typing import Dict, Optional, Tuple

from .types import Measurement

# Blade order used across the app
BLADES = ["BLU", "GRN", "YEL", "RED"]

# Keep in sync with vxp.sim.REGIMES
REGIMES = ["GROUND", "HOVER", "HORIZ"]

# Clock reference used by the simulator (12 o'clock = 0°, 3 o'clock = 90° ...)
BLADE_CLOCK_DEG = {"YEL": 0.0, "RED": 90.0, "BLU": 180.0, "GRN": 270.0}

# Correction sensitivities (BO105 training material)
PITCHLINK_MM_PER_TURN = 10.0
TRIMTAB_MMTRACK_PER_MM = 15.0

# Balance chart scaling (your polar table)
# - Ground (G axis): 0.5 IPS -> 200 g  => 0.0025 IPS/g
# - Hover  (H axis): 0.5 IPS -> 500 g  => 0.0010 IPS/g
IPS_PER_GRAM = {
    "GROUND": 0.0025,
    "HOVER": 0.0010,
    # In this simulator, Horizontal Flight uses the same sensitivity as hover.
    "HORIZ": 0.0010,
}


# -----------------------------
# Acceptance limits (used by all_ok)
# -----------------------------

def track_limit(regime: str) -> float:
    """Acceptance limit for track spread (mm)."""
    if regime == "GROUND":
        # Training text uses 15 mm as the allowable ground spread.
        return 15.0
    # Hover and horizontal flight are tightened to 5 mm.
    return 5.0


def balance_limit(regime: str) -> float:
    """Acceptance limit for 1/rev vibration amplitude (IPS)."""
    if regime == "GROUND":
        # Training material drives balance to 0.2 IPS or less on ground.
        return 0.20
    # Hover target is much tighter.
    return 0.05


# -----------------------------
# Legacy-style limit bands (for UI icons)
# -----------------------------
# The original UI shows 3 states per regime:
#  - OK   : within acceptance
#  - WARN : exceeds acceptance (correction recommended)
#  - STOP : exceeds procedural boundary (do not proceed)


def acceptance_track_limit(regime: str) -> float:
    return track_limit(regime)


def procedural_track_limit(regime: str) -> float:
    # Procedural “do not proceed” bands.
    if regime == "GROUND":
        # Above ~20–30 mm on ground is clearly out-of-family.
        return 30.0
    if regime == "HOVER":
        return 10.0
    # Horizontal flight: many procedures allow stepping speeds only if <50 mm.
    return 20.0


def acceptance_balance_limit(regime: str) -> float:
    return balance_limit(regime)


def procedural_balance_limit(regime: str) -> float:
    if regime == "GROUND":
        # Abort / don't continue if it stays above 0.4 IPS.
        return 0.40
    # Hover: keep a practical upper band above the 0.05 acceptance.
    return 0.15


def track_spread(m: Measurement) -> float:
    vals = [float(m.track_mm[b]) for b in BLADES]
    return float(max(vals) - min(vals))


def regime_status(regime: str, m: Optional[Measurement]) -> Optional[str]:
    """Return a status code used for the small regime icons.

    None: no measurement
    "OK":   within acceptance
    "WARN": exceeds acceptance but within procedural
    "STOP": exceeds procedural
    "DONE": measurement exists but we can't compute limits
    """
    if m is None:
        return None

    try:
        ts = track_spread(m)
        amp = float(m.balance.amp_ips)
    except Exception:
        return "DONE"

    if regime not in REGIMES:
        return "DONE"

    if ts > procedural_track_limit(regime) or amp > procedural_balance_limit(regime):
        return "STOP"
    if ts > acceptance_track_limit(regime) or amp > acceptance_balance_limit(regime):
        return "WARN"
    return "OK"


def all_ok(meas_by_regime: Dict[str, Measurement]) -> bool:
    """True if all regimes are collected and within acceptance limits."""
    for r in REGIMES:
        if r not in meas_by_regime:
            return False
        m = meas_by_regime[r]
        if track_spread(m) > track_limit(r):
            return False
        if float(m.balance.amp_ips) > balance_limit(r):
            return False
    return True


def _round_quarter(x: float) -> float:
    return round(x * 4.0) / 4.0


def suggest_pitchlink(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest pitch-link turns (flats) based on Ground + Hover track."""
    used = [r for r in ("GROUND", "HOVER") if r in meas]
    if not used:
        return {b: 0.0 for b in BLADES}

    out: Dict[str, float] = {}
    for b in BLADES:
        avg = sum(float(meas[r].track_mm[b]) for r in used) / len(used)
        # Positive avg => blade tip too high => reduce lift => turn clockwise (negative turns)
        out[b] = _round_quarter((-avg) / PITCHLINK_MM_PER_TURN)
    return out


def suggest_trimtabs(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest trim-tab bending based on Horizontal Flight track.

    In this simplified BO105 workflow, Horizontal Flight is the only forward-flight regime.
    Values are in mm equivalent bend, clamped to ±5 mm.
    """
    if "HORIZ" not in meas:
        return {b: 0.0 for b in BLADES}

    out: Dict[str, float] = {}
    for b in BLADES:
        dev = float(meas["HORIZ"].track_mm[b])
        out[b] = max(-5.0, min(5.0, _round_quarter((-dev) / TRIMTAB_MMTRACK_PER_MM)))
    return out


# -----------------------------
# Balance weight suggestion (2-bolt max, chart-like)
# -----------------------------

def _vec_from_clock_deg(theta_deg: float) -> Tuple[float, float]:
    """Unit vector from a clock angle, consistent with vxp.sim._vec_from_clock_deg."""
    phi = math.radians(90.0 - float(theta_deg))
    return (math.cos(phi), math.sin(phi))


def _dot(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return float(a[0] * b[0] + a[1] * b[1])


def _pick_balance_regime(meas: Dict[str, Measurement]) -> Optional[str]:
    # Prefer hover if available; otherwise ground; otherwise horizontal.
    if "HOVER" in meas:
        return "HOVER"
    if "GROUND" in meas:
        return "GROUND"
    if "HORIZ" in meas:
        return "HORIZ"
    return None


def suggest_weight(meas: Dict[str, Measurement]) -> Dict[str, float]:
    """Suggest balance weights in grams per blade.

    Returns a dict {BLU/GRN/YEL/RED: grams_to_add}.

    Implementation goals:
    - Distinguish G vs H chart scaling (IPS/gram differs).
    - Use at most 2 blades (max 2 bolts with weights).
    - If amp > 0.5 IPS, change only one weight first (training note).

    This is a *chart-like* solver: it decomposes the measured 1/rev vector into the
    two orthogonal blade axes of the current quadrant (equivalent to drawing parallels
    to the chart axes).
    """
    if not meas:
        return {b: 0.0 for b in BLADES}

    regime = _pick_balance_regime(meas)
    if regime is None:
        return {b: 0.0 for b in BLADES}

    m = meas[regime]
    amp = float(m.balance.amp_ips)
    phase = float(m.balance.phase_deg) % 360.0

    k = IPS_PER_GRAM.get(regime, IPS_PER_GRAM["GROUND"])
    if k <= 0:
        return {b: 0.0 for b in BLADES}

    # Vector in "grams" that would reproduce the measured IPS vector using the chart scaling.
    vx, vy = _vec_from_clock_deg(phase)
    gvec = (vx * (amp / k), vy * (amp / k))

    # Choose the two orthogonal blade axes for the quadrant.
    # 0..90:  YEL (0)  + RED (90)
    # 90..180: RED (90) + BLU (180)
    # 180..270: BLU (180) + GRN (270)
    # 270..360: GRN (270) + YEL (0)
    if 0.0 <= phase < 90.0:
        axes = ("YEL", "RED")
    elif 90.0 <= phase < 180.0:
        axes = ("RED", "BLU")
    elif 180.0 <= phase < 270.0:
        axes = ("BLU", "GRN")
    else:
        axes = ("GRN", "YEL")

    out = {b: 0.0 for b in BLADES}

    # Project onto the axis unit vectors to get positive grams in that quadrant.
    comps: Dict[str, float] = {}
    for b in axes:
        ub = _vec_from_clock_deg(BLADE_CLOCK_DEG[b])
        comps[b] = max(0.0, _dot(gvec, ub))

    # Training note: if amplitude is >0.5 IPS, adjust only one weight first.
    if amp > 0.50:
        # Keep only the larger component.
        keep = max(comps, key=lambda bb: comps[bb])
        comps = {keep: comps[keep]}

    # Round to practical increments (10 g), clamp to practical bounds.
    def round10(x: float) -> float:
        return round(x / 10.0) * 10.0

    for b, g in comps.items():
        g = round10(g)
        if g < 10.0:
            g = 0.0
        g = min(600.0, g)
        out[b] = float(g)

    # Guarantee max 2 blades (should already be true).
    nonzero = [b for b in BLADES if out[b] > 0.0]
    if len(nonzero) > 2:
        nonzero.sort(key=lambda bb: out[bb], reverse=True)
        keep2 = set(nonzero[:2])
        for b in BLADES:
            if b not in keep2:
                out[b] = 0.0

    return out
