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

    def rebuild_config(self) -> None:
        """Re-load configuration applying the Advanced Settings overrides."""
        self.config = load_config(overrides=self.config_overrides)
