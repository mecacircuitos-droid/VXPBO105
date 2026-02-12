import math
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter

from .types import Measurement

BLADES = ["BLU", "GRN", "YEL", "RED"]

# Keep in sync with vxp.sim.REGIMES
REGIMES = ["GROUND", "HOVER", "HORIZ"]

REGIME_LABEL = {
    "GROUND": "100% Ground",
    "HOVER": "Hover Flight",
    "HORIZ": "Horizontal Flight",
}

REGIME_LABEL_SHORT = {
    "GROUND": "100% Ground",
    "HOVER": "Hover Flight",
    "HORIZ": "Horizontal Flight",
}

# Colors (blue/green/yellow/red) to mimic the legacy VXP appearance
BLADE_COLOR = {
    "BLU": "#0047AB",
    "GRN": "#0A8F08",
    "YEL": "#B58900",
    "RED": "#B00020",
}

REGIME_TAG = {"GROUND": "GND", "HOVER": "HOV", "HORIZ": "HOR"}
REGIME_COLOR = {"GROUND": "#000000", "HOVER": "#0047AB", "HORIZ": "#0A8F08"}


def _track_rel(meas: Measurement, blade_ref: str) -> List[float]:
    ref = float(meas.track_mm.get(blade_ref, 0.0))
    return [float(meas.track_mm[b]) - ref for b in BLADES]


def _auto_lim(vals: List[float], *, min_lim: float = 6.0, max_lim: float = 32.5) -> Tuple[float, List[float]]:
    """Return (lim, ticks) for symmetric track plots.

    The legacy VXP uses a wide fixed range, but for training it's useful to
    auto-zoom so small corrections are visible.
    """
    if not vals:
        lim = min_lim
    else:
        m = max(abs(float(v)) for v in vals)
        lim = max(min_lim, min(max_lim, m * 1.25 + 1.0))
    # Round to nearest 0.5 mm
    lim = round(lim * 2.0) / 2.0
    return lim, [-lim, 0.0, lim]


