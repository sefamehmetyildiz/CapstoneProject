import numpy as np

from biomech_analyzer.utils.math_utils import (
    butter_bandpass,
    butter_lowpass,
    moving_rms,
)


def test_lowpass_removes_high_frequency():
    fs = 1000.0
    t = np.arange(0, 2, 1 / fs)
    slow = np.sin(2 * np.pi * 2 * t)
    noisy = slow + 0.5 * np.sin(2 * np.pi * 200 * t)
    out = butter_lowpass(noisy, 20.0, fs)
    assert np.abs(out - slow).mean() < 0.05


def test_lowpass_invalid_cutoff_returns_copy():
    data = np.ones(100)
    out = butter_lowpass(data, 0.0, 1000.0)
    assert np.array_equal(out, data)
    out2 = butter_lowpass(data, 600.0, 1000.0)  # >= Nyquist
    assert np.array_equal(out2, data)


def test_bandpass_keeps_passband():
    fs = 2000.0
    t = np.arange(0, 2, 1 / fs)
    inband = np.sin(2 * np.pi * 100 * t)
    out = butter_bandpass(inband, 20.0, 450.0, fs)
    # amplitude mostly preserved
    assert 0.8 < np.abs(out).max() < 1.2


def test_bandpass_clamps_high_cutoff():
    fs = 500.0  # Nyquist 250 < requested 450
    data = np.random.default_rng(0).normal(size=1000)
    out = butter_bandpass(data, 20.0, 450.0, fs)
    assert out.shape == data.shape
    assert np.isfinite(out).all()


def test_moving_rms_constant_signal():
    out = moving_rms(np.full(200, 2.0), 20)
    assert np.allclose(out[50:150], 2.0, atol=1e-6)


def test_moving_rms_short_signal():
    out = moving_rms(np.array([1.0, 2.0]), 50)
    assert out.shape == (2,)
