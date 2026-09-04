"""Deterministic biomechanical event detection from the force plate Fz signal.

Real laboratory recordings (SubjectsData) differ from the idealized single
jump in three ways this module accounts for:

* one recording contains **several jump repetitions** (typically ~5);
* SLDJ recordings **start with an empty plate** (participant on the box), so
  the longest below-threshold interval is *not* the flight phase;
* there is not always a quiet stance at the very start for body-weight
  estimation.

Strategy:

1. Candidate flight phases = below-threshold runs bounded by contact on both
   sides with a plausible duration (``events.min_flight_s``..``max_flight_s``).
2. One repetition is selected (config ``events.repetition_selection``:
   ``longest_flight`` default, or ``first``); the count of detected
   repetitions is reported.
3. Body weight = median of the initial quiet stance when available, else the
   most force-stable contact window anywhere in the recording.
4. Post-landing analysis (peak force, stabilization) is confined to the
   window before the next repetition's take-off.
"""

from __future__ import annotations

import logging

import numpy as np

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.models import EventSet, ForcePlateData

log = logging.getLogger(__name__)

_G = 9.81


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) index pairs of contiguous True runs."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, b in enumerate(mask):
        if b and start is None:
            start = i
        elif not b and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _flight_candidates(
    fz: np.ndarray, fs: float, threshold: float, min_s: float, max_s: float
) -> list[tuple[int, int]]:
    """Below-threshold runs bounded by contact with plausible duration."""
    candidates = []
    for s, e in _runs(fz < threshold):
        if s == 0 or e >= len(fz):
            continue  # empty plate at recording start/end, not flight
        duration = (e - s) / fs
        if min_s <= duration <= max_s:
            candidates.append((s, e))
    return candidates


