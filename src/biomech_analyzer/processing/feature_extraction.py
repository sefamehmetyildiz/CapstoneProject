"""Biomechanical feature extraction (formula registry).

This module is the single home of every feature formula, per the project
rule that clinically sensitive computations must not be scattered across
modules. Each emitted :class:`FeatureValue` carries a ``validation_status``;
formulas whose final definition has not been confirmed by the Biomedical
Engineering team are marked ``PENDING_BME_VALIDATION`` and reported as such.

Formula notes
-------------
* peak_vgrf_bw        = max(Fz after IC) / body weight
* rfd_n_per_s         = (Fz(IC + w) - Fz(IC)) / w         (w = config rfd_window_s)
* jump_height_m       = g * flight_time^2 / 8              (flight-time method)
* rsi                 = jump_height / contact_time         (requires push-off contact)
* time_to_stabilization_s = stabilization - IC
* landing_impulse_ns  = trapezoidal integral of Fz from IC to stabilization
* cop_path_length_m   = sum of CoP step lengths from IC to stabilization
* preactivation_ratio = mean summed EMG envelope in the pre-IC window
                        divided by its trial peak
* hq_activation_ratio = mean hamstring envelope / mean quadriceps envelope
                        in the landing window
* joint angle features are peaks / ranges within the landing window
"""

from __future__ import annotations

import logging

import numpy as np

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.constants import (
    VALIDATION_PENDING,
    Modality,
)
from biomech_analyzer.core.models import (
    EventSet,
    FeatureValue,
    TrialData,
    TrialFeatures,
)
from biomech_analyzer.processing.event_detection import jump_height_from_flight
from biomech_analyzer.processing.preprocessing import EmgEnvelopes

log = logging.getLogger(__name__)


