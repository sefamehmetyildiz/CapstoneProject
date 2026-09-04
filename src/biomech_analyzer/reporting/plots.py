"""Matplotlib figure generation for reports and the GUI.

Uses the non-interactive Agg backend; every function writes a PNG and
returns its path.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from biomech_analyzer.core.models import TrialData, TrialResult  # noqa: E402
from biomech_analyzer.utils.file_utils import ensure_dir  # noqa: E402

log = logging.getLogger(__name__)

_DPI = 110


def plot_fz_with_events(
    trial: TrialData, result: TrialResult, out_dir: Path
) -> Path | None:
    """Vertical GRF trace with detected events marked."""
    if trial.force_plate is None:
        return None
    ensure_dir(out_dir)
    fp = trial.force_plate
    events = result.features.events
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(fp.time_s, fp.fz_n, lw=0.9, color="#1f77b4", label="Fz")
    if events is not None:
        markers = [
            (events.takeoff_s, "Take-off", "#d62728"),
            (events.initial_contact_s, "Initial contact", "#2ca02c"),
            (events.peak_force_s, "Peak force", "#9467bd"),
            (events.stabilization_s, "Stabilization", "#8c564b"),
        ]
        for t, label, color in markers:
            if t is not None:
                ax.axvline(t, color=color, ls="--", lw=1, label=label)
        if events.body_weight_n:
            ax.axhline(events.body_weight_n, color="gray", ls=":", lw=1, label="Body weight")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Force (N)")
    from biomech_analyzer.core.constants import RISK_COLORS

    ax.set_title(
        f"{result.trial_id} — vertical GRF and events "
        f"[risk: {result.overall_risk.value}]",
        color=RISK_COLORS[result.overall_risk],
        fontweight="bold",
    )
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    path = out_dir / f"{result.trial_id}_fz.png"
    fig.savefig(path, dpi=_DPI)
    plt.close(fig)
    return path


def _z_color(z: float) -> str:
    """Risk-band colour for a z-score: green < 1, orange 1-2, red >= 2."""
    if abs(z) >= 2.0:
        return "#d62728"
    if abs(z) >= 1.0:
        return "#ff7f0e"
    return "#2ca02c"


def plot_zscores(result: TrialResult, out_dir: Path) -> Path | None:
    """Horizontal bar chart of baseline z-scores, risk-colour coded."""
    comps = [c for c in result.baseline_comparisons if c.z_score is not None]
    if not comps:
        return None
    ensure_dir(out_dir)
    comps.sort(key=lambda c: abs(c.z_score or 0), reverse=True)
    names = [c.feature for c in comps]
    zs = [c.z_score or 0.0 for c in comps]
    colors = [_z_color(z) for z in zs]
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(comps) + 1.2))
    ax.barh(names[::-1], zs[::-1], color=colors[::-1])
    for x in (-2.0, -1.0, 1.0, 2.0):
        ax.axvline(x, color="gray", ls="--", lw=0.8)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("z-score vs normative baseline")
    ax.set_title(f"{result.trial_id} — baseline comparison")
    fig.tight_layout()
    path = out_dir / f"{result.trial_id}_zscores.png"
    fig.savefig(path, dpi=_DPI)
    plt.close(fig)
    return path


def plot_knee_flexion(
    trial: TrialData, result: TrialResult, out_dir: Path
) -> Path | None:
    """Knee flexion trace around the landing, when Xsens data exists."""
    if trial.xsens is None:
        return None
    keys = [
        k
        for k in trial.xsens.joint_angles_deg
        if "knee" in k.lower() and "flexion" in k.lower()
    ]
    if not keys:
        return None
    ensure_dir(out_dir)
    fig, ax = plt.subplots(figsize=(7, 2.6))
    ax.plot(
        trial.xsens.time_s,
        trial.xsens.joint_angles_deg[keys[0]],
        lw=1.0,
        color="#2ca02c",
    )
    events = result.features.events
    if events is not None and events.initial_contact_s is not None:
        offset = trial.sync.xsens_offset_s if trial.sync else 0.0
        ax.axvline(
            events.initial_contact_s - offset, color="#d62728", ls="--", lw=1,
            label="Initial contact",
        )
        ax.legend(fontsize=7)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Knee flexion (deg)")
    ax.set_title(f"{result.trial_id} — knee flexion")
    fig.tight_layout()
    path = out_dir / f"{result.trial_id}_knee.png"
    fig.savefig(path, dpi=_DPI)
    plt.close(fig)
    return path