def _estimate_body_weight(
    fz: np.ndarray, fs: float, stance_window_s: float, threshold: float
) -> tuple[float | None, list[str]]:
    """Initial quiet stance when available, else the most stable contact window."""
    warnings: list[str] = []
    n = max(1, int(round(stance_window_s * fs)))
    initial = fz[:n]
    if initial.size and np.median(initial) > threshold and np.std(initial) < 0.05 * np.median(initial):
        return float(np.median(initial)), warnings

    # Fallback: minimum rolling standard deviation over contact samples.
    warnings.append(
        "No quiet stance at recording start; body weight estimated from the "
        "most force-stable contact window in the recording "
        "(PENDING_BME_VALIDATION)."
    )
    best_std = np.inf
    best_median: float | None = None
    step = max(1, n // 4)
    for start in range(0, len(fz) - n, step):
        seg = fz[start : start + n]
        if np.min(seg) < threshold:
            continue  # window touches a non-contact phase
        seg_std = float(np.std(seg))
        if seg_std < best_std:
            best_std = seg_std
            best_median = float(np.median(seg))
    if best_median is None:
        warnings.append("Body weight could not be estimated from the recording.")
    return best_median, warnings


def detect_events(
    data: ForcePlateData, config: Config, known_body_weight_n: float | None = None
) -> EventSet:
    """Detect jump events from a (preprocessed) force plate recording.

    Never raises for detection failures; missing events stay ``None`` with
    an explanatory warning so the pipeline can degrade gracefully.

    Args:
        known_body_weight_n: body weight from participant anthropometrics
            (mass * g), used as a fallback when the plate offers no stable
            estimate and as a consistency check otherwise.
    """
    events = EventSet()
    fz = data.fz_n
    t = data.time_s
    fs = data.sampling_rate_hz
    threshold = float(config.get("force_plate.contact_threshold_n", 20.0))
    stance_window_s = float(config.get("force_plate.bodyweight_stance_window_s", 0.5))
    min_flight_s = float(config.get("events.min_flight_s", 0.08))
    max_flight_s = float(config.get("events.max_flight_s", 1.0))
    selection = str(config.get("events.repetition_selection", "longest_flight"))

    bw, bw_warnings = _estimate_body_weight(fz, fs, stance_window_s, threshold)
    events.warnings.extend(bw_warnings)
    if bw is None and known_body_weight_n is not None:
        bw = known_body_weight_n
        events.warnings.append(
            "Body weight taken from participant anthropometrics "
            f"({known_body_weight_n:.0f} N) because no stable plate estimate "
            "was available."
        )
    elif bw is not None and known_body_weight_n is not None:
        deviation = abs(bw - known_body_weight_n) / known_body_weight_n
        if deviation > 0.15:
            events.warnings.append(
                f"Plate-based body weight ({bw:.0f} N) deviates "
                f"{deviation * 100:.0f}% from the participant's registered "
                f"weight ({known_body_weight_n:.0f} N); the registered weight "
                "was used instead."
            )
            bw = known_body_weight_n
    events.body_weight_n = bw

    candidates = _flight_candidates(fz, fs, threshold, min_flight_s, max_flight_s)
    if not candidates:
        events.warnings.append(
            "No plausible flight phase found in Fz; take-off and initial "
            "contact could not be detected. Check the contact threshold "
            f"(currently {threshold:g} N) and the flight duration limits "
            f"({min_flight_s:g}-{max_flight_s:g} s)."
        )
        return events

    if len(candidates) > 1:
        events.warnings.append(
            f"{len(candidates)} jump repetitions detected in this recording; "
            f"repetition selection rule: '{selection}' "
            "(PENDING_BME_VALIDATION). Flight times per repetition: "
            + ", ".join(f"{(e - s) / fs:.3f}s" for s, e in candidates)
            + "."
        )

    if selection == "first":
        takeoff_idx, ic_idx = candidates[0]
    else:  # longest_flight (default)
        takeoff_idx, ic_idx = max(candidates, key=lambda r: r[1] - r[0])

    events.takeoff_s = float(t[takeoff_idx])
    events.initial_contact_s = float(t[ic_idx])
    events.flight_time_s = events.initial_contact_s - events.takeoff_s

    # Post-landing analysis window ends where the next repetition leaves the
    # plate (or at the end of the recording).
    later_starts = [s for s, _ in candidates if s > ic_idx]
    window_end = min(later_starts) if later_starts else len(fz)

    post = fz[ic_idx:window_end]
    peak_rel = int(np.argmax(post))
    events.peak_force_s = float(t[ic_idx + peak_rel])
    events.peak_force_n = float(post[peak_rel])

    # Contact time: duration of the contiguous contact phase immediately
    # before take-off (drop-jump ground contact / push-off duration).
    i = takeoff_idx - 1
    while i > 0 and fz[i] >= threshold:
        i -= 1
    if takeoff_idx - 1 > i:
        events.contact_start_s = float(t[i + 1])
        events.contact_time_s = float(t[takeoff_idx] - t[i + 1])

    # Stabilization: Fz stays within ±band of BW for a sustained hold,
    # searched only inside the post-landing window.
    if bw is not None:
        frac = float(config.get("events.stabilization_bw_fraction", 0.05))
        hold_s = float(config.get("events.stabilization_hold_s", 0.5))
        hold_n = max(1, int(round(hold_s * fs)))
        band = frac * bw
        inside = np.abs(post - bw) <= band
        run = 0
        for j, ok in enumerate(inside):
            run = run + 1 if ok else 0
            if run >= hold_n:
                events.stabilization_s = float(t[ic_idx + j - hold_n + 1])
                break
        if events.stabilization_s is None:
            events.warnings.append(
                "Force did not stabilize within the post-landing window; "
                "time to stabilization unavailable."
            )
    else:
        events.warnings.append(
            "Stabilization detection skipped (no body-weight estimate)."
        )

    log.info(
        "Events: %d repetition(s), takeoff=%.3f IC=%.3f peak=%.3f stab=%s",
        len(candidates),
        events.takeoff_s,
        events.initial_contact_s,
        events.peak_force_s,
        f"{events.stabilization_s:.3f}" if events.stabilization_s else "None",
    )
    return events


def jump_height_from_flight(flight_time_s: float) -> float:
    """Flight-time jump height: h = g * t^2 / 8 (projectile assumption)."""
    return _G * flight_time_s**2 / 8.0
