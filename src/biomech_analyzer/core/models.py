"""Standardized internal data models shared by every pipeline stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from biomech_analyzer.core.constants import Condition, Modality, RiskLevel, Task

# ---------------------------------------------------------------------------
# Input discovery / validation
# ---------------------------------------------------------------------------


@dataclass
class TrialFile:
    """A single data file assigned to a trial."""

    path: Path
    modality: Modality


@dataclass
class TrialPackage:
    """One (task, condition) trial with its (up to three) modality files."""

    task: Task
    condition: Condition
    files: dict[Modality, TrialFile] = field(default_factory=dict)

    @property
    def trial_id(self) -> str:
        return f"{self.task.value}_{self.condition.value}"

    @property
    def missing_modalities(self) -> list[Modality]:
        return [m for m in Modality if m not in self.files]

    @property
    def is_complete(self) -> bool:
        return not self.missing_modalities


@dataclass
class FolderValidationReport:
    """Outcome of scanning and validating a participant folder."""

    participant_id: str
    folder: Path
    trials: list[TrialPackage] = field(default_factory=list)
    unmatched_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def complete_trials(self) -> list[TrialPackage]:
        return [t for t in self.trials if t.is_complete]

    @property
    def is_analyzable(self) -> bool:
        """At least one trial has a force plate file (the temporal anchor)."""
        return any(Modality.FORCE_PLATE in t.files for t in self.trials)

    def summary_lines(self) -> list[str]:
        lines = [f"Participant: {self.participant_id}", f"Folder: {self.folder}"]
        lines.append(f"Trials detected: {len(self.trials)}")
        for t in sorted(self.trials, key=lambda x: x.trial_id):
            status = "OK" if t.is_complete else (
                "missing: " + ", ".join(m.value for m in t.missing_modalities)
            )
            lines.append(f"  {t.trial_id}: {status}")
        if self.unmatched_files:
            lines.append("Unmatched files:")
            lines.extend(f"  {p.name}" for p in self.unmatched_files)
        lines.extend(f"ERROR: {e}" for e in self.errors)
        lines.extend(f"WARNING: {w}" for w in self.warnings)
        return lines


# ---------------------------------------------------------------------------
# Parsed data
# ---------------------------------------------------------------------------


@dataclass
class ForcePlateData:
    """Parsed force plate recording (canonical units: seconds, newtons, metres)."""

    time_s: np.ndarray
    fz_n: np.ndarray
    fx_n: np.ndarray | None = None
    fy_n: np.ndarray | None = None
    cop_x_m: np.ndarray | None = None
    cop_y_m: np.ndarray | None = None
    sampling_rate_hz: float = 0.0
    source_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class EmgData:
    """Parsed sEMG recording with one signal per channel."""

    time_s: np.ndarray
    channels: dict[str, np.ndarray]
    sampling_rate_hz: float
    mvic: dict[str, float] = field(default_factory=dict)
    source_path: Path | None = None
    mat_version: str = "unknown"
    warnings: list[str] = field(default_factory=list)


@dataclass
class XsensData:
    """Parsed Xsens MVNX kinematics (joint angle time series, degrees)."""

    time_s: np.ndarray
    joint_angles_deg: dict[str, np.ndarray]
    sampling_rate_hz: float
    source_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SyncInfo:
    """How the three modalities were aligned to the force plate time base."""

    strategy: str  # "timestamp" | "event" | "none"
    emg_offset_s: float = 0.0
    xsens_offset_s: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class TrialData:
    """All parsed (and later synchronized) data for one trial."""

    package: TrialPackage
    force_plate: ForcePlateData | None = None
    emg: EmgData | None = None
    xsens: XsensData | None = None
    sync: SyncInfo | None = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Events / features
# ---------------------------------------------------------------------------


@dataclass
class EventSet:
    """Detected biomechanical events on the force-plate time base (seconds)."""

    initial_contact_s: float | None = None
    takeoff_s: float | None = None
    peak_force_s: float | None = None
    peak_force_n: float | None = None
    stabilization_s: float | None = None
    body_weight_n: float | None = None
    flight_time_s: float | None = None
    contact_time_s: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class FeatureValue:
    """A single extracted feature with provenance metadata."""

    name: str
    value: float
    unit: str
    modality: Modality
    validation_status: str
    description: str = ""


@dataclass
class TrialFeatures:
    """Feature set extracted from one trial."""

    trial_id: str
    task: Task
    condition: Condition
    features: dict[str, FeatureValue] = field(default_factory=dict)
    events: EventSet | None = None
    warnings: list[str] = field(default_factory=list)

    def value(self, name: str) -> float | None:
        fv = self.features.get(name)
        return fv.value if fv is not None else None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@dataclass
class BaselineComparison:
    """Comparison of one feature value against the normative baseline."""

    feature: str
    participant_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float | None
    interpretation: str
    unit: str = ""


@dataclass
class RiskIndicatorResult:
    """One triggered (or evaluated) rule-based risk indicator."""

    indicator_id: str
    name: str
    feature: str
    observed_value: float | None
    reference: str
    triggered: bool
    risk_level: RiskLevel
    explanation: str
    validation_status: str


@dataclass
class TrialResult:
    """Full analysis outcome for a single trial."""

    trial_id: str
    task: Task
    condition: Condition
    features: TrialFeatures
    baseline_comparisons: list[BaselineComparison] = field(default_factory=list)
    risk_indicators: list[RiskIndicatorResult] = field(default_factory=list)
    sync: SyncInfo | None = None
    warnings: list[str] = field(default_factory=list)
    #: Parsed/preprocessed signals kept for plotting; not persisted to storage.
    data: TrialData | None = None


@dataclass
class ParticipantResult:
    """Full analysis outcome for a participant folder."""

    participant_id: str
    folder: Path
    validation: FolderValidationReport
    trials: list[TrialResult] = field(default_factory=list)
    ml_output: dict[str, Any] | None = None
    analysis_timestamp: str = ""
    report_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
