from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import re

from .types import Measurement
from .solver import suggest_pitchlink, suggest_trimtabs, suggest_weight, track_split_mm

BLADES = ["BLU", "GRN", "YEL", "RED"]

# Blade colors (approximate legacy VXP palette)
BLADE_COLOR = {
    "BLU": "#0000cc",
    "GRN": "#008800",
    "YEL": "#b09000",
    "RED": "#cc0000",
}

# Subtle coloring for regime names (legacy screens used colored regime text)
REGIME_COLOR = {
    "GROUND": "#000000",
    "HOVER": "#0000cc",
    "HORIZ": "#008800",
}

# Display order (BO105 procedure): ONLY these three.
DISPLAY_POINTS: List[Tuple[str, str]] = [
    ("100% Ground", "GROUND"),
    ("Hover Flight", "HOVER"),
    ("Horizontal Flight", "HORIZ"),
]


def clock_label(theta_deg: float) -> str:
    """Convert phase degrees to a 12-hour clock label (legacy VXP style)."""
    # 0° = 12:00, 90° = 03:00, 180° = 06:00 ...
    hour = int(round(theta_deg / 30.0)) % 12
    hour = 12 if hour == 0 else hour
    minute = 0 if abs((theta_deg / 30.0) - round(theta_deg / 30.0)) < 0.25 else 30
    return f"{hour:02d}:{minute:02d}"


def _c(txt: str, color: str) -> str:
    return f"<span style='color:{color};'>{txt}</span>"


def legacy_results_text(run: int, meas_by_regime: Dict[str, Measurement], *, aircraft: Optional[dict] = None) -> str:
    """Legacy-like mono report (with inline color spans)."""
    ac_id = None
    if aircraft:
        ac_id = str(aircraft.get("registration") or aircraft.get("reg") or "").strip() or None

    lines: List[str] = []
    lines.append("BO105   MAIN ROTOR   TRACK & BALANCE")
    lines.append("OPTION: B   STROBEX MODE: B")
    lines.append(f"RUN: {run}   ID: {ac_id or 'TRAINING'}")
    lines.append("")

    # -------------------------
    # Balance measurements
    # -------------------------
    lines.append("----- Balance Measurements -----")
    for name, src in DISPLAY_POINTS:
        if src not in meas_by_regime:
            continue
        m = meas_by_regime[src]
        amp = float(m.balance.amp_ips)
        ph = float(m.balance.phase_deg)
        reg = _c(f"{name:<18}", REGIME_COLOR.get(src, "#000"))
        lines.append(f"{reg}  1P {amp:0.2f} IPS  {clock_label(ph):>5}  RPM:{m.balance.rpm:0.0f}")

    lines.append("")

    # -------------------------
    # Track height
    # -------------------------
    lines.append("----- Track Height (mm rel. YEL) -----")
    for name, src in DISPLAY_POINTS:
        if src not in meas_by_regime:
            continue
        m = meas_by_regime[src]
        reg = _c(f"{name:<18}", REGIME_COLOR.get(src, "#000"))
        parts = [_c(f"{b}:{m.track_mm[b]:+5.1f}", BLADE_COLOR[b]) for b in BLADES]
        lines.append(f"{reg}  " + "  ".join(parts))

    # -------------------------
    # Solution
    # -------------------------
    lines.append("")
    lines.append("----- Solution Options -----")

    used_regimes = [name for name, src in DISPLAY_POINTS if src in meas_by_regime]
    if not used_regimes:
        lines.append("(No regimes collected yet)")
        lines.append("")
        return "\n".join(lines)

    lines.append("SOLUTION TYPE: BALANCE")
    lines.append(f"REGIMES USED: {', '.join(used_regimes)}")
    lines.append("USED: Pitch link, Trim tab, Weight")

    pl = suggest_pitchlink(meas_by_regime)
    tab = suggest_trimtabs(meas_by_regime)
    wrow = suggest_weight(meas_by_regime)

    lines.append("")
    lines.append("Adjustments")

    # Fixed-width columns so the result remains stable inside pre text.
    COL_W = 8

    def _hblade(b: str) -> str:
        return _c(f"{b:>{COL_W}}", BLADE_COLOR[b])

    def _vblade(b: str, s: str) -> str:
        return _c(f"{s:>{COL_W}}", BLADE_COLOR[b])

    def _hdr(label: str) -> str:
        return f"{label:<12}" + _hblade("BLU") + _hblade("GRN") + _hblade("YEL") + _hblade("RED")

    def _row(label: str, vals: Dict[str, float], fmt: str) -> str:
        return (
            f"{label:<12}"
            + _vblade("BLU", format(vals["BLU"], fmt))
            + _vblade("GRN", format(vals["GRN"], fmt))
            + _vblade("YEL", format(vals["YEL"], fmt))
            + _vblade("RED", format(vals["RED"], fmt))
        )

    lines.append(_hdr("P/L(flats)"))
    lines.append(_row("", pl, "6.2f"))

    lines.append(_hdr("Tab(mm)"))
    lines.append(_row("", tab, "6.2f"))

    lines.append(_hdr("Wt(g)"))
    lines.append(_row("", wrow, "6.0f"))

    lines.append("")
    lines.append("----- Track Split (mm) -----")
    for name, src in DISPLAY_POINTS:
        if src not in meas_by_regime:
            continue
        m = meas_by_regime[src]
        reg = _c(f"{name:<18}", REGIME_COLOR.get(src, "#000"))
        lines.append(f"{reg}  {track_split_mm(m):0.1f}")

    lines.append("")
    return "\n".join(lines)


