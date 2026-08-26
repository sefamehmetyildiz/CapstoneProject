from biomech_analyzer.core.constants import (
    VALIDATION_PENDING,
    Condition,
    Modality,
    RiskLevel,
    Task,
)
from biomech_analyzer.core.models import (
    BaselineComparison,
    FeatureValue,
    TrialFeatures,
)
from biomech_analyzer.diagnostics.risk_scoring import evaluate_risk_rules


def _features(**values: float) -> TrialFeatures:
    tf = TrialFeatures(trial_id="SLVJ_baseline", task=Task.SLVJ, condition=Condition.BASELINE)
    for name, value in values.items():
        tf.features[name] = FeatureValue(
            name=name,
            value=value,
            unit="x",
            modality=Modality.FORCE_PLATE,
            validation_status=VALIDATION_PENDING,
        )
    return tf


def test_absolute_threshold_below():
    rules = [
        {
            "id": "stiff",
            "name": "Stiff landing",
            "feature": "peak_knee_flexion_deg",
            "direction": "below",
            "threshold": 45.0,
            "risk_level": "MODERATE",
            "explanation": "e",
        }
    ]
    triggered = evaluate_risk_rules(_features(peak_knee_flexion_deg=30.0), [], rules)
    assert triggered[0].triggered
    assert triggered[0].risk_level is RiskLevel.MODERATE
    ok = evaluate_risk_rules(_features(peak_knee_flexion_deg=60.0), [], rules)
    assert not ok[0].triggered
    assert ok[0].risk_level is RiskLevel.NONE


def test_zscore_threshold():
    rules = [
        {
            "id": "impact",
            "name": "High impact",
            "feature": "peak_vgrf_bw",
            "direction": "above",
            "zscore_threshold": 1.5,
            "risk_level": "HIGH",
            "explanation": "e",
        }
    ]
    comparisons = [
        BaselineComparison(
            feature="peak_vgrf_bw",
            participant_value=3.5,
            baseline_mean=2.6,
            baseline_std=0.4,
            z_score=2.25,
            interpretation="above",
        )
    ]
    res = evaluate_risk_rules(_features(peak_vgrf_bw=3.5), comparisons, rules)
    assert res[0].triggered
    assert "z-score" in res[0].reference


def test_negative_zscore_threshold():
    rules = [
        {
            "id": "low_rsi",
            "name": "Low RSI",
            "feature": "rsi",
            "direction": "below",
            "zscore_threshold": -1.5,
            "risk_level": "LOW",
            "explanation": "e",
        }
    ]
    comparisons = [
        BaselineComparison("rsi", 0.3, 1.1, 0.3, -2.67, "below")
    ]
    res = evaluate_risk_rules(_features(rsi=0.3), comparisons, rules)
    assert res[0].triggered


def test_missing_feature_reports_reason():
    rules = [
        {
            "id": "x",
            "name": "X",
            "feature": "not_computed",
            "threshold": 1.0,
            "risk_level": "LOW",
            "explanation": "e",
        }
    ]
    res = evaluate_risk_rules(_features(), [], rules)
    assert not res[0].triggered
    assert "not available" in res[0].reference


def test_zscore_rule_without_baseline_is_skipped():
    rules = [
        {
            "id": "x",
            "name": "X",
            "feature": "peak_vgrf_bw",
            "zscore_threshold": 1.5,
            "risk_level": "LOW",
            "explanation": "e",
        }
    ]
    res = evaluate_risk_rules(_features(peak_vgrf_bw=3.0), [], rules)
    assert not res[0].triggered
    assert "no baseline" in res[0].reference
