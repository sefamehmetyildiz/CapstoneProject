from pathlib import Path

import pytest

from biomech_analyzer.core.pipeline import AnalysisPipeline
from biomech_analyzer.storage.sqlite_repository import SqliteRepository


@pytest.fixture(scope="module")
def p001_result(p001: Path, config, mock_data_dir: Path):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    return pipeline.analyze(p001)


def test_save_and_query(p001_result, tmp_path: Path):
    db = tmp_path / "results.sqlite3"
    with SqliteRepository(db) as repo:
        analysis_id = repo.save_participant_result(p001_result)
        analyses = repo.list_analyses()
        assert len(analyses) == 1
        assert analyses[0]["participant_id"] == "P001"
        feats = repo.features_for_analysis(analysis_id)
        assert feats
        names = {f["name"] for f in feats}
        assert "peak_vgrf_bw" in names
        # anonymization: no personal-data columns exist in the schema
        cols = {f.lower() for f in feats[0].keys()}
        assert "name" in cols  # feature name only
        assert not {"participant_name", "national_id", "email"} & cols


def test_reopen_appends(p001_result, tmp_path: Path):
    db = tmp_path / "re.sqlite3"
    with SqliteRepository(db) as repo:
        repo.save_participant_result(p001_result)
    with SqliteRepository(db) as repo:
        repo.save_participant_result(p001_result)
        assert len(repo.list_analyses()) == 2
