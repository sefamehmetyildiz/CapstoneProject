from pathlib import Path

import numpy as np
import pytest

from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.io.force_plate_csv_parser import parse_force_plate_csv


def test_parse_mock_file(p001: Path, config):
    data = parse_force_plate_csv(p001 / "SLVJ_baseline_force.csv", config)
    assert data.sampling_rate_hz == pytest.approx(1000.0, rel=0.01)
    assert data.fz_n.size == 5000
    assert data.cop_x_m is not None
    # metadata header rows were skipped
    assert any("metadata" in w.lower() for w in data.warnings)
    # flight phase exists (Fz ~ 0) and landing spike exists
    assert data.fz_n.min() < 5
    assert data.fz_n.max() > 1200


def test_semicolon_delimiter_and_negative_fz(tmp_path: Path, config):
    p = tmp_path / "weird.csv"
    rows = ["Time;Force Z;Force X"]
    for i in range(200):
        rows.append(f"{i / 500:.4f};{-700 - i % 5};{1.0}")
    p.write_text("\n".join(rows), encoding="utf-8")
    data = parse_force_plate_csv(p, config)
    assert data.sampling_rate_hz == pytest.approx(500.0, rel=0.01)
    # sign convention flipped to positive-up
    assert np.median(data.fz_n) > 0
    assert any("sign" in w.lower() for w in data.warnings)


def test_missing_fz_column(tmp_path: Path, config):
    p = tmp_path / "nofz.csv"
    p.write_text("Time,Pressure\n0.0,1.2\n0.001,1.3\n", encoding="utf-8")
    with pytest.raises(ParseError) as exc:
        parse_force_plate_csv(p, config)
    assert "Fz" in str(exc.value)


def test_no_time_column_uses_config_rate(tmp_path: Path, config):
    p = tmp_path / "notime.csv"
    lines = ["Fz (N),Fx (N)"] + [f"{700 + i % 3},0.0" for i in range(100)]
    p.write_text("\n".join(lines), encoding="utf-8")
    data = parse_force_plate_csv(p, config)
    assert data.sampling_rate_hz == 1000.0
    assert any("assumed" in w.lower() for w in data.warnings)


def test_empty_file(tmp_path: Path, config):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_force_plate_csv(p, config)


def test_non_numeric_cells_interpolated(tmp_path: Path, config):
    p = tmp_path / "gaps.csv"
    lines = ["Time (s),Fz (N)"]
    for i in range(100):
        val = "" if i == 50 else f"{700.0 + i % 2}"
        lines.append(f"{i / 1000:.4f},{val}")
    p.write_text("\n".join(lines), encoding="utf-8")
    data = parse_force_plate_csv(p, config)
    assert not np.isnan(data.fz_n).any()
