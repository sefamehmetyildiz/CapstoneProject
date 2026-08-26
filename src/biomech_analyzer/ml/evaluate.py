"""Research Mode: leave-one-subject-out evaluation.

Trials of the same participant are never split between train and test
(participant-level grouping prevents data leakage, per proposal §7.3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import LeaveOneGroupOut

from biomech_analyzer.core.exceptions import MLError

log = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    accuracy: float
    precision: float
    recall: float
    f1: float
    confusion: list[list[int]]
    class_labels: list[str]
    n_participants: int
    n_trials: int
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Leave-one-subject-out CV over {self.n_participants} participants "
            f"({self.n_trials} trials)",
            f"Accuracy:  {self.accuracy:.3f}",
            f"Precision: {self.precision:.3f} (macro)",
            f"Recall:    {self.recall:.3f} (macro)",
            f"F1-score:  {self.f1:.3f} (macro)",
            "Confusion matrix (rows=true, cols=predicted, order: "
            + ", ".join(self.class_labels) + "):",
        ]
        lines.extend("  " + "  ".join(f"{v:4d}" for v in row) for row in self.confusion)
        lines.extend(f"WARNING: {w}" for w in self.warnings)
        return lines


def evaluate_loso(
    model, x: pd.DataFrame, y: pd.Series, groups: pd.Series, min_participants: int = 10
) -> EvaluationResult:
    """Leave-one-subject-out cross-validation of ``model`` (unfitted)."""
    warnings: list[str] = []
    n_participants = groups.nunique()
    if n_participants < 2:
        raise MLError(
            "Leave-one-subject-out CV needs at least 2 participants."
        )
    if n_participants < min_participants:
        warnings.append(
            f"Only {n_participants} participants available: results are "
            "exploratory and must not be treated as reliable model performance."
        )
    counts = y.value_counts()
    if len(counts) < 2:
        raise MLError("Need at least two classes in the labels for classification.")
    if counts.min() / counts.max() < 0.5:
        warnings.append(
            f"Class distribution is imbalanced ({dict(counts)}); interpret "
            "metrics with caution."
        )

    logo = LeaveOneGroupOut()
    y_true_all: list[str] = []
    y_pred_all: list[str] = []
    for train_idx, test_idx in logo.split(x, y, groups):
        fold_model = clone(model)
        fold_model.fit(x.iloc[train_idx], y.iloc[train_idx])
        preds = fold_model.predict(x.iloc[test_idx])
        y_true_all.extend(y.iloc[test_idx].tolist())
        y_pred_all.extend(list(preds))

    labels = sorted(set(y_true_all))
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true_all, y_pred_all, labels=labels, average="macro", zero_division=0
    )
    cm = confusion_matrix(y_true_all, y_pred_all, labels=labels)
    result = EvaluationResult(
        accuracy=float(accuracy_score(y_true_all, y_pred_all)),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        confusion=np.asarray(cm).astype(int).tolist(),
        class_labels=labels,
        n_participants=int(n_participants),
        n_trials=len(y),
        warnings=warnings,
    )
    log.info("LOSO evaluation: accuracy=%.3f f1=%.3f", result.accuracy, result.f1)
    return result
