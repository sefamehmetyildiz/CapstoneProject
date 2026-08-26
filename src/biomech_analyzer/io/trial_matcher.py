"""Flexible, token-based classification of trial data files.

No official naming convention was available at development time (see
docs/inspection_report.md), so classification is keyword-based and
case-insensitive: the task (SLVJ/SLDJ), condition (baseline/upright/
cognitive) and modality (force plate / EMG / Xsens) are each recognized
from the file extension and from tokens anywhere in the file name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from biomech_analyzer.core.constants import (
    CONDITION_KEYWORDS,
    MODALITY_EXTENSIONS,
    MODALITY_KEYWORDS,
    TASK_KEYWORDS,
    Condition,
    Modality,
    Task,
)
from biomech_analyzer.utils.file_utils import normalize_token

log = logging.getLogger(__name__)


@dataclass
class FileClassification:
    """Classification outcome for a single file."""

    path: Path
    modality: Modality | None
    task: Task | None
    condition: Condition | None

    @property
    def is_trial_file(self) -> bool:
        return (
            self.modality is not None
            and self.task is not None
            and self.condition is not None
        )


def _tokens(stem: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", normalize_token(stem)) if t]


def _match_keywords(stem: str, tokens: list[str], keywords: tuple[str, ...]) -> bool:
    for kw in keywords:
        kw_norm = normalize_token(kw)
        # Multi-character keywords may match as substrings; very short
        # keywords ("dt", "vj", "fp"...) must match a whole token to avoid
        # false positives such as "dt" inside "width".
        if len(kw_norm) <= 2 or "_" in kw_norm:
            if kw_norm in tokens or kw_norm.replace("_", "") in tokens:
                return True
        elif kw_norm in stem:
            return True
    return False


def _resolve_csv_modality(path: Path, stem: str, tokens: list[str]) -> Modality:
    """Decide whether a .csv file is a force plate or a Delsys EMG export.

    Real datasets contain both: Bertec force exports AND Delsys
    "Plot and Store" EMG exports share the .csv extension. Resolution order:
    filename keywords -> parent-folder keywords -> content sniff of the
    first bytes (Delsys files start with "Label: ... EMG ..." metadata,
    Bertec files have an Fx/Fy/Fz header). Defaults to force plate.
    """
    if _match_keywords(stem, tokens, MODALITY_KEYWORDS[Modality.EMG]):
        return Modality.EMG
    if _match_keywords(stem, tokens, MODALITY_KEYWORDS[Modality.FORCE_PLATE]):
        return Modality.FORCE_PLATE
    for parent in list(path.parents)[:2]:
        p_stem = normalize_token(parent.name)
        p_tokens = _tokens(parent.name)
        if _match_keywords(p_stem, p_tokens, MODALITY_KEYWORDS[Modality.FORCE_PLATE]):
            return Modality.FORCE_PLATE
        if _match_keywords(p_stem, p_tokens, MODALITY_KEYWORDS[Modality.EMG]):
            return Modality.EMG
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            head = fh.read(2048).lower()
    except OSError:
        return Modality.FORCE_PLATE
    if "label:" in head and "emg" in head:
        return Modality.EMG
    if "x[s]" in head:
        return Modality.EMG
    return Modality.FORCE_PLATE


def classify_file(path: Path) -> FileClassification:
    """Classify one file into (modality, task, condition), best effort."""
    stem = normalize_token(path.stem)
    tokens = _tokens(path.stem)
    ext = path.suffix.lower()

    modality: Modality | None = None
    if ext == ".csv":
        modality = _resolve_csv_modality(path, stem, tokens)
    else:
        # Non-CSV extensions are unambiguous.
        for mod, exts in MODALITY_EXTENSIONS.items():
            if ext in exts and ext != ".csv":
                modality = mod
                break
    if modality is None:
        for mod, kws in MODALITY_KEYWORDS.items():
            if _match_keywords(stem, tokens, kws):
                modality = mod
                break

    task: Task | None = None
    for t, kws in TASK_KEYWORDS.items():
        if _match_keywords(stem, tokens, kws):
            task = t
            break

    condition: Condition | None = None
    for c, kws in CONDITION_KEYWORDS.items():
        if _match_keywords(stem, tokens, kws):
            condition = c
            break

    result = FileClassification(path=path, modality=modality, task=task, condition=condition)
    log.debug(
        "Classified %s -> modality=%s task=%s condition=%s",
        path.name,
        modality,
        task,
        condition,
    )
    return result
