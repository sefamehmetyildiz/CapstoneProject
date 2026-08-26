"""Research Mode: inference with an exported model bundle.

Outputs are exploratory decision-support information only; the rule-based
scoring and baseline comparison remain the primary interpretable outputs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from biomech_analyzer.core.models import ParticipantResult
from biomech_analyzer.ml.dataset_builder import build_feature_table
from biomech_analyzer.ml.train import load_model_bundle

log = logging.getLogger(__name__)


def predict_participant(result: ParticipantResult, model_path: Path) -> dict:
    """Predict the class of each analyzed trial of one participant.

    Returns a JSON-serializable dict stored in ``ParticipantResult.ml_output``.
    """
    bundle = load_model_bundle(model_path)
    model = bundle["model"]
    columns: list[str] = bundle["feature_columns"]

    table = build_feature_table([result])
    x = table.reindex(columns=columns).astype(float)
    missing = [c for c in columns if c not in table.columns or table[c].isna().all()]
    x = x.fillna(x.median(numeric_only=True)).fillna(0.0)

    predictions = model.predict(x)
    proba = None
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x)

    trials_out = []
    for i, trial_id in enumerate(table["trial_id"]):
        entry: dict = {"trial_id": str(trial_id), "prediction": str(predictions[i])}
        if proba is not None:
            entry["probabilities"] = {
                str(cls): round(float(p), 4)
                for cls, p in zip(
                    bundle.get("classes", model.classes_), proba[i], strict=True
                )
            }
        trials_out.append(entry)

    majority = pd.Series([t["prediction"] for t in trials_out]).mode().iloc[0]
    output = {
        "model_path": str(model_path),
        "trials": trials_out,
        "majority_prediction": str(majority),
        "warnings": (
            [
                "Feature(s) missing at inference time were imputed: "
                + ", ".join(missing)
            ]
            if missing
            else []
        )
        + [
            "Exploratory machine-learning output; not a medical diagnosis and "
            "not the primary decision-support result."
        ],
    }
    log.info(
        "ML inference for %s: majority=%s", result.participant_id, majority
    )
    return output
