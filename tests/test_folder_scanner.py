from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import FolderValidationError
from biomech_analyzer.io.folder_scanner import scan_participant_folder


def test_complete_participant(p001: Path):
    report = scan_participant_folder(p001)
    assert report.participant_id == "P001"
    assert len(report.trials) == 6
    assert len(report.complete_trials) == 6
    assert report.is_analyzable
    assert not report.errors


def test_imperfect_participant(p003: Path):
    report = scan_participant_folder(p003)
    # SLVJ_upright force file was renamed to something unclassifiable,
    # SLDJ_cognitive is missing its EMG file.
    assert report.unmatched_files, "cryptic file should be unmatched"
    trial_ids = {t.trial_id for t in report.trials}
    assert "SLDJ_cognitive" in trial_ids
    sldj_cog = next(t for t in report.trials if t.trial_id == "SLDJ_cognitive")
    assert not sldj_cog.is_complete
    assert any("missing" in w.lower() for w in report.warnings)
    assert report.is_analyzable  # other trials still have force data


def test_missing_folder():
    with pytest.raises(FolderValidationError):
        scan_participant_folder(Path("Z:/definitely/not/here"))


def test_empty_folder(tmp_path: Path):
    report = scan_participant_folder(tmp_path)
    assert report.errors
    assert not report.is_analyzable


def test_summary_lines(p001: Path):
    report = scan_participant_folder(p001)
    text = "\n".join(report.summary_lines())
    assert "SLVJ_baseline" in text
    assert "P001" in text
