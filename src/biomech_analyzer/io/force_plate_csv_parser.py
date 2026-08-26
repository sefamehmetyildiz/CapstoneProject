"""Force plate CSV parser.

Robust against metadata header rows, delimiter variants, differing column
names (configurable aliases), unit suffixes, and empty rows. Canonical
output units: seconds, newtons, metres.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.core.models import ForcePlateData

log = logging.getLogger(__name__)

_DELIMITERS = [",", ";", "\t"]
_MAX_HEADER_SCAN = 30


def _sniff_table_start(lines: list[str]) -> tuple[int, str]:
    """Locate the header row of the data table and its delimiter.

    The header row is the first row where at least two cells are non-numeric
    text and the following row parses as mostly numeric with the same
    delimiter and column count.
    """
    for idx in range(min(_MAX_HEADER_SCAN, len(lines) - 1)):
        line = lines[idx].strip()
        if not line:
            continue
        for delim in _DELIMITERS:
            cells = [c.strip() for c in line.split(delim)]
            if len(cells) < 2:
                continue
            next_line = ""
            for j in range(idx + 1, min(idx + 4, len(lines))):
                if lines[j].strip():
                    next_line = lines[j]
                    break
            if not next_line:
                continue
            next_cells = [c.strip() for c in next_line.split(delim)]
            if len(next_cells) != len(cells):
                continue
            numeric = sum(1 for c in next_cells if _is_number(c))
            textual = sum(1 for c in cells if c and not _is_number(c))
            if textual >= 2 and numeric >= max(2, len(next_cells) - 1):
                return idx, delim
    raise ParseError(
        "Could not locate a data table (header row + numeric rows) in the CSV.",
        hint="Check that the file is a force plate export with named columns.",
    )


def _is_number(cell: str) -> bool:
    try:
        float(cell)
        return True
    except ValueError:
        return False


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    """First column whose lower-cased name contains any alias (in alias order)."""
    lowered = {c: c.lower() for c in columns}
    for alias in aliases:
        for col, low in lowered.items():
            if alias.lower() in low:
                return col
    return None


def parse_force_plate_csv(path: Path, config: Config) -> ForcePlateData:
    """Parse a force plate CSV export into :class:`ForcePlateData`."""
    path = Path(path)
    warnings: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ParseError(f"Cannot read file: {exc}", path=str(path)) from exc

    lines = raw.splitlines()
    if not lines:
        raise ParseError("File is empty.", path=str(path))

    header_idx, delim = _sniff_table_start(lines)
    if header_idx > 0:
        warnings.append(f"Skipped {header_idx} metadata line(s) before the data table.")

    try:
        df = pd.read_csv(
            path,
            sep=delim,
            skiprows=header_idx,
            encoding="utf-8-sig",
            skip_blank_lines=True,
            quoting=csv.QUOTE_MINIMAL,
        )
    except Exception as exc:  # pandas raises many types here
        raise ParseError(f"CSV table could not be read: {exc}", path=str(path)) from exc

    df = df.dropna(how="all")
    columns = [str(c) for c in df.columns]

    aliases = config.require("force_plate.column_aliases")
    col_map: dict[str, str | None] = {
        key: _find_column(columns, alias_list) for key, alias_list in aliases.items()
    }

    fz_col = col_map.get("fz")
    if fz_col is None:
        lowered_cols = {c.strip().lower() for c in columns}
        if lowered_cols <= {"sync", "aux", "seq", "eventcounter"}:
            raise ParseError(
                "This force plate export contains only synchronization "
                f"channels ({', '.join(columns)}) and no force data.",
                path=str(path),
                hint="Re-export the recording from the Bertec software with "
                "the force channels (Fx, Fy, Fz) included.",
            )
        raise ParseError(
            "No vertical force (Fz) column was found.",
            path=str(path),
            hint=f"Columns present: {', '.join(columns)}. "
            "Add an alias under force_plate.column_aliases.fz in the config.",
        )

    def _numeric(col: str | None) -> np.ndarray | None:
        if col is None:
            return None
        series = pd.to_numeric(df[col], errors="coerce")
        return series.to_numpy(dtype=float)

    fz = _numeric(fz_col)
    assert fz is not None
    n_bad = int(np.isnan(fz).sum())
    if n_bad:
        warnings.append(f"{n_bad} non-numeric Fz sample(s) interpolated.")
        fz = pd.Series(fz).interpolate(limit_direction="both").to_numpy()

    time_col = col_map.get("time")
    if time_col is not None:
        time_s = _numeric(time_col)
        assert time_s is not None
        time_s = pd.Series(time_s).interpolate(limit_direction="both").to_numpy()
        diffs = np.diff(time_s)
        good = diffs[diffs > 0]
        fs = float(1.0 / np.median(good)) if good.size else 0.0
    else:
        fs = float(config.get("sampling.force_plate_hz", 1000.0))
        time_s = np.arange(len(fz)) / fs
        warnings.append(
            f"No time column found; assumed configured rate of {fs:g} Hz."
        )

    if fs <= 0:
        raise ParseError(
            "Sampling rate could not be determined from the time column.",
            path=str(path),
        )

    # Negative-down conventions: decide by the largest-magnitude sample
    # (the landing peak), not the median — recordings that are mostly
    # empty-plate (SLDJ starts on the box) have a near-zero, slightly
    # negative median that must NOT trigger a flip.
    finite = fz[np.isfinite(fz)]
    if finite.size and abs(float(np.min(finite))) > abs(float(np.max(finite))):
        fz = -fz
        warnings.append("Fz sign flipped (export used negative-down convention).")

    data = ForcePlateData(
        time_s=np.asarray(time_s, dtype=float),
        fz_n=np.asarray(fz, dtype=float),
        fx_n=_numeric(col_map.get("fx")),
        fy_n=_numeric(col_map.get("fy")),
        cop_x_m=_numeric(col_map.get("cop_x")),
        cop_y_m=_numeric(col_map.get("cop_y")),
        sampling_rate_hz=fs,
        source_path=path,
        warnings=warnings,
    )
    log.info(
        "Parsed force plate CSV %s: %d samples @ %.1f Hz", path.name, fz.size, fs
    )
    return data
