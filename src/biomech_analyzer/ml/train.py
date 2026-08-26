"""Research Mode: model training and export.

Random Forest is the primary baseline classifier (proposal §3.3). The
exported bundle stores the fitted model together with its feature-column
order and class labels so inference cannot silently mis-align columns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import MLError
from biomech_analyzer.ml.evaluate import EvaluationResult, evaluate_loso
from biomech_analyzer.utils.file_utils import ensure_dir

log = logging.getLogger(__name__)

BUNDLE_FORMAT = 1


@dataclass
class TrainingOutput:
    model: RandomForestClassifier
    evaluation: EvaluationResult
    feature_columns: list[str]
    feature_importances: dict[str, float]


def make_classifier(config: Config) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=int(config.get("ml.n_estimators", 200)),
        random_state=int(config.get("ml.random_state", 42)),
        class_weight="balanced",
    )


def train_and_evaluate(
    x: pd.DataFrame, y: pd.Series, groups: pd.Series, config: Config
) -> TrainingOutput:
    """LOSO-evaluate, then fit the final model on all labeled data."""
    model = make_classifier(config)
    evaluation = evaluate_loso(
        model,
        x,
        y,
        groups,
        min_participants=int(config.get("ml.min_participants_warning", 10)),
    )
    model.fit(x, y)
    importances = dict(
        sorted(
            zip(list(x.columns), model.feature_importances_.tolist(), strict=True),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )
    return TrainingOutput(
        model=model,
        evaluation=evaluation,
        feature_columns=list(x.columns),
        feature_importances=importances,
    )


def export_model(output: TrainingOutput, path: Path) -> Path:
    """Persist the fitted model bundle with joblib."""
    path = Path(path)
    ensure_dir(path.parent)
    joblib.dump(
        {
            "format": BUNDLE_FORMAT,
            "model": output.model,
            "feature_columns": output.feature_columns,
            "classes": list(output.model.classes_),
        },
        path,
    )
    log.info("Model exported to %s", path)
    return path


def load_model_bundle(path: Path) -> dict:
    """Load a previously exported model bundle."""
    path = Path(path)
    if not path.is_file():
        raise MLError(f"Model file not found: {path}")
    try:
        bundle = joblib.load(path)
    except Exception as exc:
        raise MLError(f"Model file could not be loaded: {exc}") from exc
    if not isinstance(bundle, dict) or "model" not in bundle or "feature_columns" not in bundle:
        raise MLError(
            "Model file has an unexpected format.",
            hint="Export models with this application's Research Mode.",
        )
    return bundle
