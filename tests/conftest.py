"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from biomech_analyzer.core.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def mock_data_dir() -> Path:
    """Session-wide mock dataset; generated on demand if absent."""
    out = REPO_ROOT / "data" / "mock"
    if not (out / "P001").is_dir():
        import generate_mock_data

        generate_mock_data.generate(out)
    return out


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def p001(mock_data_dir: Path) -> Path:
    return mock_data_dir / "P001"


@pytest.fixture(scope="session")
def p003(mock_data_dir: Path) -> Path:
    """The deliberately imperfect participant."""
    return mock_data_dir / "P003"
