"""Optional local SQLite persistence of anonymized analysis results.

Stored: participant ID (anonymous), trial metadata, extracted features,
risk indicators, ML outputs, report path, timestamps, warnings.
Never stored: names, national IDs, contact data, or any directly
identifying information — the schema has no columns for them.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from biomech_analyzer.core.exceptions import StorageError
from biomech_analyzer.core.models import ParticipantResult
from biomech_analyzer.utils.file_utils import ensure_dir

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT NOT NULL,
    analysis_timestamp TEXT NOT NULL,
    folder TEXT NOT NULL,
    report_path TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    ml_output_json TEXT
);
CREATE TABLE IF NOT EXISTS trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    trial_id TEXT NOT NULL,
    task TEXT NOT NULL,
    condition TEXT NOT NULL,
    sync_strategy TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_row_id INTEGER NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    modality TEXT NOT NULL,
    validation_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_row_id INTEGER NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    indicator_id TEXT NOT NULL,
    name TEXT NOT NULL,
    feature TEXT NOT NULL,
    observed_value REAL,
    reference TEXT NOT NULL,
    triggered INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    validation_status TEXT NOT NULL
);
"""


class SqliteRepository:
    """Small repository wrapper over the results database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        ensure_dir(self.db_path.parent)
        try:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not open results database: {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteRepository:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ save

    def save_participant_result(self, result: ParticipantResult) -> int:
        """Persist one analysis run; returns the analysis row id."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO analyses (participant_id, analysis_timestamp, folder,"
                " report_path, warnings_json, ml_output_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    result.participant_id,
                    result.analysis_timestamp,
                    str(result.folder),
                    str(result.report_path) if result.report_path else None,
                    json.dumps(result.warnings),
                    json.dumps(result.ml_output) if result.ml_output else None,
                ),
            )
            analysis_id = int(cur.lastrowid or 0)
            for trial in result.trials:
                cur.execute(
                    "INSERT INTO trials (analysis_id, trial_id, task, condition,"
                    " sync_strategy, warnings_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        analysis_id,
                        trial.trial_id,
                        trial.task.value,
                        trial.condition.value,
                        trial.sync.strategy if trial.sync else None,
                        json.dumps(trial.warnings),
                    ),
                )
                trial_row_id = int(cur.lastrowid or 0)
                cur.executemany(
                    "INSERT INTO features (trial_row_id, name, value, unit,"
                    " modality, validation_status) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (trial_row_id, fv.name, fv.value, fv.unit,
                         fv.modality.value, fv.validation_status)
                        for fv in trial.features.features.values()
                    ],
                )
                cur.executemany(
                    "INSERT INTO risk_indicators (trial_row_id, indicator_id,"
                    " name, feature, observed_value, reference, triggered,"
                    " risk_level, validation_status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (trial_row_id, r.indicator_id, r.name, r.feature,
                         r.observed_value, r.reference, int(r.triggered),
                         r.risk_level.value, r.validation_status)
                        for r in trial.risk_indicators
                    ],
                )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise StorageError(f"Saving results failed: {exc}") from exc
        log.info(
            "Saved analysis %d for participant %s to %s",
            analysis_id,
            result.participant_id,
            self.db_path,
        )
        return analysis_id

    # ----------------------------------------------------------------- query

    def list_analyses(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, participant_id, analysis_timestamp, folder, report_path"
            " FROM analyses ORDER BY id DESC"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def features_for_analysis(self, analysis_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT t.trial_id, f.name, f.value, f.unit, f.modality,"
            " f.validation_status"
            " FROM features f JOIN trials t ON f.trial_row_id = t.id"
            " WHERE t.analysis_id = ? ORDER BY t.trial_id, f.name",
            (analysis_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
