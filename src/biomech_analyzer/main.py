"""Desktop application entry point (``biomech-analyzer-gui``)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from biomech_analyzer.core.logging_config import setup_logging


def main() -> int:
    setup_logging(logging.INFO, log_file=Path("output") / "biomech_analyzer.log")
    from biomech_analyzer.app.gui_main import run_gui

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
