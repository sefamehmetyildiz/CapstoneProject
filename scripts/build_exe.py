"""PyInstaller build script — packages the GUI as a standalone Windows app.

Usage (from the repository root, inside the virtual environment):

    python scripts/build_exe.py

Produces ``dist/BiomechAnalyzer/BiomechAnalyzer.exe`` (one-folder build:
starts faster and is easier to debug than one-file). The config/ directory
is bundled next to the executable so thresholds stay editable after
packaging.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    entry = REPO_ROOT / "src" / "biomech_analyzer" / "main.py"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        "BiomechAnalyzer",
        "--paths",
        str(REPO_ROOT / "src"),
        # Bundle the editable configuration next to the executable.
        "--add-data",
        f"{REPO_ROOT / 'config'};config",
        # Sklearn/scipy occasionally need explicit collection.
        "--collect-submodules",
        "sklearn",
        "--hidden-import",
        "scipy._lib.array_api_compat.numpy.fft",
        str(entry),
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
