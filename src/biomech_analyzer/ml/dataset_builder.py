"""Research Mode: labeled feature-table construction.

Builds a tabular dataset (one row per trial) from analyzed participants and
an external labels file (``participant_id,label``). Labels come from the
project team; the software never invents them.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from biomech_analyzer.core.exceptions import MLError
from biomech_analyzer.core.models import ParticipantResult

log = logging.getLogger(__name__)

_META_COLUMNS = ["participant_id", "trial_id", "task", "condition", "label"]


def load_labels(path: Path) -> dict[str, str]:
    """Read a ``participant_id,label`` CSV into a mapping."""
    path = Path(path)
    if not path.is_file():
        raise MLError(
            f"Labels file not found: {path}",
            hint="Research Mode needs a CSV with columns participant_id,label.",
        )
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "participant_id" not in df.columns or "label" not in df.columns:
        raise MLError(
            "Labels file must contain 'participant_id' and 'label' columns."
        )
    return {
        str(r["participant_id"]).strip(): str(r["label"]).strip()
        for _, r in df.iterrows()
    }


def build_feature_table(
    results: list[ParticipantResult], labels: dict[str, str] | None = None
) -> pd.DataFrame:
    """One row per analyzed trial; feature columns are the union of all
    extracted features (missing values stay NaN)."""
    rows: list[dict] = []
    for res in results:
        label = (labels or {}).get(res.participant_id)
        for trial in res.trials:
            row: dict = {
                "participant_id": res.participant_id,
                "trial_id": trial.trial_id,
                "task": trial.task.value,
                "condition": trial.condition.value,
                "label": label,
            }
            for name, fv in trial.features.features.items():
                row[name] = fv.value
            rows.append(row)
    if not rows:
        raise MLError("No analyzed trials available to build a feature table.")
    df = pd.DataFrame(rows)
    log.info(
        "Feature table: %d rows, %d feature columns",
        len(df),
        len([c for c in df.columns if c not in _META_COLUMNS]),
    )
    return df


def split_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, groups) for model training.

    Drops rows without a label; missing feature values are median-imputed
    (documented simplification for the exploratory module).
    """
    labeled = df.dropna(subset=["label"])
    if labeled.empty:
        raise MLError(
            "No labeled rows in the feature table.",
            hint="Check that the labels file covers the analyzed participants.",
        )
    feature_cols = [c for c in labeled.columns if c not in _META_COLUMNS]
    if not feature_cols:
        raise MLError("Feature table contains no feature columns.")
    x = labeled[feature_cols].astype(float)
    x = x.fillna(x.median(numeric_only=True))
    # A column that is entirely NaN has no median; drop it explicitly.
    all_nan = [c for c in x.columns if x[c].isna().all()]
    if all_nan:
        log.warning("Dropping all-NaN feature columns: %s", ", ".join(all_nan))
        x = x.drop(columns=all_nan)
    y = labeled["label"].astype(str)
    groups = labeled["participant_id"].astype(str)
    return x, y, groups
