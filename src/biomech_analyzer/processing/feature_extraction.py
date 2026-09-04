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
* contact_time_s      = reactive ground contact duration before take-off
* peak_force_time_pct = time of peak Fz within the reactive contact,
                        as % of contact duration (Read 2022 definition)
* ssc_spring_correlation = Pearson r between Fz and vertical COM
                        displacement over the reactive contact; spring-like
                        behaviour when r <= -0.80 (Read/Pedley criteria);
                        combined with an early impact peak (< 20 % of
                        contact) into an SSC category good/moderate/poor
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

    _reactive_contact_features(tf, fp, events, config)

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


def _reactive_contact_features(
    tf: TrialFeatures, fp: object, events: EventSet, config: Config
) -> None:
    """Features of the reactive ground contact preceding take-off.

    Implements the drop-jump reactive-contact metrics of Read 2022 /
    Pedley 2020: contact time, timing of the peak force within contact,
    and a simplified stretch-shortening cycle (SSC) categorization based
    on (a) an impact peak in the first 20 % of contact and (b) spring-like
    behaviour, i.e. a strong negative correlation between Fz and the
    vertical centre-of-mass displacement obtained by double integration
    (initial velocity from the preceding free-fall duration).
    All PENDING_BME_VALIDATION.
    """
    if events.contact_start_s is None or events.takeoff_s is None:
        return
    t = fp.time_s  # type: ignore[attr-defined]
    fz = fp.fz_n  # type: ignore[attr-defined]
    i0 = int(np.searchsorted(t, events.contact_start_s))
    i1 = int(np.searchsorted(t, events.takeoff_s))
    if i1 - i0 < 10:
        return
    duration = float(t[i1 - 1] - t[i0])
    if duration <= 0:
        return
    _add(
        tf, "contact_time_s", duration, "s", Modality.FORCE_PLATE,
        "Ground contact duration before take-off (reactive contact for SLDJ).",
    )
    contact_fz = fz[i0:i1]
    contact_t = t[i0:i1]

    # ---- touchdown velocity for COM integration ---------------------------
    # Preferred: observed free-fall duration immediately before contact
    # (previous repetition's flight). SLDJ fallback: the participant drops
    # from a box placed OFF the plate, so the below-threshold interval also
    # contains standing on the box; the protocol box height (15 cm) then
    # provides the touchdown velocity v0 = -sqrt(2 g h).
    bw = events.body_weight_n
    v0: float | None = None
    threshold = float(config.get("force_plate.contact_threshold_n", 20.0))
    j = i0 - 1
    while j > 0 and fz[j] < threshold:
        j -= 1
    t_air = float(t[i0 - 1] - t[j]) if i0 >= 1 else 0.0
    if 0.05 <= t_air <= 0.9:
        v0 = -9.81 * t_air
    elif tf.task.value == "SLDJ":
        box_h = float(config.get("events.drop_box_height_m", 0.15))
        v0 = -float(np.sqrt(2 * 9.81 * box_h))

    # SSC categorization and landing-phase peak timing follow drop-jump
    # literature (Read 2022 / Pedley 2020); they are only meaningful for
    # the SLDJ reactive contact, not the SLVJ countermovement stance.
    if tf.task.value != "SLDJ":
        return

    if bw is None or bw <= 0 or v0 is None:
        # Landing sub-phase unknown: report peak timing over the whole
        # contact only for short, clearly reactive contacts.
        if duration <= 0.6:
            peak_rel = int(np.argmax(contact_fz))
            pct = 100.0 * float(contact_t[peak_rel] - contact_t[0]) / duration
            _add(
                tf, "peak_force_time_pct", pct, "%", Modality.FORCE_PLATE,
                "Time of peak force within the reactive contact, as % of "
                "contact duration.",
            )
        tf.warnings.append(
            "SSC classification skipped: touchdown velocity could not be "
            "estimated (no observable free-fall and no drop-box reference)."
        )
        return

    mass = bw / 9.81
    accel = (contact_fz - bw) / mass
    dt = np.diff(contact_t)
    vel = v0 + np.concatenate([[0.0], np.cumsum((accel[1:] + accel[:-1]) / 2 * dt)])
    disp = np.concatenate([[0.0], np.cumsum((vel[1:] + vel[:-1]) / 2 * dt)])
    if float(np.std(disp)) <= 0 or float(np.std(contact_fz)) <= 0:
        return

    # Landing sub-phase = contact start until peak downward COM displacement
    # (Read 2022); peak LANDING force is the maximum within that sub-phase,
    # expressed as % of the total contact duration.
    com_min = int(np.argmin(disp))
    landing_end = max(com_min, 2)
    peak_rel = int(np.argmax(contact_fz[: landing_end + 1]))
    pct = 100.0 * float(contact_t[peak_rel] - contact_t[0]) / duration
    _add(
        tf, "peak_force_time_pct", pct, "%", Modality.FORCE_PLATE,
        "Time of the peak landing force (within the landing sub-phase, up "
        "to peak COM displacement) as % of total contact duration.",
    )
    impact_peak = pct < 20.0

    r = float(np.corrcoef(contact_fz, disp)[0, 1])
    _add(
        tf, "ssc_spring_correlation", r, "r", Modality.FORCE_PLATE,
        "Pearson correlation between Fz and vertical COM displacement over "
        "the reactive contact (spring-like when r <= -0.80).",
    )
    spring_like = r <= -0.80
    if spring_like and not impact_peak:
        tf.ssc_category = "good"
    elif (not spring_like) and impact_peak:
        tf.ssc_category = "poor"
    else:
        tf.ssc_category = "moderate"


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
