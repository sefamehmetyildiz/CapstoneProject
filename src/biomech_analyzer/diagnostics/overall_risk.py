"""Aggregation of triggered risk indicators into an overall risk level.

Used purely for colour-coded presentation (green / orange / red) in the
GUI and PDF reports — decision-support only, never a diagnosis. The
weights and score thresholds live in ``config/risk_thresholds.yaml``
under ``overall`` and are PENDING_BME_VALIDATION.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from biomech_analyzer.core.config import DEFAULT_RISK_PATH
from biomech_analyzer.core.constants import RiskLevel
from biomech_analyzer.core.models import RiskIndicatorResult

log = logging.getLogger(__name__)

_DEFAULT_OVERALL = {
    "weights": {"HIGH": 3, "MODERATE": 2, "LOW": 1},
    "moderate_min_score": 1,
    "high_min_score": 5,
}


def load_overall_config(path: Path | None = None) -> dict[str, Any]:
    """Read the ``overall`` block of risk_thresholds.yaml (with defaults)."""
    path = Path(path) if path is not None else DEFAULT_RISK_PATH
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        overall = data.get("overall") or {}
    except OSError:
        overall = {}
    merged = dict(_DEFAULT_OVERALL)
    merged.update({k: v for k, v in overall.items() if v is not None})
    return merged


def trial_risk_level(
    indicators: list[RiskIndicatorResult], overall_cfg: dict[str, Any]
) -> RiskLevel:
    """Score the triggered indicators of one trial into LOW/MODERATE/HIGH."""
    weights = overall_cfg.get("weights", _DEFAULT_OVERALL["weights"])
    score = sum(
        int(weights.get(ind.risk_level.value, 1))
        for ind in indicators
        if ind.triggered
    )
    if score >= int(overall_cfg.get("high_min_score", 5)):
        return RiskLevel.HIGH
    if score >= int(overall_cfg.get("moderate_min_score", 1)):
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def participant_risk_level(trial_levels: list[RiskLevel]) -> RiskLevel:
    """Participant level = worst trial level (LOW when no trials)."""
    order = [RiskLevel.NONE, RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH]
    worst = RiskLevel.LOW
    for level in trial_levels:
        if order.index(level) > order.index(worst):
            worst = level
    return worst
