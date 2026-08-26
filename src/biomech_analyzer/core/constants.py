"""Project-wide constants and controlled vocabularies."""

from __future__ import annotations

from enum import Enum


class Task(str, Enum):
    """Jump task types defined by the experimental protocol."""

    SLVJ = "SLVJ"  # Single-Leg Vertical Jump
    SLDJ = "SLDJ"  # Single-Leg Drop Jump


class Condition(str, Enum):
    """Experimental landing conditions."""

    BASELINE = "baseline"
    UPRIGHT = "upright"
    COGNITIVE = "cognitive"


class Modality(str, Enum):
    """Data acquisition modalities."""

    FORCE_PLATE = "force_plate"
    EMG = "emg"
    XSENS = "xsens"


class RiskLevel(str, Enum):
    """Ordinal risk labels used by rule-based indicators."""

    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


#: File extensions accepted per modality. ".csv" is ambiguous (Bertec force
#: exports and Delsys EMG exports both use it) and is resolved by keywords
#: and content sniffing in the trial matcher.
MODALITY_EXTENSIONS: dict[Modality, tuple[str, ...]] = {
    Modality.FORCE_PLATE: (".csv",),
    Modality.EMG: (".mat", ".csv"),
    Modality.XSENS: (".mvnx",),
}

#: Case-insensitive filename keywords that hint at a modality.
MODALITY_KEYWORDS: dict[Modality, tuple[str, ...]] = {
    Modality.FORCE_PLATE: ("force", "fp", "grf", "bertec", "plate"),
    Modality.EMG: ("emg", "delsys", "trigno", "semg"),
    Modality.XSENS: ("xsens", "mvnx", "imu", "mvn"),
}

#: Case-insensitive filename keywords per task.
TASK_KEYWORDS: dict[Task, tuple[str, ...]] = {
    Task.SLVJ: ("slvj", "vertical", "vj"),
    Task.SLDJ: ("sldj", "drop", "dj"),
}

#: Case-insensitive filename keywords per condition.
CONDITION_KEYWORDS: dict[Condition, tuple[str, ...]] = {
    # "correct"/"corect" appear in real exports as the natural-form trial.
    Condition.BASELINE: ("baseline", "natural", "base", "correct", "corect"),
    Condition.UPRIGHT: ("upright", "trunk", "erect"),
    Condition.COGNITIVE: ("cognitive", "dualtask", "dual_task", "dual-task", "dt", "cog"),
}

#: The six expected trial packages per participant.
EXPECTED_TRIALS: tuple[tuple[Task, Condition], ...] = tuple(
    (task, condition) for task in Task for condition in Condition
)

VALIDATION_PENDING = "PENDING_BME_VALIDATION"
VALIDATION_OK = "VALIDATED"
