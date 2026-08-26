"""Central logging configuration.

Production modules use ``logging`` exclusively (never ``print``); the CLI
and GUI decide verbosity via :func:`setup_logging`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure the root logger once for the whole application.

    Args:
        level: minimum level for console output.
        log_file: optional file that additionally receives DEBUG output.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicate handlers when called twice (e.g. tests + CLI).
    root.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(fh)
