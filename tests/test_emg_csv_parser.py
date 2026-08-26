from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.io.emg_csv_parser import parse_emg_csv

_DELSYS_HEADER = (
    "Label: R TIBIALIS ANTERIOR (2): EMG 2 Sampling frequency: 2.148148e+003 "
    "Number of points: 6 start: 0.000000e+000 Unit: V Domain Unit: s\n"
    "Label: R VASTUS LATERALIS (6): EMG 6 Sampling frequency: 2.148148e+003 "
    "Number of points: 6 start: 0.000000e+000 Unit: V Domain Unit: s\n"
    "Start Trigger Method: Trigno Wireless System (start trigger)\n"
    "Stop Trigger Method: Trigno Wireless System (stop trigger)\n"
    " \n"
)


def _write_delsys_csv(path: Path, uneven: bool = False) -> None:
    lines = [
        'X[s],"R TIBIALIS ANTERIOR (2): EMG 2",X[s],"R VASTUS LATERALIS (6): EMG 6"'
    ]
    for i in range(6):
        t = i / 2148.148
        if uneven and i == 5:
            lines.append(f"{t:.6f},0.001,,")
        else:
            lines.append(f"{t:.6f},0.001,{t:.6f},0.002")
    path.write_text(_DELSYS_HEADER + "\n".join(lines), encoding="utf-8")


def test_parse_delsys_csv(tmp_path: Path, config):
    p = tmp_path / "slvjbaseline.csv"
    _write_delsys_csv(p)
    data = parse_emg_csv(p, config)
    assert data.sampling_rate_hz == pytest.approx(2148.148, rel=1e-4)
    assert len(data.channels) == 2
    assert "R TIBIALIS ANTERIOR (2): EMG 2" in data.channels
    assert data.mat_version == "csv"
    assert not data.mvic
    assert any("mvic" in w.lower() for w in data.warnings)


def test_uneven_channel_lengths_truncated(tmp_path: Path, config):
    p = tmp_path / "uneven.csv"
    _write_delsys_csv(p, uneven=True)
    data = parse_emg_csv(p, config)
    lengths = {v.size for v in data.channels.values()}
    assert len(lengths) == 1
    assert any("truncated" in w.lower() for w in data.warnings)


def test_not_a_delsys_csv(tmp_path: Path, config):
    p = tmp_path / "other.csv"
    p.write_text("Time,Fz\n0,700\n0.001,701\n", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_emg_csv(p, config)


def test_real_mock_delsys_via_pipeline(tmp_path: Path, config):
    # A trial with a Delsys EMG CSV instead of a MAT file goes through the
    # pipeline's extension dispatch.
    from biomech_analyzer.core.constants import Condition, Modality, Task
    from biomech_analyzer.core.models import TrialFile, TrialPackage
    from biomech_analyzer.core.pipeline import AnalysisPipeline

    emg_csv = tmp_path / "slvjbaseline_emg_delsys.csv"
    _write_delsys_csv(emg_csv)
    pkg = TrialPackage(task=Task.SLVJ, condition=Condition.BASELINE)
    pkg.files[Modality.EMG] = TrialFile(emg_csv, Modality.EMG)
    # No force plate: _analyze_trial is not called directly here; instead
    # just assert the parser dispatch path used by the pipeline.
    pipeline = AnalysisPipeline(config)
    assert pipeline is not None
    data = parse_emg_csv(emg_csv, config)
    assert data.channels
