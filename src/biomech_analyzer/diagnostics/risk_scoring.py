"""Rule-based biomechanical risk indicators.

The primary interpretable diagnostic-support layer of the platform. Rules
are fully configuration-driven (``config/risk_thresholds.yaml``): each rule
names a feature, a direction, and either an absolute threshold or a
baseline z-score threshold. Every result carries its validation status so
that placeholder thresholds are never mistaken for validated clinical
criteria. No output constitutes a medical diagnosis.
"""

from __future__ import annotations

import logging
from typing import Any

from biomech_analyzer.core.constants import VALIDATION_PENDING, RiskLevel
from biomech_analyzer.core.models import (
    BaselineComparison,
    RiskIndicatorResult,
    TrialFeatures,
)

log = logging.getLogger(__name__)


def _z_for(feature: str, comparisons: list[BaselineComparison]) -> float | None:
    for c in comparisons:
        if c.feature == feature:
            return c.z_score
    return None


def evaluate_risk_rules(
    features: TrialFeatures,
    comparisons: list[BaselineComparison],
    rules: list[dict[str, Any]],
) -> list[RiskIndicatorResult]:
    """Evaluate every configured rule against one trial's features.

    Rules whose feature is absent are reported as not-triggered with an
    explanatory reference so reports show *why* an indicator was skipped.
    """
    results: list[RiskIndicatorResult] = []
    for rule in rules:
        rid = str(rule.get("id", "unnamed_rule"))
        name = str(rule.get("name", rid))
        feature = str(rule.get("feature", ""))
        direction = str(rule.get("direction", "above")).lower()
        explanation = " ".join(str(rule.get("explanation", "")).split())
        validation = str(rule.get("validation_status", VALIDATION_PENDING))
        try:
            level = RiskLevel(str(rule.get("risk_level", "LOW")).upper())
        except ValueError:
            log.warning("Rule %s has invalid risk_level; defaulting to LOW", rid)
            level = RiskLevel.LOW

        observed = features.value(feature)
        abs_thr = rule.get("threshold")
        z_thr = rule.get("zscore_threshold")

        triggered = False
        reference = ""
        if observed is None:
            reference = f"feature '{feature}' not available for this trial"
        elif z_thr is not None:
            z = _z_for(feature, comparisons)
            if z is None:
                reference = (
                    f"z-score threshold {z_thr:+g} (no baseline entry; rule skipped)"
                )
            else:
                z_thr_f = float(z_thr)
                triggered = z >= z_thr_f if z_thr_f >= 0 else z <= z_thr_f
                # direction still applies for sign interpretation
                if direction == "below" and z_thr_f > 0:
                    triggered = z <= -z_thr_f
                reference = f"baseline z-score {z:+.2f} vs threshold {z_thr_f:+g}"
        elif abs_thr is not None:
            thr = float(abs_thr)
            triggered = observed > thr if direction == "above" else observed < thr
            reference = f"threshold {thr:g} ({direction})"
        else:
            reference = "rule has no threshold configured; skipped"

        results.append(
            RiskIndicatorResult(
                indicator_id=rid,
                name=name,
                feature=feature,
                observed_value=observed,
                reference=reference,
                triggered=triggered,
                risk_level=level if triggered else RiskLevel.NONE,
                explanation=explanation,
                validation_status=validation,
            )
        )
    n_triggered = sum(1 for r in results if r.triggered)
    log.info(
        "Risk rules evaluated for %s: %d/%d triggered",
        features.trial_id,
        n_triggered,
        len(results),
    )
    return results
