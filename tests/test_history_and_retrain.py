"""Tests for DB migration, history queries, and condition-model retraining."""

import sqlite3
from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import MLError
from biomech_analyzer.core.pipeline import AnalysisPipeline
from biomech_analyzer.ml.retrain import retrain_condition_model
from biomech_analyzer.storage.sqlite_repository import SqliteRepository


@pytest.fixture(scope="module")
def populated_db(mock_data_dir: Path, config, tmp_path_factory) -> Path:
    """A database holding analyses for P001-P003 (mock data)."""
    db = tmp_path_factory.mktemp("db") / "results.sqlite3"
    pipeline = AnalysisPipeline(config)
    with SqliteRepository(db) as repo:
        for pid in ("P001", "P002", "P003"):
            result = pipeline.analyze(mock_data_dir / pid)
            repo.save_participant_result(result)
    return db


def test_overall_risk_stored_and_listed(populated_db: Path):
    with SqliteRepository(populated_db) as repo:
        rows = repo.list_analyses()
    assert len(rows) == 3
    assert all(r["overall_risk"] in ("LOW", "MODERATE", "HIGH") for r in rows)


def test_update_report_path(populated_db: Path, tmp_path: Path):
    fake_report = tmp_path / "r.pdf"
    with SqliteRepository(populated_db) as repo:
        first_id = repo.list_analyses()[-1]["id"]
        repo.update_report_path(first_id, fake_report, overall_risk="HIGH")
        row = next(r for r in repo.list_analyses() if r["id"] == first_id)
    assert row["report_path"] == str(fake_report)
    assert row["overall_risk"] == "HIGH"


def test_latest_feature_rows_deduplicates_reanalyses(
    populated_db: Path, mock_data_dir: Path, config
):
    pipeline = AnalysisPipeline(config)
    result = pipeline.analyze(mock_data_dir / "P001")
    with SqliteRepository(populated_db) as repo:
        repo.save_participant_result(result)  # P001 now has two analyses
        rows = repo.latest_feature_rows()
    # only one analysis per participant contributes
    p001_trials = {r["trial_id"] for r in rows if r["participant_id"] == "P001"}
    assert len(p001_trials) == 6
    participants = {r["participant_id"] for r in rows}
    assert participants == {"P001", "P002", "P003"}


def test_migration_adds_overall_risk_column(tmp_path: Path):
    # Simulate a pre-upgrade database without the overall_risk column.
    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE analyses (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " participant_id TEXT NOT NULL, analysis_timestamp TEXT NOT NULL,"
        " folder TEXT NOT NULL, report_path TEXT,"
        " warnings_json TEXT NOT NULL DEFAULT '[]', ml_output_json TEXT)"
    )
    conn.execute(
        "INSERT INTO analyses (participant_id, analysis_timestamp, folder)"
        " VALUES ('P999', 'x', 'y')"
    )
    conn.commit()
    conn.close()
    with SqliteRepository(db) as repo:
        rows = repo.list_analyses()
    assert rows[0]["participant_id"] == "P999"
    assert rows[0]["overall_risk"] == "LOW"  # migrated default


def test_retrain_condition_model(populated_db: Path, config, tmp_path: Path):
    out = tmp_path / "condition.joblib"
    result = retrain_condition_model(populated_db, config, out)
    assert out.is_file()
    assert result.n_participants == 3
    assert result.n_trials >= 15
    # labels are the three experimental conditions
    assert set(result.output.model.classes_) == {"baseline", "upright", "cognitive"}
    # honest framing: exploratory + condition-model warnings attached
    joined = " ".join(result.output.evaluation.warnings)
    assert "exploratory" in joined
    assert "Condition-classification" in joined


def test_retrain_requires_history(tmp_path: Path, config):
    db = tmp_path / "empty.sqlite3"
    with SqliteRepository(db):
        pass  # creates empty schema
    with pytest.raises(MLError):
        retrain_condition_model(db, config)
