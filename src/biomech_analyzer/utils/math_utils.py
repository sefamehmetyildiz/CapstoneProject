"""Numeric helpers shared across processing modules."""

from __future__ import annotations

import numpy as np
from scipy import signal


def butter_lowpass(
    data: np.ndarray, cutoff_hz: float, fs_hz: float, order: int = 4
) -> np.ndarray:
    """Zero-phase Butterworth low-pass filter.

    Falls back to the unfiltered signal (copy) when the cutoff is not
    achievable at the given sampling rate.
    """
    nyq = fs_hz / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyq or data.size < 15:
        return data.copy()
    b, a = signal.butter(order, cutoff_hz / nyq, btype="low")
    return signal.filtfilt(b, a, data)


def butter_bandpass(
    data: np.ndarray, low_hz: float, high_hz: float, fs_hz: float, order: int = 4
) -> np.ndarray:
    """Zero-phase Butterworth band-pass filter with safe clamping."""
    nyq = fs_hz / 2.0
    high_hz = min(high_hz, nyq * 0.99)
    if low_hz <= 0 or low_hz >= high_hz or data.size < 15:
        return data.copy()
    b, a = signal.butter(order, [low_hz / nyq, high_hz / nyq], btype="band")
    return signal.filtfilt(b, a, data)


def moving_rms(data: np.ndarray, window_samples: int) -> np.ndarray:
    """Moving root-mean-square envelope with same-length output.

    The window is clamped to the signal length: ``np.convolve`` with
    ``mode="same"`` sizes its output to the *longer* input, which would
    silently change the output length for very short signals.
    """
    squared = np.asarray(data, dtype=float) ** 2
    window_samples = max(1, min(int(window_samples), squared.size))
    kernel = np.ones(window_samples) / window_samples
    return np.sqrt(np.convolve(squared, kernel, mode="same"))


