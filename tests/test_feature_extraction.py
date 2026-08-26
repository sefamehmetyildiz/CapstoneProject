from pathlib import Path

import pytest

from biomech_analyzer.core.constants import VALIDATION_PENDING
from biomech_analyzer.core.pipeline import AnalysisPipeline


@pytest.fixture(scope="module")
def p001_result(p001: Path, config, mock_data_dir: Path):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    return pipeline.analyze(p001)


def test_all_six_trials_analyzed(p001_result):
    assert len(p001_result.trials) == 6


def test_force_plate_features_present(p001_result):
    trial = p001_result.trials[0]
    f = trial.features
    for name in (
        "peak_vgrf_n",
        "peak_vgrf_bw",
        "rfd_n_per_s",
        "flight_time_s",
        "jump_height_m",
        "time_to_stabilization_s",
        "landing_impulse_ns",
        "cop_path_length_m",
    ):
        assert name in f.features, f"missing {name}"
    assert f.features["peak_vgrf_bw"].value == pytest.approx(2.8, abs=0.6)
    assert f.features["peak_vgrf_bw"].validation_status == VALIDATION_PENDING


def test_emg_features_present(p001_result):
    f = p001_result.trials[0].features
    assert "preactivation_ratio" in f.features
    assert "hq_activation_ratio" in f.features
    assert "landing_emg_rms_mean" in f.features
    assert 0 <= f.features["preactivation_ratio"].value <= 1


def test_xsens_features_present(p001_result):
    f = p001_result.trials[0].features
    assert "peak_knee_flexion_deg" in f.features
    assert f.features["peak_knee_flexion_deg"].value > 30
    assert "knee_rom_deg" in f.features
    assert "knee_frontal_rom_deg" in f.features


def test_baseline_comparisons_and_zscores(p001_result):
    trial = p001_result.trials[0]
    assert trial.baseline_comparisons
    by_name = {c.feature: c for c in trial.baseline_comparisons}
    assert "peak_vgrf_bw" in by_name
    c = by_name["peak_vgrf_bw"]
    assert c.z_score == pytest.approx((c.participant_value - 2.6) / 0.4, abs=1e-6)
    assert c.interpretation


def test_risk_indicators_evaluated(p001_result):
    trial = p001_result.trials[0]
    assert trial.risk_indicators
    for ind in trial.risk_indicators:
        assert ind.validation_status == VALIDATION_PENDING
        assert ind.reference  # every rule explains its reference/skip reason


def test_imperfect_participant_degrades_gracefully(p003, config, mock_data_dir):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    result = pipeline.analyze(p003)
    # SLVJ_upright lost its force file (unclassifiable name) -> 5 analyzable
    trial_ids = {t.trial_id for t in result.trials}
    assert "SLVJ_upright" not in trial_ids
    assert len(result.trials) == 5
    # SLDJ_cognitive has no EMG: analyzed, but with warnings and no EMG features
    sldj_cog = next(t for t in result.trials if t.trial_id == "SLDJ_cognitive")
    assert "preactivation_ratio" not in sldj_cog.features.features
    assert any("emg" in w.lower() for w in sldj_cog.warnings)
