"""Comparison of extracted features against literature reference profiles.

Per the Biomedical Engineering advisor's guidance, values are not turned
into arbitrary injury-risk scores. Each feature with a literature reference
(``config/reference_profiles.yaml``) is compared against a healthy Control
profile and an ACLR-involved-limb profile (both mean +/- SD); the report
states which profile the value is closer to and groups features by body
region (knee / hip / ankle / global).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from biomech_analyzer.core.config import _config_root  # shared root resolver
from biomech_analyzer.core.constants import RiskLevel
from biomech_analyzer.core.exceptions import ConfigError
from biomech_analyzer.core.models import ProfileComparison, TrialFeatures

log = logging.getLogger(__name__)

DEFAULT_PROFILES_PATH = _config_root() / "config" / "reference_profiles.yaml"

#: Region assignment for features without a literature reference entry
#: (used only for regional grouping in reports).
REGION_BY_FEATURE: dict[str, str] = {
    "peak_knee_flexion_deg": "knee",
    "knee_rom_deg": "knee",
    "knee_frontal_rom_deg": "knee",
    "hq_activation_ratio": "knee",
    "quad_onset_latency_s": "knee",
    "peak_hip_flexion_deg": "hip",
    "peak_ankle_dorsiflexion_deg": "ankle",
    "peak_vgrf_n": "global",
    "peak_vgrf_bw": "global",
    "rfd_n_per_s": "global",
    "jump_height_m": "global",
    "flight_time_s": "global",
    "contact_time_s": "global",
    "peak_force_time_pct": "global",
    "rsi": "global",
    "time_to_stabilization_s": "global",
    "landing_impulse_ns": "global",
    "cop_path_length_m": "global",
    "ssc_spring_correlation": "global",
    "preactivation_ratio": "global",
    "landing_emg_rms_mean": "global",
}

REGIONS = ("knee", "hip", "ankle", "global")


class ReferenceProfiles:
    """Loaded literature reference profiles with scoped lookup."""

    def __init__(self, entries: list[dict[str, Any]], sources: dict[str, str]) -> None:
        self.entries = entries
        self.sources = sources

    def lookup(self, feature: str, task: str) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for entry in self.entries:
            if str(entry.get("feature")) != feature:
                continue
            entry_task = str(entry.get("task", "ALL")).upper()
            if entry_task == task.upper():
                return entry
            if entry_task == "ALL" and best is None:
                best = entry
        return best


def load_reference_profiles(path: Path | None = None) -> ReferenceProfiles:
    """Load ``config/reference_profiles.yaml``."""
    path = Path(path) if path is not None else DEFAULT_PROFILES_PATH
    if not path.is_file():
        raise ConfigError(f"Reference profiles file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    entries = data.get("references")
    if not isinstance(entries, list):
        raise ConfigError("reference_profiles.yaml must contain a 'references' list.")
    sources = {str(k): str(v).strip() for k, v in (data.get("sources") or {}).items()}
    return ReferenceProfiles(entries, sources)


def compare_with_profiles(
    features: TrialFeatures, profiles: ReferenceProfiles
) -> list[ProfileComparison]:
    """Compare every referenced feature against the Control/ACLR profiles."""
    comparisons: list[ProfileComparison] = []
    for name, fv in features.features.items():
        entry = profiles.lookup(name, features.task.value)
        if entry is None:
            continue
        try:
            c_mean = float(entry["control"]["mean"])
            c_sd = float(entry["control"]["sd"])
            a_mean = float(entry["aclr"]["mean"])
            a_sd = float(entry["aclr"]["sd"])
        except (KeyError, TypeError, ValueError):
            log.warning("Malformed reference entry for %s; skipped", name)
            continue
        if c_sd <= 0 or a_sd <= 0:
            continue
        z_control = (fv.value - c_mean) / c_sd
        z_aclr = (fv.value - a_mean) / a_sd
        if abs(z_control) <= 1.0 and abs(z_control) <= abs(z_aclr):
            closer = "control"
        elif abs(z_aclr) <= 1.0 and abs(z_aclr) < abs(z_control):
            closer = "aclr"
        elif abs(abs(z_control) - abs(z_aclr)) < 0.25:
            closer = "between"
        else:
            closer = "control" if abs(z_control) < abs(z_aclr) else "aclr"
        comparisons.append(
            ProfileComparison(
                feature=name,
                region=str(entry.get("region", REGION_BY_FEATURE.get(name, "global"))),
                unit=str(entry.get("unit", fv.unit)),
                value=fv.value,
                control_mean=c_mean,
                control_sd=c_sd,
                z_control=z_control,
                aclr_mean=a_mean,
                aclr_sd=a_sd,
                z_aclr=z_aclr,
                closer_to=closer,
                source=str(entry.get("source", "")),
            )
        )
    return comparisons


def region_status(
    comparisons: list[ProfileComparison],
) -> dict[str, RiskLevel]:
    """Aggregate profile comparisons into a colour-codable status per region.

    A region is HIGH when a feature deviates strongly from the control
    profile (|z_control| >= 2) while sitting closer to the ACLR profile,
    MODERATE when it deviates moderately (|z| >= 1) or matches the ACLR
    profile better, LOW otherwise. Regions without any referenced feature
    are omitted. Presentation aid only; PENDING_BME_VALIDATION.
    """
    status: dict[str, RiskLevel] = {}
    for comp in comparisons:
        level = RiskLevel.LOW
        if abs(comp.z_control) >= 2.0 and comp.closer_to == "aclr":
            level = RiskLevel.HIGH
        elif abs(comp.z_control) >= 1.0 or comp.closer_to == "aclr":
            level = RiskLevel.MODERATE
        current = status.get(comp.region, RiskLevel.LOW)
        order = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH]
        if order.index(level) > order.index(current):
            status[comp.region] = level
        else:
            status.setdefault(comp.region, current)
    return status
