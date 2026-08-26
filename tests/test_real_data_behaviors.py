"""Tests for behaviors discovered while validating against real exports."""

from pathlib import Path

import numpy as np
import pytest

from biomech_analyzer.core.constants import Condition, Modality, Task
from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.core.models import ForcePlateData
from biomech_analyzer.io.folder_scanner import _derive_anonymous_id
from biomech_analyzer.io.force_plate_csv_parser import parse_force_plate_csv
from biomech_analyzer.io.trial_matcher import classify_file
from biomech_analyzer.processing.preprocessing import preprocess_force_plate

# --- naming variants -------------------------------------------------------


def test_correct_and_corect_mean_baseline():
    assert classify_file(Path("SLVJ_corect.csv")).condition is Condition.BASELINE
    assert classify_file(Path("SLDJ_correct.csv")).condition is Condition.BASELINE


def test_uprightnew_variant():
    assert classify_file(Path("slvj_uprightnew.csv")).condition is Condition.UPRIGHT


def test_concatenated_names():
    c = classify_file(Path("sldjbcognitive.csv"))
    assert c.task is Task.SLDJ
    assert c.condition is Condition.COGNITIVE


# --- CSV modality resolution ----------------------------------------------


def test_csv_in_force_plate_folder(tmp_path: Path):
    d = tmp_path / "force plate"
    d.mkdir()
    p = d / "slvjbaseline.csv"
    p.write_text("Seq,Fx,Fy,Fz\n0,0,0,700\n", encoding="utf-8")
    assert classify_file(p).modality is Modality.FORCE_PLATE


def test_delsys_csv_detected_by_content(tmp_path: Path):
    p = tmp_path / "slvjbaseline.csv"
    p.write_text(
        "Label: R TIBIALIS ANTERIOR: EMG 2 Sampling frequency: 2.148e+003\n"
        'X[s],"R TIBIALIS ANTERIOR: EMG 2"\n0.0,0.001\n',
        encoding="utf-8",
    )
    assert classify_file(p).modality is Modality.EMG


def test_bertec_csv_defaults_to_force_plate(tmp_path: Path):
    p = tmp_path / "slvjbaseline.csv"
    p.write_text("Seq,Sync,Aux,Fx,Fy,Fz\n0,255,255,0,0,700\n", encoding="utf-8")
    assert classify_file(p).modality is Modality.FORCE_PLATE


# --- anonymous ID derivation ----------------------------------------------


def test_subject_folder_with_name_is_anonymized():
    pid, warning = _derive_anonymous_id("subject 4 sefa")
    assert pid == "S04"
    assert warning is not None and "personal" in warning.lower()


def test_subject_folder_without_name():
    pid, warning = _derive_anonymous_id("Subject 12")
    assert pid == "S12"
    assert warning is None


def test_plain_folder_name_kept():
    pid, warning = _derive_anonymous_id("P001")
    assert pid == "P001"
    assert warning is None


# --- force plate robustness ------------------------------------------------


def test_sync_aux_only_export_gives_actionable_error(tmp_path: Path, config):
    p = tmp_path / "broken.csv"
    p.write_text(
        "Sync,Aux\n" + "\n".join("255.0,255.0" for _ in range(50)), encoding="utf-8"
    )
    with pytest.raises(ParseError) as exc:
        parse_force_plate_csv(p, config)
    assert "synchronization channels" in str(exc.value)
    assert "Re-export" in exc.value.user_message


def test_mostly_empty_plate_not_sign_flipped(tmp_path: Path, config):
    # SLDJ-style recording: long empty phase (small negative noise) then a
    # positive landing. The old median rule would wrongly flip the signal.
    rng = np.random.default_rng(1)
    noise = rng.normal(-0.5, 0.4, 3000)
    lines = ["Time (s),Fz (N)"]
    lines += [f"{i / 1000:.4f},{v:.4f}" for i, v in enumerate(noise)]
    lines += [f"{(3000 + i) / 1000:.4f},800.0" for i in range(500)]
    p = tmp_path / "sldj.csv"
    p.write_text("\n".join(lines), encoding="utf-8")
    data = parse_force_plate_csv(p, config)
    assert data.fz_n.max() > 700  # not flipped
    assert not any("sign" in w.lower() for w in data.warnings)


def test_auto_zero_removes_unloaded_offset(config):
    # Plate not zeroed: empty plate reads ~41 N, stance ~741 N.
    fs = 1000.0
    t = np.arange(0, 10, 1 / fs)
    fz = np.full_like(t, 41.0)
    fz[(t >= 2) & (t < 4)] = 741.0
    fz[(t >= 4.3) & (t < 6)] = 741.0
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=fs)
    out = preprocess_force_plate(fp, config)
    assert any("offset" in w.lower() for w in out.warnings)
    # empty-plate phase now reads ~0 -> below the 20 N contact threshold
    assert float(np.median(out.fz_n[t < 2])) < 5.0


def test_auto_zero_skips_zeroed_recordings(config):
    fs = 1000.0
    t = np.arange(0, 5, 1 / fs)
    fz = np.full_like(t, 700.0)
    fz[(t >= 2) & (t < 2.4)] = 0.0
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=fs)
    out = preprocess_force_plate(fp, config)
    assert not any("offset" in w.lower() for w in out.warnings)
