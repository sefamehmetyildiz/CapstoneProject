from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import MLError
from biomech_analyzer.core.pipeline import AnalysisPipeline
from biomech_analyzer.ml.dataset_builder import build_feature_table, load_labels, split_xy
from biomech_analyzer.ml.inference import predict_participant
from biomech_analyzer.ml.train import export_model, load_model_bundle, train_and_evaluate


@pytest.fixture(scope="module")
def analyzed_participants(mock_data_dir: Path, config):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    return [pipeline.analyze(mock_data_dir / pid) for pid in ("P001", "P002", "P003")]


def test_load_labels(mock_data_dir: Path):
    labels = load_labels(mock_data_dir / "baseline" / "labels.csv")
    assert labels["P001"] == "low_risk"
    assert labels["P002"] == "high_risk"


def test_labels_missing_file():
    with pytest.raises(MLError):
        load_labels(Path("nope.csv"))


def test_feature_table(analyzed_participants, mock_data_dir: Path):
    labels = load_labels(mock_data_dir / "baseline" / "labels.csv")
    table = build_feature_table(analyzed_participants, labels)
    # P001/P002: 6 trials each, P003: 5 analyzable
    assert len(table) == 17
    assert "peak_vgrf_bw" in table.columns
    assert table["label"].notna().all()


def test_train_evaluate_export_roundtrip(
    analyzed_participants, mock_data_dir: Path, config, tmp_path: Path
):
    labels = load_labels(mock_data_dir / "baseline" / "labels.csv")
    table = build_feature_table(analyzed_participants, labels)
    x, y, groups = split_xy(table)
    output = train_and_evaluate(x, y, groups, config)
    # 3 participants -> exploratory warning must be present
    assert any("exploratory" in w for w in output.evaluation.warnings)
    assert 0.0 <= output.evaluation.accuracy <= 1.0
    assert output.feature_importances

    model_path = tmp_path / "model.joblib"
    export_model(output, model_path)
    bundle = load_model_bundle(model_path)
    assert bundle["feature_columns"] == output.feature_columns

    ml_out = predict_participant(analyzed_participants[0], model_path)
    assert ml_out["majority_prediction"] in ("low_risk", "high_risk")
    assert len(ml_out["trials"]) == 6
    assert any("Exploratory" in w for w in ml_out["warnings"])


def test_split_requires_labels(analyzed_participants):
    table = build_feature_table(analyzed_participants, labels={})
    with pytest.raises(MLError):
        split_xy(table)


def test_load_model_bad_file(tmp_path: Path):
    p = tmp_path / "bad.joblib"
    p.write_bytes(b"junk")
    with pytest.raises(MLError):
        load_model_bundle(p)
