"""Participant folder scanning and validation."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from biomech_analyzer.core.constants import EXPECTED_TRIALS, Modality
from biomech_analyzer.core.exceptions import FolderValidationError
from biomech_analyzer.core.models import (
    FolderValidationReport,
    TrialFile,
    TrialPackage,
)
from biomech_analyzer.io.trial_matcher import classify_file
from biomech_analyzer.utils.file_utils import sanitize_id

log = logging.getLogger(__name__)

#: Extensions we even attempt to classify; anything else is ignored silently
#: (readme files, raw .hpf/.mvn/.mvna recordings, etc. are legitimate
#: folder residents that this software does not process).
_CANDIDATE_EXTENSIONS = {".csv", ".mat", ".mvnx"}

_SUBJECT_PATTERN = re.compile(r"subject\s*(\d+)\s*(.*)", re.IGNORECASE)


def _derive_anonymous_id(folder_name: str) -> tuple[str, str | None]:
    """Derive an anonymous participant ID from the folder name.

    Real data folders are named like ``subject 4 sefa`` — they contain a
    personal name, which must never appear in reports or the database. Such
    names are mapped to ``S04`` and a privacy warning is raised.
    """
    match = _SUBJECT_PATTERN.match(folder_name.strip())
    if match:
        number = int(match.group(1))
        pid = f"S{number:02d}"
        extra = match.group(2).strip()
        warning = None
        if extra:
            warning = (
                f"Folder name '{folder_name}' appears to contain a personal "
                f"name; the anonymous ID '{pid}' is used instead. Please "
                "rename data folders to anonymous IDs only."
            )
        return pid, warning
    return sanitize_id(folder_name), None


def scan_participant_folder(
    folder: Path, participant_id: str | None = None
) -> FolderValidationReport:
    """Scan ``folder``, group data files into trial packages, and validate.

    Args:
        folder: participant folder containing exported data files.
        participant_id: anonymous ID; defaults to the folder name.

    Returns:
        A :class:`FolderValidationReport`; scanning itself never raises for
        content problems (they land in ``errors``/``warnings``), only for a
        missing or unreadable folder.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FolderValidationError(
            f"Participant folder does not exist or is not a directory: {folder}",
            hint="Select the folder that contains the trial CSV/MAT/MVNX files.",
        )

    anonymity_warning: str | None = None
    if participant_id:
        pid = sanitize_id(participant_id)
    else:
        pid, anonymity_warning = _derive_anonymous_id(folder.name)
    report = FolderValidationReport(participant_id=pid, folder=folder)
    if anonymity_warning:
        report.warnings.append(anonymity_warning)

    # Priority when a trial has several repeat exports: files outside an
    # "original" folder first (raw-export copies are deprioritized), then
    # the canonical short name (e.g. "slvjbaseline.csv" beats
    # "slvjbaseline_0004.csv"), then a stable path order.
    def _priority(p: Path) -> tuple:
        in_original = any(parent.name.lower() == "original" for parent in p.parents)
        return (in_original, len(p.stem), str(p).lower())

    candidates = sorted(
        (
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in _CANDIDATE_EXTENSIONS
        ),
        key=_priority,
    )
    if not candidates:
        report.errors.append(
            "No data files (.csv, .mat, .mvnx) were found in the folder."
        )
        return report

    packages: dict[tuple, TrialPackage] = {}
    for path in candidates:
        cls = classify_file(path)
        if not cls.is_trial_file:
            report.unmatched_files.append(path)
            missing_parts = [
                label
                for label, val in (
                    ("modality", cls.modality),
                    ("task (SLVJ/SLDJ)", cls.task),
                    ("condition", cls.condition),
                )
                if val is None
            ]
            report.warnings.append(
                f"Could not assign '{path.name}' to a trial "
                f"(unrecognized {', '.join(missing_parts)})."
            )
            continue

        key = (cls.task, cls.condition)
        pkg = packages.setdefault(
            key, TrialPackage(task=cls.task, condition=cls.condition)  # type: ignore[arg-type]
        )
        assert cls.modality is not None
        if cls.modality in pkg.files:
            try:
                dup_rel = path.relative_to(folder)
                kept_rel = pkg.files[cls.modality].path.relative_to(folder)
            except ValueError:
                dup_rel, kept_rel = path, pkg.files[cls.modality].path
            report.warnings.append(
                f"Duplicate {cls.modality.value} file for trial {pkg.trial_id}: "
                f"'{dup_rel}' ignored (kept '{kept_rel}')."
            )
            report.unmatched_files.append(path)
            continue
        pkg.files[cls.modality] = TrialFile(path=path, modality=cls.modality)

    report.trials = list(packages.values())

    # Completeness against the protocol's six expected trials.
    found_keys = {(t.task, t.condition) for t in report.trials}
    for task, condition in EXPECTED_TRIALS:
        if (task, condition) not in found_keys:
            report.warnings.append(
                f"Expected trial {task.value}_{condition.value} was not found."
            )
    for pkg in report.trials:
        for modality in pkg.missing_modalities:
            report.warnings.append(
                f"Trial {pkg.trial_id} is missing its {modality.value} file."
            )
        if Modality.FORCE_PLATE not in pkg.files:
            report.warnings.append(
                f"Trial {pkg.trial_id} cannot be event-synchronized without a "
                "force plate file and will be skipped in analysis."
            )

    if not report.is_analyzable:
        report.errors.append(
            "No trial contains a force plate CSV file; analysis cannot run."
        )

    log.info(
        "Scanned %s: %d trials, %d unmatched files, %d warnings",
        folder,
        len(report.trials),
        len(report.unmatched_files),
        len(report.warnings),
    )
    return report