def legacy_results_plain_text(run: int, meas_by_regime: Dict[str, Measurement], *, aircraft: Optional[dict] = None) -> str:
    """Same report as legacy_results_text but without HTML tags."""
    txt = legacy_results_text(run, meas_by_regime, aircraft=aircraft)
    return re.sub(r"</?span[^>]*>", "", txt)


def legacy_results_html(run: int, meas_by_regime: Dict[str, Measurement], *, aircraft: Optional[dict] = None) -> str:
    """HTML report used in the UI.

    We keep one single scrollable pane (like the legacy VXP textbox) but render
    *Adjustments* as a real HTML table so columns line up even with colors.
    """
    txt = legacy_results_text(run, meas_by_regime, aircraft=aircraft)

    marker = "\nAdjustments\n"
    if marker not in txt:
        return (
            "<div class='vxp-mono' style='white-space:pre; height:560px; overflow:auto;'>"
            + txt
            + "</div>"
        )

    before, after = txt.split(marker, 1)

    # Recompute adjustments for a real table
    pl = suggest_pitchlink(meas_by_regime)
    tab = suggest_trimtabs(meas_by_regime)
    wrow = suggest_weight(meas_by_regime)

    def td(text: str, *, color: str | None = None, bold: bool = False, align: str = "right") -> str:
        style = ["padding:2px 10px", f"text-align:{align}", "white-space:pre"]
        if color:
            style.append(f"color:{color}")
        if bold:
            style.append("font-weight:700")
        return f"<td style='{';'.join(style)}'>{text}</td>"

    def th(text: str, color: str) -> str:
        return td(text, color=color, bold=True)

    def row(label: str, vals: Dict[str, float], fmt: str) -> str:
        return (
            "<tr>"
            + td(label, bold=True, align="left")
            + td(format(vals["BLU"], fmt), color=BLADE_COLOR["BLU"])
            + td(format(vals["GRN"], fmt), color=BLADE_COLOR["GRN"])
            + td(format(vals["YEL"], fmt), color=BLADE_COLOR["YEL"])
            + td(format(vals["RED"], fmt), color=BLADE_COLOR["RED"])
            + "</tr>"
        )

    table = (
        "<table style='border-collapse:collapse; width:100%; font-family:Consolas, monospace; font-size:13px;'>"
        "<tr>"
        + td("Adjustments", bold=True, align="left")
        + th("BLU", BLADE_COLOR["BLU"])
        + th("GRN", BLADE_COLOR["GRN"])
        + th("YEL", BLADE_COLOR["YEL"])
        + th("RED", BLADE_COLOR["RED"])
        + "</tr>"
        + row("P/L(flats)", pl, "6.2f")
        + row("Tab(mm)", tab, "6.2f")
        + row("Wt(g)", wrow, "6.0f")
        + "</table>"
    )

    return (
        "<div class='vxp-mono' style='height:560px; overflow:auto;'>"
        "<div style='white-space:pre;'>"
        + before
        + "\n</div>"
        "<div style='padding:6px 8px; background:white; border:1px solid #808080; margin:6px 0;'>"
        + table
        + "</div>"
        "<div style='white-space:pre;'>"
        + after
        + "</div>"
        "</div>"
    )
