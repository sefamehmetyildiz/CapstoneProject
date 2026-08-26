from pathlib import Path

import pytest

from biomech_analyzer.core.pipeline import AnalysisPipeline
from biomech_analyzer.reporting.pdf_report import generate_pdf_report


@pytest.fixture(scope="module")
def p001_result(p001: Path, config, mock_data_dir: Path):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    return pipeline.analyze(p001)


def test_pdf_generated(p001_result, tmp_path: Path):
    path = generate_pdf_report(p001_result, tmp_path)
    assert path.is_file()
    assert path.name == "P001_biomech_report.pdf"
    content = path.read_bytes()
    assert content.startswith(b"%PDF")
    assert len(content) > 20_000  # plots embedded


def test_pdf_without_plots(p001_result, tmp_path: Path):
    path = generate_pdf_report(p001_result, tmp_path / "np", include_plots=False)
    assert path.is_file()
    assert path.stat().st_size > 1000


def test_pdf_for_imperfect_participant(p003, config, mock_data_dir, tmp_path: Path):
    pipeline = AnalysisPipeline(
        config, baseline_path=mock_data_dir / "baseline" / "normative_baseline.csv"
    )
    result = pipeline.analyze(p003)
    path = generate_pdf_report(result, tmp_path, include_plots=False)
    assert path.is_file()
