from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import BaselineError
from biomech_analyzer.io.baseline_loader import load_baseline


def test_load_mock_baseline(mock_data_dir: Path):
    ds = load_baseline(mock_data_dir / "baseline" / "normative_baseline.csv")
    assert "peak_vgrf_bw" in ds.feature_names
    entry = ds.lookup("peak_vgrf_bw")
    assert entry is not None
    assert entry.mean == pytest.approx(2.6)


def test_scoped_lookup(mock_data_dir: Path):
    ds = load_baseline(mock_data_dir / "baseline" / "normative_baseline.csv")
    # rsi is scoped to SLDJ only in the mock baseline
    assert ds.lookup("rsi", task="SLDJ") is not None
    assert ds.lookup("rsi", task="SLVJ") is None


def test_missing_file():
    with pytest.raises(BaselineError):
        load_baseline(Path("does_not_exist.csv"))


def test_missing_columns(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("feature,average\nx,1\n", encoding="utf-8")
    with pytest.raises(BaselineError) as exc:
        load_baseline(p)
    assert "missing required" in str(exc.value).lower()


def test_bad_rows_skipped(tmp_path: Path):
    p = tmp_path / "mixed.csv"
    p.write_text("feature,mean,std\ngood,1.0,0.5\nbad,not_a_number,0.1\n", encoding="utf-8")
    ds = load_baseline(p)
    assert ds.feature_names == ["good"]
