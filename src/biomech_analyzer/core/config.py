"""Configuration loading and access.

The analysis configuration lives in YAML (``config/default_config.yaml``)
so that clinically sensitive parameters are never hard-coded. User-supplied
overrides are deep-merged over the defaults.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from biomech_analyzer.core.exceptions import ConfigError

log = logging.getLogger(__name__)


def _config_root() -> Path:
    """Directory that contains ``config/``.

    In a PyInstaller build the config directory is bundled next to the
    executable; in a source checkout it sits at the repository root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "_internal"
    return Path(__file__).resolve().parents[3]


DEFAULT_CONFIG_PATH = _config_root() / "config" / "default_config.yaml"
DEFAULT_RISK_PATH = _config_root() / "config" / "risk_thresholds.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` recursively updated with ``override``."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Config:
    """Read-only dotted-path access over a merged configuration mapping."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Return the value at ``section.sub.key``, or ``default``."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted_key: str) -> Any:
        """Return the value at ``dotted_key`` or raise :class:`ConfigError`."""
        sentinel = object()
        value = self.get(dotted_key, sentinel)
        if value is sentinel:
            raise ConfigError(
                f"Missing required configuration key '{dotted_key}'.",
                hint="Check config/default_config.yaml.",
            )
        return value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration root must be a mapping: {path}")
    return data


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Config:
    """Load the default configuration, optionally merged with a user file
    and/or an in-memory override mapping (in that precedence order)."""
    data = _load_yaml(DEFAULT_CONFIG_PATH)
    if config_path is not None:
        data = _deep_merge(data, _load_yaml(Path(config_path)))
        log.info("Loaded configuration overrides from %s", config_path)
    if overrides:
        data = _deep_merge(data, overrides)
    return Config(data)


def load_risk_rules(path: Path | None = None) -> list[dict[str, Any]]:
    """Load rule-based risk indicator definitions from YAML."""
    data = _load_yaml(path or DEFAULT_RISK_PATH)
    indicators = data.get("indicators")
    if not isinstance(indicators, list):
        raise ConfigError(
            "risk_thresholds.yaml must contain a top-level 'indicators' list."
        )
    return indicators
