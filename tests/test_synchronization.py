from pathlib import Path

import numpy as np
import pytest

from biomech_analyzer.core.constants import Condition, Modality, Task
from biomech_analyzer.core.exceptions import SynchronizationError
from biomech_analyzer.core.models import TrialData, TrialFile, TrialPackage
from biomech_analyzer.io.emg_mat_parser import parse_emg_mat
from biomech_analyzer.io.force_plate_csv_parser import parse_force_plate_csv
from biomech_analyzer.io.xsens_mvnx_parser import parse_xsens_mvnx
from biomech_analyzer.processing.preprocessing import preprocess_emg
from biomech_analyzer.processing.synchronization import synchronize_trial


def _trial(p001: Path, config) -> tuple[TrialData, object]:
    pkg = TrialPackage(task=Task.SLVJ, condition=Condition.BASELINE)
    pkg.files[Modality.FORCE_PLATE] = TrialFile(
        p001 / "SLVJ_baseline_force.csv", Modality.FORCE_PLATE
    )
    trial = TrialData(package=pkg)
    trial.force_plate = parse_force_plate_csv(p001 / "SLVJ_baseline_force.csv", config)
    trial.emg = parse_emg_mat(p001 / "SLVJ_baseline_emg.mat", config)
    trial.xsens = parse_xsens_mvnx(p001 / "SLVJ_baseline_xsens.mvnx", config)
    env = preprocess_emg(trial.emg, config)
    return trial, env


def test_timestamp_sync_on_consistent_streams(p001: Path, config):
    trial, env = _trial(p001, config)
    sync = synchronize_trial(trial, env, config)
    assert sync.strategy == "timestamp"
    assert sync.emg_offset_s == 0.0
    assert sync.notes


def test_event_fallback_on_skewed_streams(p001: Path, config):
    trial, env = _trial(p001, config)
    # Shift the EMG clock by 2 s: timestamp sync must be rejected.
    trial.emg.time_s = trial.emg.time_s + 2.0
    env.time_s = trial.emg.time_s
    sync = synchronize_trial(trial, env, config)
    assert sync.strategy == "event"
    # landing peaks realign: offset compensates the 2 s shift (mock signals
    # place EMG burst peak near the Fz landing peak)
    assert sync.emg_offset_s == pytest.approx(-2.0, abs=0.3)


def test_forced_timestamp_raises_on_skew(p001: Path, config):
    from biomech_analyzer.core.config import Config

    trial, env = _trial(p001, config)
    trial.emg.time_s = trial.emg.time_s + 2.0
    forced = Config(
        {**config.as_dict(), "synchronization": {"strategy": "timestamp", "max_timestamp_skew_s": 0.5}}
    )
    with pytest.raises(SynchronizationError):
        synchronize_trial(trial, env, forced)


def test_missing_force_plate_raises(config):
    pkg = TrialPackage(task=Task.SLVJ, condition=Condition.BASELINE)
    with pytest.raises(SynchronizationError):
        synchronize_trial(TrialData(package=pkg), None, config)


def test_fz_only_trial_syncs(p001: Path, config):
    pkg = TrialPackage(task=Task.SLDJ, condition=Condition.UPRIGHT)
    trial = TrialData(package=pkg)
    trial.force_plate = parse_force_plate_csv(p001 / "SLDJ_upright_force.csv", config)
    sync = synchronize_trial(trial, None, config)
    assert sync.strategy == "timestamp"
    assert np.isfinite(sync.emg_offset_s)
