from pathlib import Path

import pytest

from biomech_analyzer.cli import main


def test_validate_ok(p001: Path, capsys):
    rc = main(["validate", str(p001)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "P001" in out
    assert "SLVJ_baseline" in out


def test_validate_missing_folder(capsys):
    rc = main(["validate", "Z:/nowhere"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "ERROR" in out


def test_analyze(p001: Path, mock_data_dir: Path, capsys):
    rc = main(
        [
            "analyze",
            str(p001),
            "--baseline",
            str(mock_data_dir / "baseline" / "normative_baseline.csv"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Analysis summary" in out
    assert "decision-support" in out  # disclaimer printed


def test_report_end_to_end(p001: Path, mock_data_dir: Path, tmp_path: Path, capsys):
    rc = main(
        [
            "report",
            str(p001),
            "--baseline",
            str(mock_data_dir / "baseline" / "normative_baseline.csv"),
            "--out",
            str(tmp_path),
            "--no-plots",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert (tmp_path / "P001_biomech_report.pdf").is_file()
    assert "PDF report written" in out


@pytest.mark.slow
def test_train_end_to_end(mock_data_dir: Path, tmp_path: Path, capsys):
    rc = main(
        [
            "train",
            str(mock_data_dir),
            "--labels",
            str(mock_data_dir / "baseline" / "labels.csv"),
            "--baseline",
            str(mock_data_dir / "baseline" / "normative_baseline.csv"),
            "--model-out",
            str(tmp_path / "model.joblib"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert (tmp_path / "model.joblib").is_file()
    assert "Leave-one-subject-out" in out
    assert "exploratory" in out.lower()
