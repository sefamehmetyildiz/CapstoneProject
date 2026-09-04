"""Tests for literature profile comparison, overall risk, and TR reports."""

from pathlib import Path

import pytest

from biomech_analyzer.core.constants import Condition, Modality, RiskLevel, Task
from biomech_analyzer.core.models import FeatureValue, RiskIndicatorResult, TrialFeatures
from biomech_analyzer.core.pipeline import AnalysisPipeline
from biomech_analyzer.diagnostics.overall_risk import (
    load_overall_config,
    participant_risk_level,
    trial_risk_level,
)
from biomech_analyzer.diagnostics.profile_comparison import (
    compare_with_profiles,
    load_reference_profiles,
    region_status,
)
from biomech_analyzer.diagnostics.risk_scoring import evaluate_risk_rules
from biomech_analyzer.reporting.i18n import risk_label, tr


def _features(task: Task = Task.SLDJ, **values: float) -> TrialFeatures:
    tf = TrialFeatures(trial_id=f"{task.value}_baseline", task=task, condition=Condition.BASELINE)
    for name, value in values.items():
        tf.features[name] = FeatureValue(
            name=name, value=value, unit="x", modality=Modality.FORCE_PLATE,
            validation_status="PENDING_BME_VALIDATION",
        )
    return tf


# ---- profile comparison ----------------------------------------------------


def test_profiles_load_with_sources():
    profiles = load_reference_profiles()
    assert profiles.lookup("peak_vgrf_bw", "SLDJ") is not None
    assert profiles.lookup("peak_vgrf_bw", "SLVJ") is None  # SLDJ-scoped
    assert "read2022" in profiles.sources


def test_control_like_value_maps_to_control_profile():
    profiles = load_reference_profiles()
    comps = compare_with_profiles(_features(peak_vgrf_bw=3.4), profiles)
    assert len(comps) == 1
    assert comps[0].closer_to == "control"
    assert comps[0].region == "global"


def test_aclr_like_value_maps_to_aclr_profile():
    profiles = load_reference_profiles()
    comps = compare_with_profiles(_features(contact_time_s=0.41), profiles)
    assert comps[0].closer_to == "aclr"


def test_region_status_flags_strong_deviation():
    profiles = load_reference_profiles()
    # Knee flexion far below control range and closer to nothing healthy.
    comps = compare_with_profiles(_features(peak_knee_flexion_deg=30.0), profiles)
    statuses = region_status(comps)
    assert statuses["knee"] in (RiskLevel.MODERATE, RiskLevel.HIGH)


# ---- task-scoped rules -----------------------------------------------------


def test_sldj_rules_skipped_for_slvj():
    rules = [
        {
            "id": "prolonged_contact", "name": "x", "task": "SLDJ",
            "feature": "contact_time_s", "direction": "above",
            "threshold": 0.37, "risk_level": "MODERATE", "explanation": "e",
        }
    ]
    slvj = evaluate_risk_rules(_features(task=Task.SLVJ, contact_time_s=1.5), [], rules)
    assert slvj == []  # rule skipped entirely
    sldj = evaluate_risk_rules(_features(task=Task.SLDJ, contact_time_s=1.5), [], rules)
    assert sldj[0].triggered


# ---- overall risk aggregation ----------------------------------------------


def _indicator(level: RiskLevel, triggered: bool = True) -> RiskIndicatorResult:
    return RiskIndicatorResult(
        indicator_id="x", name="x", feature="f", observed_value=1.0,
        reference="r", triggered=triggered,
        risk_level=level if triggered else RiskLevel.NONE,
        explanation="e", validation_status="PENDING_BME_VALIDATION",
    )


def test_trial_risk_levels():
    cfg = load_overall_config()
    assert trial_risk_level([], cfg) is RiskLevel.LOW
    assert trial_risk_level([_indicator(RiskLevel.LOW)], cfg) is RiskLevel.MODERATE
    heavy = [_indicator(RiskLevel.MODERATE)] * 2 + [_indicator(RiskLevel.LOW)]
    assert trial_risk_level(heavy, cfg) is RiskLevel.HIGH
    assert trial_risk_level([_indicator(RiskLevel.HIGH, triggered=False)], cfg) is RiskLevel.LOW


def test_participant_risk_is_worst_trial():
    assert participant_risk_level([RiskLevel.LOW, RiskLevel.HIGH]) is RiskLevel.HIGH
    assert participant_risk_level([]) is RiskLevel.LOW


# ---- pipeline integration + Turkish report ---------------------------------


@pytest.fixture(scope="module")
def p001_result(p001: Path, config, mock_data_dir: Path):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    return pipeline.analyze(p001)


def test_pipeline_produces_profiles_and_overall_risk(p001_result):
    assert p001_result.overall_risk in (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH)
    sldj = next(t for t in p001_result.trials if t.task is Task.SLDJ)
    assert sldj.profile_comparisons  # SLDJ has literature references
    assert sldj.features.value("contact_time_s") is not None
    # SSC categorization runs on SLDJ (box-height fallback for v0)
    assert sldj.features.ssc_category in ("good", "moderate", "poor")
    slvj = next(t for t in p001_result.trials if t.task is Task.SLVJ)
    assert slvj.features.ssc_category is None  # SLDJ-only concept


def test_turkish_pdf_report(p001_result, tmp_path: Path):
    from biomech_analyzer.reporting.pdf_report import generate_pdf_report

    path = generate_pdf_report(p001_result, tmp_path, include_plots=False, language="tr")
    assert path.name == "P001_biomech_report_tr.pdf"
    assert path.read_bytes().startswith(b"%PDF")
    # English default keeps its original name
    path_en = generate_pdf_report(p001_result, tmp_path, include_plots=False)
    assert path_en.name == "P001_biomech_report.pdf"


def test_i18n_strings():
    assert tr("report.overall_risk", "tr").startswith("Genel")
    assert tr("report.overall_risk", "en").startswith("Overall")
    assert tr("missing.key", "tr") == "missing.key"
    assert risk_label(RiskLevel.HIGH, "tr") == "YÜKSEK"


def test_known_mass_used_as_bw_fallback(config, tmp_path: Path):
    # A recording with no stable contact at all: BW comes from participants
    # metadata passed through detect_events.
    import numpy as np

    from biomech_analyzer.core.models import ForcePlateData
    from biomech_analyzer.processing.event_detection import detect_events

    t = np.arange(0, 3, 0.001)
    fz = np.zeros_like(t)
    fz[(t >= 1.0) & (t < 1.2)] = 900.0  # brief spike only, never stable
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=1000.0)
    events = detect_events(fp, config, known_body_weight_n=700.0)
    assert events.body_weight_n == pytest.approx(700.0)
    assert any("anthropometrics" in w for w in events.warnings)
