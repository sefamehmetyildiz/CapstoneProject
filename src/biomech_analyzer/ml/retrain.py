"""Self-retraining of the condition classifier from stored history.

Per the methodology agreed with the Software Engineering advisor, the ML
model is a RESEARCH-ORIENTED classifier of the experimental condition
(baseline / upright / cognitive) — condition labels come for free from the
trial identity, so no external ground-truth is needed and the model can be
retrained at any time from every analysis accumulated in the local SQLite
database ("kendi kendini eğitme"). Injury-risk assessment stays with the
separate interpretable rule-based / profile-comparison layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import MLError
from biomech_analyzer.ml.train import TrainingOutput, export_model, train_and_evaluate
from biomech_analyzer.storage.sqlite_repository import SqliteRepository

log = logging.getLogger(__name__)

_META = ["participant_id", "trial_id", "task", "condition"]


@dataclass
class RetrainResult:
    output: TrainingOutput
    model_path: Path
    n_participants: int
    n_trials: int


def build_condition_table(repo: SqliteRepository) -> pd.DataFrame:
    """Pivot stored feature rows into one row per trial with a condition label."""
    rows = repo.latest_feature_rows()
    if not rows:
        raise MLError(
            "No stored analyses found in the local database.",
            hint="Run and save at least one analysis before retraining.",
        )
    df = pd.DataFrame(rows)
    table = df.pivot_table(
        index=_META, columns="name", values="value", aggfunc="first"
    ).reset_index()
    table.columns.name = None
    return table


def retrain_condition_model(
    db_path: Path, config: Config, model_out: Path | None = None
) -> RetrainResult:
    """Retrain the condition classifier on all stored history.

    Uses leave-one-subject-out cross-validation grouped by participant,
    then fits the final model on all data and exports it.
    """
    with SqliteRepository(db_path) as repo:
        table = build_condition_table(repo)

    feature_cols = [c for c in table.columns if c not in _META]
    if not feature_cols:
        raise MLError("Stored analyses contain no feature values.")
    x = table[feature_cols].astype(float)
    x = x.fillna(x.median(numeric_only=True))
    all_nan = [c for c in x.columns if x[c].isna().all()]
    if all_nan:
        x = x.drop(columns=all_nan)
    y = table["condition"].astype(str)
    groups = table["participant_id"].astype(str)

    if groups.nunique() < 2:
        raise MLError(
            "Retraining needs analyses from at least 2 participants "
            f"(found {groups.nunique()})."
        )
    if y.nunique() < 2:
        raise MLError("Retraining needs at least 2 different conditions in history.")

    output = train_and_evaluate(x, y, groups, config)
    output.evaluation.warnings.append(
        "Condition-classification model (baseline/upright/cognitive): "
        "research-oriented output; injury-risk assessment remains with the "
        "interpretable rule-based layer."
    )
    if model_out is None:
        model_out = (
            Path(config.get("ml.model_dir", "output/models"))
            / "condition_classifier.joblib"
        )
    export_model(output, model_out)
    log.info(
        "Condition model retrained on %d trials from %d participants",
        len(table),
        groups.nunique(),
    )
    return RetrainResult(
        output=output,
        model_path=model_out,
        n_participants=int(groups.nunique()),
        n_trials=len(table),
    )
