"""Shared mutable state passed between GUI screens."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from biomech_analyzer.core.config import Config, load_config
from biomech_analyzer.core.models import FolderValidationReport, ParticipantResult


@dataclass
class AppState:
    """Session state of the desktop application."""

    config: Config = field(default_factory=load_config)
    config_overrides: dict[str, Any] = field(default_factory=dict)
    folder: Path | None = None
    participant_id: str = ""
    baseline_path: Path | None = None
    model_path: Path | None = None
    validation: FolderValidationReport | None = None
    result: ParticipantResult | None = None
    #: PDF report language: "en" or "tr".
    report_language: str = "en"
    #: Row id of the auto-saved analysis in the local SQLite database.
    analysis_id: int | None = None

    @property
    def db_path(self) -> Path:
        return Path(self.config.get("storage.sqlite_path", "output/results.sqlite3"))

    def rebuild_config(self) -> None:
        """Re-load configuration applying the Advanced Settings overrides."""
        self.config = load_config(overrides=self.config_overrides)