def _window_mask(time_s: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    return (time_s >= start_s) & (time_s <= end_s)


def _add(
    tf: TrialFeatures,
    name: str,
    value: float | None,
    unit: str,
    modality: Modality,
    description: str,
) -> None:
    """Register a feature when its value exists and is finite."""
    if value is None or not np.isfinite(value):
        tf.warnings.append(f"Feature '{name}' could not be computed.")
        return
    tf.features[name] = FeatureValue(
        name=name,
        value=float(value),
        unit=unit,
        modality=modality,
        validation_status=VALIDATION_PENDING,
        description=description,
    )


def extract_features(
    trial: TrialData,
    emg_env: EmgEnvelopes | None,
    events: EventSet,
    config: Config,
) -> TrialFeatures:
    """Extract all available features for one synchronized trial."""
    tf = TrialFeatures(
        trial_id=trial.package.trial_id,
        task=trial.package.task,
        condition=trial.package.condition,
        events=events,
    )
    _force_plate_features(tf, trial, events, config)
    if emg_env is not None:
        _emg_features(tf, trial, emg_env, events, config)
    if trial.xsens is not None:
        _xsens_features(tf, trial, events, config)
    log.info("Extracted %d features for %s", len(tf.features), tf.trial_id)
    return tf


# ---------------------------------------------------------------------------


def _force_plate_features(
    tf: TrialFeatures, trial: TrialData, events: EventSet, config: Config
) -> None:
    fp = trial.force_plate
    if fp is None:
        tf.warnings.append("No force plate data; kinetic features unavailable.")
        return
    t, fz = fp.time_s, fp.fz_n
    bw = events.body_weight_n

    if events.peak_force_n is not None:
        _add(
            tf, "peak_vgrf_n", events.peak_force_n, "N", Modality.FORCE_PLATE,
            "Peak vertical ground reaction force after initial contact.",
        )
        if bw:
            _add(
                tf, "peak_vgrf_bw", events.peak_force_n / bw, "BW", Modality.FORCE_PLATE,
                "Peak vGRF normalized to body weight.",
            )
        else:
            tf.warnings.append(
                "peak_vgrf_bw skipped: body weight estimate unavailable."
            )

    ic = events.initial_contact_s
    if ic is not None:
        w = float(config.get("events.rfd_window_s", 0.1))
        i0 = int(np.searchsorted(t, ic))
        i1 = min(int(np.searchsorted(t, ic + w)), len(fz) - 1)
        if i1 > i0:
            _add(
                tf, "rfd_n_per_s", (fz[i1] - fz[i0]) / (t[i1] - t[i0]), "N/s",
                Modality.FORCE_PLATE,
                f"Rate of force development over the first {w * 1000:.0f} ms after contact.",
            )

    if events.flight_time_s is not None:
        _add(
            tf, "flight_time_s", events.flight_time_s, "s", Modality.FORCE_PLATE,
            "Flight time between take-off and landing.",
        )
        height = jump_height_from_flight(events.flight_time_s)
        _add(
            tf, "jump_height_m", height, "m", Modality.FORCE_PLATE,
            "Jump height from flight time (h = g*t^2/8).",
        )
        if events.contact_time_s and events.contact_time_s > 0:
            _add(
                tf, "rsi", height / events.contact_time_s, "m/s", Modality.FORCE_PLATE,
                "Reactive strength index: jump height / ground contact time.",
            )
        else:
            tf.warnings.append("rsi skipped: push-off contact time unavailable.")

    if ic is not None and events.stabilization_s is not None:
        tts = events.stabilization_s - ic
        _add(
            tf, "time_to_stabilization_s", tts, "s", Modality.FORCE_PLATE,
            "Time from initial contact until Fz stays within the body-weight band.",
        )
        mask = _window_mask(t, ic, events.stabilization_s)
        if mask.sum() > 2:
            _add(
                tf, "landing_impulse_ns",
                float(np.trapezoid(fz[mask], t[mask])), "N*s", Modality.FORCE_PLATE,
                "Vertical impulse from initial contact to stabilization.",
            )
            if fp.cop_x_m is not None and fp.cop_y_m is not None:
                dx = np.diff(fp.cop_x_m[mask])
                dy = np.diff(fp.cop_y_m[mask])
                _add(
                    tf, "cop_path_length_m",
                    float(np.nansum(np.sqrt(dx**2 + dy**2))), "m", Modality.FORCE_PLATE,
                    "Centre-of-pressure path length during the landing phase.",
                )


def _landing_window(
    events: EventSet, config: Config
) -> tuple[float, float] | None:
    ic = events.initial_contact_s
    if ic is None:
        return None
    pre = float(config.get("xsens.landing_window_pre_s", 0.1))
    post = float(config.get("xsens.landing_window_post_s", 0.5))
    return ic - pre, ic + post


def _emg_features(
    tf: TrialFeatures,
    trial: TrialData,
    emg_env: EmgEnvelopes,
    events: EventSet,
    config: Config,
) -> None:
    ic = events.initial_contact_s
    if ic is None:
        tf.warnings.append("EMG features skipped: initial contact undetected.")
        return
    offset = trial.sync.emg_offset_s if trial.sync else 0.0
    # Convert force-plate times into the EMG stream's own time base.
    t_emg = emg_env.time_s
    ic_local = ic - offset

    env_stack = np.vstack(list(emg_env.envelopes.values()))
    summed = env_stack.sum(axis=0)
    peak = float(summed.max()) if summed.size else 0.0

    pre_w = float(config.get("emg.pre_activation_window_s", 0.15))
    pre_mask = _window_mask(t_emg, ic_local - pre_w, ic_local)
    if pre_mask.any() and peak > 0:
        _add(
            tf, "preactivation_ratio",
            float(summed[pre_mask].mean() / peak), "ratio", Modality.EMG,
            "Mean summed EMG envelope in the pre-contact window relative to "
            "its trial peak.",
        )
    else:
        tf.warnings.append(
            "preactivation_ratio skipped: pre-contact window outside the EMG recording."
        )

    # Muscle-group mapping from config.
    groups: dict[str, list[str]] = {}
    group_cfg = config.get("emg.muscle_groups", {}) or {}
    for group_name, fragments in group_cfg.items():
        members = [
            ch
            for ch in emg_env.envelopes
            if any(str(f).lower() in ch.lower() for f in fragments)
        ]
        if members:
            groups[group_name] = members

    win = _landing_window(events, config)
    if win is not None:
        w_mask = _window_mask(t_emg, win[0] - offset, win[1] - offset)
        if w_mask.any():
            quad = groups.get("quadriceps")
            ham = groups.get("hamstrings")
            if quad and ham:
                quad_mean = float(
                    np.mean([emg_env.envelopes[ch][w_mask].mean() for ch in quad])
                )
                ham_mean = float(
                    np.mean([emg_env.envelopes[ch][w_mask].mean() for ch in ham])
                )
                if quad_mean > 0:
                    _add(
                        tf, "hq_activation_ratio", ham_mean / quad_mean, "ratio",
                        Modality.EMG,
                        "Hamstring/quadriceps mean envelope ratio in the landing window.",
                    )
            else:
                tf.warnings.append(
                    "hq_activation_ratio skipped: quadriceps/hamstrings channels "
                    "not identified from channel names."
                )
            _add(
                tf, "landing_emg_rms_mean",
                float(env_stack[:, w_mask].mean()),
                "MVIC" if emg_env.normalized else "a.u.",
                Modality.EMG,
                "Mean EMG envelope across channels in the landing window"
                + ("" if emg_env.normalized else " (NON-normalized)"),
            )

    # Onset latency of the quadriceps group relative to initial contact.
    quad = groups.get("quadriceps")
    if quad:
        base_w = float(config.get("emg.onset_baseline_window_s", 0.25))
        k = float(config.get("emg.onset_threshold_sd", 3.0))
        sig = np.mean(np.vstack([emg_env.envelopes[ch] for ch in quad]), axis=0)
        base_mask = t_emg <= (t_emg[0] + base_w)
        if base_mask.sum() > 5:
            thr = float(sig[base_mask].mean() + k * sig[base_mask].std())
            search = t_emg >= (ic_local - 0.5)
            idx = np.flatnonzero(search & (sig >= thr))
            if idx.size:
                onset_local = float(t_emg[idx[0]])
                _add(
                    tf, "quad_onset_latency_s", onset_local - ic_local, "s",
                    Modality.EMG,
                    "Quadriceps activation onset relative to initial contact "
                    "(negative = pre-activation).",
                )


def _xsens_features(
    tf: TrialFeatures, trial: TrialData, events: EventSet, config: Config
) -> None:
    xs = trial.xsens
    assert xs is not None
    win = _landing_window(events, config)
    if win is None:
        tf.warnings.append("Kinematic features skipped: initial contact undetected.")
        return
    offset = trial.sync.xsens_offset_s if trial.sync else 0.0
    mask = _window_mask(xs.time_s, win[0] - offset, win[1] - offset)
    if not mask.any():
        tf.warnings.append(
            "Kinematic features skipped: landing window outside the Xsens recording."
        )
        return

    aliases = config.get("xsens.joint_aliases", {}) or {}

    def _trace(joint_key: str, component: str) -> np.ndarray | None:
        fragments = [str(f).lower() for f in aliases.get(joint_key, [joint_key])]
        for name, sig in xs.joint_angles_deg.items():
            low = name.lower()
            if component in low and any(f in low for f in fragments):
                return sig
        return None

    knee = _trace("knee", "flexion")
    if knee is not None:
        _add(
            tf, "peak_knee_flexion_deg", float(knee[mask].max()), "deg", Modality.XSENS,
            "Peak knee flexion in the landing window.",
        )
        _add(
            tf, "knee_rom_deg", float(knee[mask].max() - knee[mask].min()), "deg",
            Modality.XSENS, "Knee flexion range of motion during landing.",
        )
    knee_frontal = _trace("knee", "abduction")
    if knee_frontal is not None:
        _add(
            tf, "knee_frontal_rom_deg",
            float(knee_frontal[mask].max() - knee_frontal[mask].min()), "deg",
            Modality.XSENS,
            "Frontal-plane knee excursion during landing (valgus/varus proxy).",
        )
    hip = _trace("hip", "flexion")
    if hip is not None:
        _add(
            tf, "peak_hip_flexion_deg", float(hip[mask].max()), "deg", Modality.XSENS,
            "Peak hip flexion in the landing window.",
        )
    ankle = _trace("ankle", "flexion")
    if ankle is not None:
        _add(
            tf, "peak_ankle_dorsiflexion_deg", float(ankle[mask].max()), "deg",
            Modality.XSENS, "Peak ankle dorsiflexion in the landing window.",
        )
    if knee is None and hip is None and ankle is None:
        tf.warnings.append(
            "No joint angle traces matched the configured joint aliases."
        )