def plot_measurements_panel(
    meas_by_regime: Dict[str, Measurement],
    selected_regime: str,
    blade_ref: str = "YEL",
) -> plt.Figure:
    """Single, VXP-like right panel: track marker + track trend + polar."""

    fig = plt.figure(figsize=(4.8, 5.05), dpi=120)
    fig.patch.set_facecolor("#c0c0c0")

    gs = fig.add_gridspec(nrows=3, ncols=1, height_ratios=[1.0, 1.15, 3.0], hspace=0.28)

    regimes_present = [r for r in REGIMES if r in meas_by_regime]
    if selected_regime not in meas_by_regime and regimes_present:
        selected_regime = regimes_present[0]

    # ----------------------
    # Track marker (selected regime)
    # ----------------------
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("white")

    m = meas_by_regime[selected_regime]
    ys = _track_rel(m, blade_ref)
    lim1, ticks1 = _auto_lim(ys, min_lim=6.0)

    ax1.set_ylim(-lim1, lim1)
    ax1.set_xlim(0.5, len(BLADES) + 0.5)
    ax1.set_yticks(ticks1)
    ax1.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax1.tick_params(axis="y", labelsize=8)
    ax1.set_ylabel("mm", fontsize=8, fontweight="bold")

    ax1.set_xticks(range(1, len(BLADES) + 1))
    ax1.set_xticklabels(BLADES, fontsize=9, fontweight="bold")
    ax1.tick_params(axis="x", labeltop=True, labelbottom=False, pad=1)
    ax1.xaxis.tick_top()

    for i in range(1, len(BLADES) + 1):
        ax1.axvline(i, color="black", linewidth=0.6, linestyle=":")

    xs = list(range(1, len(BLADES) + 1))
    ax1.scatter(
        xs,
        ys,
        marker="s",
        s=30,
        c=[BLADE_COLOR[b] for b in BLADES],
        edgecolors="black",
        linewidths=0.4,
        zorder=5,
    )
    ax1.axhline(0.0, color="black", linewidth=0.8)

    for sp in ax1.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)

    # ----------------------
    # Track trend across regimes
    # ----------------------
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor("white")

    x_labels = [REGIME_LABEL_SHORT[r] for r in regimes_present]
    x = list(range(len(regimes_present)))

    all_vals: List[float] = []
    for r in regimes_present:
        all_vals.extend(_track_rel(meas_by_regime[r], blade_ref))
    lim2, ticks2 = _auto_lim(all_vals, min_lim=6.0)

    ax2.set_ylim(-lim2, lim2)
    ax2.set_yticks(ticks2)
    ax2.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax2.tick_params(axis="y", labelsize=8)
    ax2.set_ylabel("mm", fontsize=8, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels, fontsize=8)

    for xi in x:
        ax2.axvline(xi, color="black", linewidth=0.5, linestyle=":")

    for b in BLADES:
        ys_b = [_track_rel(meas_by_regime[r], blade_ref)[BLADES.index(b)] for r in regimes_present]
        ax2.plot(x, ys_b, marker="s", linewidth=1.0, markersize=3.5, color=BLADE_COLOR[b])

    ax2.axhline(0.0, color="black", linewidth=0.8)
    ax2.grid(True, linestyle=":", linewidth=0.6)

    for sp in ax2.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)

    # ----------------------
    # Polar plot (selected regime)
    # ----------------------
    ax3 = fig.add_subplot(gs[2, 0], projection="polar")
    ax3.set_facecolor("white")
    ax3.set_theta_zero_location("N")
    ax3.set_theta_direction(-1)
    ticks = [math.radians(t) for t in range(0, 360, 30)]
    labels = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    ax3.set_xticks(ticks)
    ax3.set_xticklabels(labels, fontsize=9, fontweight="bold")

    amp = float(m.balance.amp_ips)
    rmax = max(0.35, amp * 1.8)
    rmax = math.ceil(rmax * 20.0) / 20.0
    ax3.set_rmax(rmax)
    rticks = [round(0.1 * i, 2) for i in range(1, int(rmax / 0.1) + 1)]
    if rticks and rticks[-1] < rmax:
        rticks.append(rmax)
    if not rticks:
        rticks = [0.1, 0.2, 0.3]
    ax3.set_rticks(rticks)
    ax3.set_yticklabels([f"{t:.2f}" for t in rticks], fontsize=8)
    ax3.grid(True, linestyle=":", linewidth=0.6)

    theta = math.radians(float(m.balance.phase_deg))
    ax3.plot([theta, theta], [0.0, amp], linewidth=2.0, color="black")
    ax3.scatter([theta], [amp], s=40, c="black")

    ax3.set_title(f"1P  {amp:.2f} IPS  @ {REGIME_LABEL.get(m.regime, m.regime)}", fontsize=9, fontweight="bold")
    for sp in ax3.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)

    fig.tight_layout(pad=0.55)
    return fig


def plot_track_marker(meas: Measurement, blade_ref: str = "YEL") -> plt.Figure:
    fig = plt.figure(figsize=(3.6, 1.18), dpi=120)
    fig.patch.set_facecolor("#c0c0c0")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")

    ys = _track_rel(meas, blade_ref)
    lim, ticks = _auto_lim(ys, min_lim=6.0)

    ax.set_ylim(-lim, lim)
    ax.set_xlim(0.5, len(BLADES) + 0.5)
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylabel("mm", fontsize=8, fontweight="bold")

    ax.set_xticks(range(1, len(BLADES) + 1))
    ax.set_xticklabels(BLADES, fontsize=9, fontweight="bold")
    ax.tick_params(axis="x", labeltop=True, labelbottom=False, pad=1)
    ax.xaxis.tick_top()

    for i in range(1, len(BLADES) + 1):
        ax.axvline(i, color="black", linewidth=0.6, linestyle=":")

    xs = list(range(1, len(BLADES) + 1))
    ax.scatter(xs, ys, marker="s", s=30, c=[BLADE_COLOR[b] for b in BLADES], edgecolors="black", linewidths=0.4)
    ax.axhline(0.0, color="black", linewidth=0.8)

    ax.set_title(f"Track Marker ({REGIME_LABEL.get(meas.regime, meas.regime)})", fontsize=9, fontweight="bold")
    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)
    fig.tight_layout(pad=0.55)
    return fig


