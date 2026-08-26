"""Configurable signal preprocessing for the three modalities."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.models import EmgData, ForcePlateData, XsensData
from biomech_analyzer.utils.math_utils import butter_bandpass, butter_lowpass, moving_rms

log = logging.getLogger(__name__)


def _auto_zero_offset(fz: np.ndarray, warnings: list[str], config: Config) -> np.ndarray:
    """Remove a constant unloaded-plate offset when one is clearly present.

    Real exports include recordings where the plate was not zeroed (empty
    plate reads ~40 N), which silently breaks contact detection against the
    configured threshold. The offset is the median of the bottom decile of
    samples, applied only when that cluster is stable (small spread) and
    small relative to the loaded level — a recording where the participant
    never leaves the plate keeps its original values.
    """
    if not bool(config.get("force_plate.auto_zero", True)):
        return fz
    finite = fz[np.isfinite(fz)]
    if finite.size < 100:
        return fz
    bottom = np.sort(finite)[: max(10, finite.size // 10)]
    offset = float(np.median(bottom))
    spread = float(np.std(bottom))
    loaded = float(np.percentile(finite, 90))
    if abs(offset) > 5.0 and spread < 10.0 and abs(offset) < 0.3 * max(loaded, 1.0):
        warnings.append(
            f"Unloaded-plate offset of {offset:+.1f} N detected and removed "
            "(force plate was not zeroed before recording)."
        )
        return fz - offset
    return fz


def preprocess_force_plate(data: ForcePlateData, config: Config) -> ForcePlateData:
    """Auto-zero + low-pass filter force signals; input object untouched."""
    cutoff = float(config.get("force_plate.lowpass_cutoff_hz", 50.0))
    order = int(config.get("force_plate.filter_order", 4))
    fs = data.sampling_rate_hz

    def _f(sig: np.ndarray | None) -> np.ndarray | None:
        return None if sig is None else butter_lowpass(sig, cutoff, fs, order)

    zero_warnings: list[str] = []
    fz_zeroed = _auto_zero_offset(data.fz_n, zero_warnings, config)
    filtered_fz = butter_lowpass(fz_zeroed, cutoff, fs, order)
    out = ForcePlateData(
        time_s=data.time_s,
        fz_n=np.clip(filtered_fz, 0.0, None),
        fx_n=_f(data.fx_n),
        fy_n=_f(data.fy_n),
        cop_x_m=data.cop_x_m,  # CoP left unfiltered; path length uses raw excursion
        cop_y_m=data.cop_y_m,
        sampling_rate_hz=fs,
        source_path=data.source_path,
        warnings=list(data.warnings) + zero_warnings,
    )
    out.warnings.append(
        f"Force signals low-pass filtered at {cutoff:g} Hz (order {order}, zero-phase)."
    )
    return out


@dataclass
class EmgEnvelopes:
    """RMS envelopes per channel, optionally MVIC-normalized."""

    time_s: np.ndarray
    envelopes: dict[str, np.ndarray]
    normalized: bool
    sampling_rate_hz: float
    warnings: list[str] = field(default_factory=list)


def preprocess_emg(data: EmgData, config: Config) -> EmgEnvelopes:
    """Band-pass -> rectify -> RMS-smooth -> MVIC-normalize (when possible)."""
    low = float(config.get("emg.bandpass_low_hz", 20.0))
    high = float(config.get("emg.bandpass_high_hz", 450.0))
    order = int(config.get("emg.filter_order", 4))
    rms_window_s = float(config.get("emg.rms_window_s", 0.05))
    fs = data.sampling_rate_hz
    window = max(1, int(round(rms_window_s * fs)))

    warnings: list[str] = []
    envelopes: dict[str, np.ndarray] = {}
    normalized = bool(data.mvic)
    if not normalized:
        warnings.append(
            "MVIC values unavailable: EMG envelopes are NOT normalized; "
            "amplitude features are in raw units and marked accordingly."
        )

    for name, signal_raw in data.channels.items():
        filtered = butter_bandpass(np.asarray(signal_raw, float), low, high, fs, order)
        rectified = np.abs(filtered)
        envelope = moving_rms(rectified, window)
        if normalized:
            mvic_val = data.mvic.get(name)
            if mvic_val is not None and mvic_val > 0:
                envelope = envelope / mvic_val
            else:
                warnings.append(
                    f"No MVIC value for channel '{name}'; channel left non-normalized."
                )
        envelopes[name] = envelope

    log.debug("Preprocessed %d EMG channels (normalized=%s)", len(envelopes), normalized)
    return EmgEnvelopes(
        time_s=data.time_s,
        envelopes=envelopes,
        normalized=normalized,
        sampling_rate_hz=fs,
        warnings=warnings,
    )


def preprocess_xsens(data: XsensData, config: Config) -> XsensData:
    """Light smoothing of joint angle traces (5 Hz low-pass)."""
    fs = data.sampling_rate_hz
    smoothed = {
        name: butter_lowpass(np.asarray(sig, float), 8.0, fs, 2)
        for name, sig in data.joint_angles_deg.items()
    }
    return XsensData(
        time_s=data.time_s,
        joint_angles_deg=smoothed,
        sampling_rate_hz=fs,
        source_path=data.source_path,
        warnings=list(data.warnings),
    )
