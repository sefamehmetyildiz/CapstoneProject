from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.io.emg_mat_parser import detect_mat_version, parse_emg_mat


def test_parse_v5(p001: Path, config):
    # SLVJ_baseline uses the v5 writer in the mock generator
    path = p001 / "SLVJ_baseline_emg.mat"
    assert detect_mat_version(path) == "v5"
    data = parse_emg_mat(path, config)
    assert data.sampling_rate_hz == 2000.0
    assert len(data.channels) == 8
    assert "R Vastus Lateralis" in data.channels
    assert data.mvic  # MVIC table present
    assert data.mat_version == "v5"


def test_parse_v73(p001: Path, config):
    # SLVJ_upright alternates to the v7.3 writer
    path = p001 / "SLVJ_upright_emg.mat"
    assert detect_mat_version(path) == "v7.3"
    data = parse_emg_mat(path, config)
    assert data.mat_version == "v7.3"
    assert len(data.channels) == 8
    assert data.time_s.size == next(iter(data.channels.values())).size


def test_missing_signal_variable(tmp_path: Path, config):
    from scipy.io import savemat

    p = tmp_path / "bad.mat"
    savemat(str(p), {"unrelated": [1, 2, 3]})
    with pytest.raises(ParseError) as exc:
        parse_emg_mat(p, config)
    assert "signal" in str(exc.value).lower() or "EMG" in str(exc.value)


def test_missing_mvic_warns(tmp_path: Path, config):
    import numpy as np
    from scipy.io import savemat

    p = tmp_path / "nomvic.mat"
    savemat(
        str(p),
        {
            "Fs": 1000.0,
            "Data": np.random.default_rng(0).normal(size=(2, 500)),
            "Channels": np.array(["A", "B"], dtype=object),
        },
    )
    data = parse_emg_mat(p, config)
    assert not data.mvic
    assert any("mvic" in w.lower() for w in data.warnings)


def test_not_a_mat_file(tmp_path: Path, config):
    p = tmp_path / "fake.mat"
    p.write_bytes(b"this is not a mat file at all" * 10)
    with pytest.raises(ParseError):
        parse_emg_mat(p, config)