def plot_track_graph(meas_by_regime: Dict[str, Measurement]) -> plt.Figure:
    xs = [REGIME_LABEL_SHORT[r] for r in REGIMES if r in meas_by_regime]
    fig = plt.figure(figsize=(3.6, 1.18), dpi=120)
    fig.patch.set_facecolor("#c0c0c0")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")

    all_vals: List[float] = []
    for r in REGIMES:
        if r not in meas_by_regime:
            continue
        all_vals.extend([float(meas_by_regime[r].track_mm[b]) for b in BLADES])
    lim, ticks = _auto_lim(all_vals, min_lim=6.0)

    for b in BLADES:
        ys = [meas_by_regime[r].track_mm[b] for r in REGIMES if r in meas_by_regime]
        ax.plot(xs, ys, marker="s", linewidth=1.2, markersize=4, label=b, color=BLADE_COLOR[b])

    ax.set_ylim(-lim, lim)
    ax.set_yticks(ticks)
    ax.set_title("Track Height (rel. YEL)", fontsize=9, fontweight="bold")
    ax.axhline(0.0, linewidth=0.8)
    ax.grid(True, linestyle=":", linewidth=0.6)

    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)
    ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout(pad=0.55)
    return fig


def plot_polar(meas: Measurement) -> plt.Figure:
    fig = plt.figure(figsize=(3.6, 2.35), dpi=120)
    fig.patch.set_facecolor("#c0c0c0")
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor("white")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ticks = [math.radians(t) for t in range(0, 360, 30)]
    labels = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=9, fontweight="bold")
    rmax = max(0.35, float(meas.balance.amp_ips) * 1.8)
    rmax = math.ceil(rmax * 20.0) / 20.0
    ax.set_rmax(rmax)
    rticks = [round(0.1 * i, 2) for i in range(1, int(rmax / 0.1) + 1)]
    if rticks and rticks[-1] < rmax:
        rticks.append(rmax)
    if not rticks:
        rticks = [0.1, 0.2, 0.3]
    ax.set_rticks(rticks)
    ax.set_yticklabels([f"{t:.2f}" for t in rticks], fontsize=8)
    ax.grid(True, linestyle=":", linewidth=0.6)

    theta = math.radians(float(meas.balance.phase_deg))
    amp = float(meas.balance.amp_ips)
    ax.plot([theta, theta], [0.0, amp], linewidth=2.0, color="black")
    ax.scatter([theta], [amp], s=45, c="black")
    ax.set_title(f"1P  {amp:.2f} IPS", fontsize=9, fontweight="bold")
    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)
    fig.tight_layout(pad=0.55)
    return fig


def plot_polar_compare(meas_by_regime: Dict[str, Measurement]) -> plt.Figure:
    """Overlay the three polar vectors in one chart (for quick comparison)."""
    fig = plt.figure(figsize=(3.6, 2.35), dpi=120)
    fig.patch.set_facecolor("#c0c0c0")
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor("white")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ticks = [math.radians(t) for t in range(0, 360, 30)]
    labels = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=9, fontweight="bold")

    amps = [float(meas_by_regime[r].balance.amp_ips) for r in REGIMES if r in meas_by_regime]
    rmax = max([0.35] + [a * 1.8 for a in amps])
    rmax = math.ceil(rmax * 20.0) / 20.0
    ax.set_rmax(rmax)
    rticks = [round(0.1 * i, 2) for i in range(1, int(rmax / 0.1) + 1)]
    if rticks and rticks[-1] < rmax:
        rticks.append(rmax)
    if not rticks:
        rticks = [0.1, 0.2, 0.3]
    ax.set_rticks(rticks)
    ax.set_yticklabels([f"{t:.2f}" for t in rticks], fontsize=8)
    ax.grid(True, linestyle=":", linewidth=0.6)

    for r in REGIMES:
        if r not in meas_by_regime:
            continue
        m = meas_by_regime[r]
        theta = math.radians(float(m.balance.phase_deg))
        amp = float(m.balance.amp_ips)
        ax.plot([theta, theta], [0.0, amp], linewidth=2.0, color=REGIME_COLOR[r])
        ax.scatter([theta], [amp], s=30, c=REGIME_COLOR[r], label=REGIME_TAG[r])

    ax.legend(loc="lower left", bbox_to_anchor=(-0.05, -0.05), fontsize=8, frameon=False)
    ax.set_title("Balance Compare", fontsize=9, fontweight="bold")
    for sp in ax.spines.values():
        sp.set_color("black")
        sp.set_linewidth(1.0)

    fig.tight_layout(pad=0.55)
    return fig
