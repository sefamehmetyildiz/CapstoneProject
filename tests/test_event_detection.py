from pathlib import Path

import numpy as np
import pytest

from biomech_analyzer.core.models import ForcePlateData
from biomech_analyzer.io.force_plate_csv_parser import parse_force_plate_csv
from biomech_analyzer.processing.event_detection import (
    detect_events,
    jump_height_from_flight,
)
from biomech_analyzer.processing.preprocessing import preprocess_force_plate


def test_events_on_mock_jump(p001: Path, config):
    fp = preprocess_force_plate(
        parse_force_plate_csv(p001 / "SLVJ_baseline_force.csv", config), config
    )
    events = detect_events(fp, config)
    # Mock profile: flight 1.8-2.2 s, landing spike at ~2.24 s.
    assert events.takeoff_s == pytest.approx(1.8, abs=0.1)
    assert events.initial_contact_s == pytest.approx(2.2, abs=0.1)
    assert events.flight_time_s == pytest.approx(0.4, abs=0.15)
    assert events.peak_force_s == pytest.approx(2.24, abs=0.1)
    assert events.body_weight_n == pytest.approx(650, rel=0.05)
    assert events.peak_force_n > 1.5 * events.body_weight_n
    assert events.stabilization_s is not None
    assert events.stabilization_s > events.initial_contact_s


def test_no_flight_phase(config):
    t = np.arange(0, 3, 0.001)
    fz = np.full_like(t, 700.0)  # standing still, never leaves the plate
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=1000.0)
    events = detect_events(fp, config)
    assert events.initial_contact_s is None
    assert any("flight" in w.lower() for w in events.warnings)


def test_empty_plate_start_is_not_flight(config):
    # Recording starts with an empty plate (participant on the drop box) and
    # contains a single landing but no jump: the initial below-threshold run
    # must NOT be treated as a flight phase (real SLDJ recordings start this
    # way), and body weight comes from the stable-contact fallback.
    t = np.arange(0, 3, 0.001)
    fz = np.zeros_like(t)
    fz[t >= 1.0] = 700.0
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=1000.0)
    events = detect_events(fp, config)
    assert events.initial_contact_s is None
    assert any("flight" in w.lower() for w in events.warnings)
    assert events.body_weight_n == pytest.approx(700.0, rel=0.01)
    assert any("stable contact" in w.lower() or "quiet stance" in w.lower()
               for w in events.warnings)


def test_multiple_repetitions_selects_longest_flight(config):
    # Two jumps: flights 0.30 s and 0.45 s; the longer one is analyzed.
    fs = 1000.0
    t = np.arange(0, 8, 1 / fs)
    fz = np.full_like(t, 700.0)
    for start, dur in ((2.0, 0.30), (5.0, 0.45)):
        fz[(t >= start) & (t < start + dur)] = 0.0
    fp = ForcePlateData(time_s=t, fz_n=fz, sampling_rate_hz=fs)
    events = detect_events(fp, config)
    assert events.takeoff_s == pytest.approx(5.0, abs=0.01)
    assert events.flight_time_s == pytest.approx(0.45, abs=0.01)
    assert any("2 jump repetitions" in w for w in events.warnings)


def test_jump_height_formula():
    # 0.4 s flight -> h = 9.81 * 0.16 / 8 = 0.196 m
    assert jump_height_from_flight(0.4) == pytest.approx(0.196, abs=0.001)
