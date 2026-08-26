"""Normative baseline dataset loader (CSV or Excel).

Schema documented in ``config/baseline_schema.yaml``: one row per feature
with normative ``mean`` and ``std``, optionally scoped by task, condition
and sex. Matching precedence: exact scope > partial > ALL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from biomech_analyzer.core.exceptions import BaselineError

log = logging.getLogger(__name__)

_REQUIRED = {"feature", "mean", "std"}
_ALL = "ALL"


@dataclass
class BaselineEntry:
    feature: str
    mean: float
    std: float
    task: str = _ALL
    condition: str = _ALL
    sex: str = _ALL
    unit: str = ""


class BaselineDataset:
    """In-memory normative baseline with scoped lookup."""

    def __init__(self, entries: list[BaselineEntry], source: Path | None = None) -> None:
        self.entries = entries
        self.source = source

    def lookup(
        self, feature: str, task: str = _ALL, condition: str = _ALL, sex: str = _ALL
    ) -> BaselineEntry | None:
        """Best-scoped entry for a feature, or ``None`` when absent."""
        candidates = [e for e in self.entries if e.feature.lower() == feature.lower()]
        if not candidates:
            return None

        def score(e: BaselineEntry) -> int:
            s = 0
            for want, have in ((task, e.task), (condition, e.condition), (sex, e.sex)):
                if have.upper() == _ALL:
                    continue
                if want.upper() == have.upper():
                    s += 1
                else:
                    return -1  # scoped to a different context: unusable
            return s

        scored = [(score(e), e) for e in candidates]
        scored = [(s, e) for s, e in scored if s >= 0]
        if not scored:
            return None
        return max(scored, key=lambda t: t[0])[1]

    @property
    def feature_names(self) -> list[str]:
        return sorted({e.feature for e in self.entries})


def load_baseline(path: Path) -> BaselineDataset:
    """Load a baseline dataset from CSV or XLSX."""
    path = Path(path)
    if not path.is_file():
        raise BaselineError(
            f"Baseline dataset not found: {path}",
            hint="Provide the normative baseline CSV/XLSX from the BME team.",
        )
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path)
    except Exception as exc:
        raise BaselineError(f"Baseline file could not be read: {exc}") from exc

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise BaselineError(
            f"Baseline file is missing required column(s): {', '.join(sorted(missing))}.",
            hint="See config/baseline_schema.yaml for the expected schema.",
        )

    entries: list[BaselineEntry] = []
    for _, row in df.iterrows():
        try:
            mean = float(row["mean"])
            std = float(row["std"])
        except (TypeError, ValueError):
            log.warning("Skipping baseline row with non-numeric mean/std: %s", dict(row))
            continue
        entries.append(
            BaselineEntry(
                feature=str(row["feature"]).strip(),
                mean=mean,
                std=std,
                task=str(row.get("task", _ALL) or _ALL).strip() or _ALL,
                condition=str(row.get("condition", _ALL) or _ALL).strip() or _ALL,
                sex=str(row.get("sex", _ALL) or _ALL).strip() or _ALL,
                unit=str(row.get("unit", "") or ""),
            )
        )
    if not entries:
        raise BaselineError("Baseline file contains no usable rows.")
    log.info("Loaded baseline dataset %s with %d entries", path.name, len(entries))
    return BaselineDataset(entries, source=path)
