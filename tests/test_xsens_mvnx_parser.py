from pathlib import Path

import pytest

from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.io.xsens_mvnx_parser import parse_xsens_mvnx


def test_parse_mock_mvnx(p001: Path, config):
    data = parse_xsens_mvnx(p001 / "SLVJ_baseline_xsens.mvnx", config)
    assert data.sampling_rate_hz == pytest.approx(60.0, rel=0.05)
    assert "jRightKnee_flexion_deg" in data.joint_angles_deg
    knee = data.joint_angles_deg["jRightKnee_flexion_deg"]
    assert knee.size == data.time_s.size
    assert knee.max() > 40  # deep flexion at landing exists in mock signal


def test_namespaceless_mvnx(tmp_path: Path, config):
    p = tmp_path / "plain.mvnx"
    p.write_text(
        """<?xml version="1.0"?>
<mvnx version="4">
 <subject frameRate="100">
  <joints><joint label="jLeftKnee"/></joints>
  <frames>
   <frame time="0" type="normal"><jointAngle>1 2 3</jointAngle></frame>
   <frame time="10" type="normal"><jointAngle>1 2 4</jointAngle></frame>
   <frame time="20" type="normal"><jointAngle>1 2 5</jointAngle></frame>
  </frames>
 </subject>
</mvnx>""",
        encoding="utf-8",
    )
    data = parse_xsens_mvnx(p, config)
    assert data.joint_angles_deg["jLeftKnee_flexion_deg"].tolist() == [3.0, 4.0, 5.0]
    assert data.sampling_rate_hz == 100.0


def test_calibration_frames_skipped(tmp_path: Path, config):
    p = tmp_path / "calib.mvnx"
    p.write_text(
        """<mvnx><subject frameRate="60">
  <joints><joint label="jK"/></joints>
  <frames>
   <frame time="0" type="tpose"><jointAngle>9 9 9</jointAngle></frame>
   <frame time="0" type="normal"><jointAngle>1 1 1</jointAngle></frame>
   <frame time="17" type="normal"><jointAngle>2 2 2</jointAngle></frame>
  </frames>
 </subject></mvnx>""",
        encoding="utf-8",
    )
    data = parse_xsens_mvnx(p, config)
    assert data.time_s.size == 2  # tpose frame excluded


def test_invalid_xml(tmp_path: Path, config):
    p = tmp_path / "broken.mvnx"
    p.write_text("<mvnx><unclosed>", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_xsens_mvnx(p, config)


def test_no_joints(tmp_path: Path, config):
    p = tmp_path / "nojoints.mvnx"
    p.write_text("<mvnx><subject><frames/></subject></mvnx>", encoding="utf-8")
    with pytest.raises(ParseError) as exc:
        parse_xsens_mvnx(p, config)
    assert "joints" in str(exc.value).lower()
