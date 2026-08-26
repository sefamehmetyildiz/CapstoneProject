"""Xsens MVNX (XML) parser.

Namespace-agnostic: elements are matched by local name so schema-version
differences do not break parsing. Extracts joint-angle time series; the
flexion component is assumed to be the third value of each joint's ZXY
triplet (configurable interpretation is documented in the report metadata).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from lxml import etree

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.core.models import XsensData

log = logging.getLogger(__name__)


def _local(tag: str) -> str:
    """Strip an XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _iter_by_local_name(root: etree._Element, name: str):
    for el in root.iter():
        if _local(str(el.tag)) == name:
            yield el


def parse_xsens_mvnx(path: Path, config: Config) -> XsensData:
    """Parse an MVNX file into :class:`XsensData` (angles in degrees)."""
    path = Path(path)
    warnings: list[str] = []
    try:
        tree = etree.parse(str(path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise ParseError(f"MVNX file is not readable XML: {exc}", path=str(path)) from exc
    root = tree.getroot()

    # --- joint order -------------------------------------------------------
    joint_labels: list[str] = []
    for joints_el in _iter_by_local_name(root, "joints"):
        for joint_el in joints_el:
            if _local(str(joint_el.tag)) == "joint":
                label = joint_el.get("label") or joint_el.get("name") or ""
                if label:
                    joint_labels.append(label)
        break
    if not joint_labels:
        raise ParseError(
            "No <joints> definition found in the MVNX file.",
            path=str(path),
            hint="The export may not include joint angle data.",
        )

    # --- frame rate --------------------------------------------------------
    frame_rate = 0.0
    for subject_el in _iter_by_local_name(root, "subject"):
        raw = subject_el.get("frameRate") or subject_el.get("framerate")
        if raw:
            try:
                frame_rate = float(raw)
            except ValueError:
                pass
        break

    # --- frames ------------------------------------------------------------
    times_ms: list[float] = []
    angle_rows: list[np.ndarray] = []
    n_expected = len(joint_labels) * 3
    for frame_el in _iter_by_local_name(root, "frame"):
        ftype = frame_el.get("type", "normal")
        if ftype not in ("normal", ""):
            continue  # skip calibration poses (identity/tpose/npose)
        angle_el = None
        for child in frame_el:
            if _local(str(child.tag)) == "jointAngle":
                angle_el = child
                break
        if angle_el is None or not (angle_el.text or "").strip():
            continue
        try:
            values = np.fromstring(angle_el.text, sep=" ")  # type: ignore[arg-type]
        except ValueError:
            continue
        if values.size != n_expected:
            warnings.append(
                f"A frame contained {values.size} joint-angle values "
                f"(expected {n_expected}); frame skipped."
            )
            continue
        raw_time = frame_el.get("time")
        if raw_time is not None:
            try:
                times_ms.append(float(raw_time))
            except ValueError:
                times_ms.append(len(times_ms) * (1000.0 / frame_rate if frame_rate else 1.0))
        else:
            times_ms.append(len(times_ms) * (1000.0 / frame_rate if frame_rate else 1.0))
        angle_rows.append(values)

    if not angle_rows:
        raise ParseError(
            "No usable motion frames with joint angles were found.",
            path=str(path),
        )

    angles = np.vstack(angle_rows)  # (frames, joints*3)
    time_s = np.asarray(times_ms, dtype=float) / 1000.0
    time_s = time_s - time_s[0]

    if frame_rate <= 0:
        diffs = np.diff(time_s)
        good = diffs[diffs > 0]
        if good.size:
            frame_rate = float(1.0 / np.median(good))
        else:
            frame_rate = float(config.get("sampling.xsens_hz", 60.0))
            warnings.append(f"Frame rate not declared; assumed {frame_rate:g} Hz.")

    # Flexion/extension is the Z component (third value) of the ZXY output —
    # standard MVNX joint-angle ordering. Kept as documented assumption.
    joint_angles: dict[str, np.ndarray] = {}
    for j_idx, label in enumerate(joint_labels):
        base = j_idx * 3
        joint_angles[f"{label}_abduction_deg"] = angles[:, base]
        joint_angles[f"{label}_rotation_deg"] = angles[:, base + 1]
        joint_angles[f"{label}_flexion_deg"] = angles[:, base + 2]

    log.info(
        "Parsed MVNX %s: %d frames, %d joints @ %.1f Hz",
        path.name,
        angles.shape[0],
        len(joint_labels),
        frame_rate,
    )
    return XsensData(
        time_s=time_s,
        joint_angles_deg=joint_angles,
        sampling_rate_hz=frame_rate,
        source_path=path,
        warnings=warnings,
    )
