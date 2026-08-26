"""Comparison of extracted features against the normative baseline dataset.

Kept strictly separate from risk scoring: this module only quantifies how a
participant's value relates to the normative distribution (z-score and a
plain-language interpretation); it assigns no risk.
"""

from __future__ import annotations

import logging

from biomech_analyzer.core.models import BaselineComparison, TrialFeatures
from biomech_analyzer.io.baseline_loader import BaselineDataset

log = logging.getLogger(__name__)

#: |z| bands for the plain-language interpretation.
_BANDS = (
    (1.0, "within the baseline range"),
    (2.0, "moderately {direction} the baseline range"),
    (float("inf"), "markedly {direction} the baseline range"),
)


def _interpret(z: float) -> str:
    direction = "above" if z > 0 else "below"
    for limit, template in _BANDS:
        if abs(z) < limit:
            return template.format(direction=direction)
    return "outside the baseline range"


def compare_with_baseline(
    features: TrialFeatures, baseline: BaselineDataset
) -> list[BaselineComparison]:
    """Compare every extracted feature that has a baseline entry."""
    comparisons: list[BaselineComparison] = []
    for name, fv in features.features.items():
        entry = baseline.lookup(
            name, task=features.task.value, condition=features.condition.value
        )
        if entry is None:
            continue
        if entry.std > 0:
            z = (fv.value - entry.mean) / entry.std
            interpretation = _interpret(z)
        else:
            z = None
            interpretation = "baseline SD is zero; z-score unavailable"
        comparisons.append(
            BaselineComparison(
                feature=name,
                participant_value=fv.value,
                baseline_mean=entry.mean,
                baseline_std=entry.std,
                z_score=z,
                interpretation=interpretation,
                unit=fv.unit,
            )
        )
    missing = [n for n in features.features if not any(c.feature == n for c in comparisons)]
    if missing:
        log.debug(
            "%d feature(s) had no baseline entry: %s",
            len(missing),
            ", ".join(sorted(missing)),
        )
    return comparisons
