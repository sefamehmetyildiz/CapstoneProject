"""Multimodal synchronization.

Primary strategy: trust shared timestamps when all streams cover a
consistent time span (their durations and origins agree within a
configurable skew).

Fallback strategy: event-based anchoring on the force plate vertical GRF —
the landing peak in Fz is matched to the summed-EMG activity peak and to
the peak knee-flexion instant in the Xsens stream. All applied offsets and
assumptions are recorded in :class:`SyncInfo` and surfaced in the report,
as required by the proposal (§3.2).
"""

from __future__ import annotations

import logging

import numpy as np

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import SynchronizationError
from biomech_analyzer.core.models import SyncInfo, TrialData
from biomech_analyzer.processing.preprocessing import EmgEnvelopes

log = logging.getLogger(__name__)


def _landing_peak_time(time_s: np.ndarray, fz_n: np.ndarray) -> float:
    """Time of the global Fz maximum (the landing impact in a jump trial)."""
    return float(time_s[int(np.argmax(fz_n))])


def synchronize_trial(
    trial: TrialData,
    emg_env: EmgEnvelopes | None,
    config: Config,
) -> SyncInfo:
    """Determine per-modality time offsets onto the force-plate time base.

    Offsets are defined so that ``t_forceplate = t_modality + offset``.
    """
    if trial.force_plate is None:
        raise SynchronizationError(
            "Cannot synchronize a trial without force plate data.",
            hint="The force plate signal is the temporal reference.",
        )

    strategy = str(config.get("synchronization.strategy", "auto"))
    max_skew = float(config.get("synchronization.max_timestamp_skew_s", 0.5))
    fp = trial.force_plate
    fp_duration = float(fp.time_s[-1] - fp.time_s[0])

    notes: list[str] = []
    timestamp_ok = True
    for label, stream_time in (
        ("emg", trial.emg.time_s if trial.emg is not None else None),
        ("xsens", trial.xsens.time_s if trial.xsens is not None else None),
    ):
        if stream_time is None:
            continue
        duration = float(stream_time[-1] - stream_time[0])
        origin_skew = abs(float(stream_time[0]) - float(fp.time_s[0]))
        duration_skew = abs(duration - fp_duration)
        if origin_skew > max_skew or duration_skew > max_skew:
            timestamp_ok = False
            notes.append(
                f"{label} stream timing deviates from force plate "
                f"(origin skew {origin_skew:.3f}s, duration skew {duration_skew:.3f}s)."
            )

    if strategy in ("auto", "timestamp") and timestamp_ok:
        notes.append(
            "Timestamp-based synchronization: all streams share a consistent "
            "time base; no offsets applied."
        )
        return SyncInfo(strategy="timestamp", emg_offset_s=0.0, xsens_offset_s=0.0, notes=notes)

    if strategy == "timestamp" and not timestamp_ok:
        raise SynchronizationError(
            "Timestamp synchronization was forced but stream time bases are "
            "inconsistent. " + " ".join(notes),
            hint="Set synchronization.strategy to 'auto' or 'event'.",
        )

    # ------------------------------------------------------------------ event
    t_ref = _landing_peak_time(fp.time_s, fp.fz_n)
    notes.append(
        f"Event-based synchronization: force-plate landing peak at {t_ref:.3f}s "
        "used as the cross-modal anchor (fallback strategy)."
    )
    for label, stream_time in (
        ("EMG", trial.emg.time_s if trial.emg is not None else None),
        ("Xsens", trial.xsens.time_s if trial.xsens is not None else None),
    ):
        if stream_time is None:
            continue
        duration = float(stream_time[-1] - stream_time[0])
        if duration < 0.6 * fp_duration:
            notes.append(
                f"{label} recording ({duration:.1f}s) covers only part of the "
                f"force-plate session ({fp_duration:.1f}s): recordings contain "
                "multiple jump repetitions and streams were started "
                "independently, so peak-based alignment may match different "
                "repetitions. Cross-modal timing features are approximate; a "
                "hardware trigger is recommended for future sessions."
            )

    emg_offset = 0.0
    if trial.emg is not None and emg_env is not None and emg_env.envelopes:
        summed = np.sum(np.vstack(list(emg_env.envelopes.values())), axis=0)
        t_emg_peak = float(emg_env.time_s[int(np.argmax(summed))])
        emg_offset = t_ref - t_emg_peak
        notes.append(
            f"EMG summed-activity peak at {t_emg_peak:.3f}s aligned to landing "
            f"peak (offset {emg_offset:+.3f}s). ASSUMPTION: peak muscle "
            "activity coincides with landing impact; requires BME validation."
        )

    xsens_offset = 0.0
    if trial.xsens is not None:
        knee_keys = [
            k for k in trial.xsens.joint_angles_deg if "knee" in k.lower() and "flexion" in k.lower()
        ]
        if knee_keys:
            knee = trial.xsens.joint_angles_deg[knee_keys[0]]
            t_knee_peak = float(trial.xsens.time_s[int(np.argmax(knee))])
            xsens_offset = t_ref - t_knee_peak
            notes.append(
                f"Xsens peak knee flexion at {t_knee_peak:.3f}s aligned to "
                f"landing peak (offset {xsens_offset:+.3f}s). ASSUMPTION: peak "
                "knee flexion follows landing impact closely; requires BME validation."
            )
        else:
            notes.append(
                "No knee flexion trace found for event alignment; Xsens left unaligned."
            )

    log.info("Event-based sync: emg_offset=%.3fs xsens_offset=%.3fs", emg_offset, xsens_offset)
    return SyncInfo(
        strategy="event",
        emg_offset_s=emg_offset,
        xsens_offset_s=xsens_offset,
        notes=notes,
    )
