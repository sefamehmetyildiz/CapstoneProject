"""Exception hierarchy for biomech_analyzer.

Every exception carries a user-facing message; the CLI and GUI display
``user_message`` directly, so keep it free of stack-trace jargon.
"""

from __future__ import annotations


class BiomechError(Exception):
    """Base class for all expected application errors."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint

    @property
    def user_message(self) -> str:
        msg = str(self)
        if self.hint:
            msg += f" Hint: {self.hint}"
        return msg


class ConfigError(BiomechError):
    """Configuration file missing, unreadable, or invalid."""


class FolderValidationError(BiomechError):
    """Participant folder does not satisfy input requirements."""


class ParseError(BiomechError):
    """A data file could not be parsed."""

    def __init__(self, message: str, *, path: str | None = None, hint: str | None = None) -> None:
        super().__init__(message, hint=hint)
        self.path = path


class SynchronizationError(BiomechError):
    """Multimodal streams could not be aligned."""


class EventDetectionError(BiomechError):
    """Required biomechanical events could not be detected."""


class BaselineError(BiomechError):
    """Normative baseline dataset missing or malformed."""


class ReportError(BiomechError):
    """PDF report generation failed."""


class StorageError(BiomechError):
    """SQLite storage operation failed."""


class MLError(BiomechError):
    """Research-mode machine learning operation failed."""
