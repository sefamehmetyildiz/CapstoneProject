"""Small filesystem helpers."""

from __future__ import annotations

import re
from pathlib import Path


def normalize_token(text: str) -> str:
    """Lower-case a filename stem and unify separators for keyword matching."""
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def sanitize_id(raw: str) -> str:
    """Keep only characters safe for filenames and database keys."""
    return re.sub(r"[^A-Za-z0-9_\-]", "", raw) or "UNKNOWN"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
