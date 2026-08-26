"""Delsys "Plot and Store" EMG CSV parser.

Real exports look like::

    Label: R TIBIALIS ANTERIOR (2): EMG 2 Sampling frequency: 2.148148e+003 ...
    ... (one Label line per channel) ...
    Start Trigger Method: ...
    Stop Trigger Method: ...

    X[s],"R TIBIALIS ANTERIOR (2): EMG 2",X[s],"R GASTROCNEMIUS ...",...
    0.000000,0.0000012,0.000000,...

Each channel has its own ``X[s]`` time column; in practice all channels
share the same rate and length, which is verified here.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.core.models import EmgData

log = logging.getLogger(__name__)

_FS_PATTERN = re.compile(r"sampling frequency:\s*([0-9.eE+\-]+)", re.IGNORECASE)
_MAX_HEADER_SCAN = 40


def _is_time_column(name: str) -> bool:
    low = name.strip().strip('"').lower()
    return low.startswith("x[") or low == "x" or bool(re.match(r"^x\[s\](\.\d+)?$", low))


def parse_emg_csv(path: Path, config: Config) -> EmgData:
    """Parse a Delsys-style EMG CSV export into :class:`EmgData`."""
    path = Path(path)
    warnings: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            head_lines = [fh.readline() for _ in range(_MAX_HEADER_SCAN)]
    except OSError as exc:
        raise ParseError(f"Cannot read file: {exc}", path=str(path)) from exc

    fs_meta: float | None = None
    header_idx: int | None = None
    for idx, line in enumerate(head_lines):
        if fs_meta is None:
            m = _FS_PATTERN.search(line)
            if m:
                try:
                    fs_meta = float(m.group(1))
                except ValueError:
                    pass
        first_cell = line.split(",", 1)[0].strip().strip('"')
        if _is_time_column(first_cell):
            header_idx = idx
            break
    if header_idx is None:
        raise ParseError(
            "No Delsys EMG data table (X[s] header) was found in the CSV.",
            path=str(path),
            hint="Expected a 'Plot and Store' export with X[s]/channel column pairs.",
        )

    try:
        df = pd.read_csv(path, skiprows=header_idx, encoding="utf-8-sig")
    except Exception as exc:
        raise ParseError(f"EMG CSV table could not be read: {exc}", path=str(path)) from exc
    df = df.dropna(how="all")

    time_cols = [c for c in df.columns if _is_time_column(str(c))]
    chan_cols = [c for c in df.columns if not _is_time_column(str(c))]
    if not time_cols or not chan_cols:
        raise ParseError(
            "EMG CSV does not contain the expected X[s]/channel column pairs.",
            path=str(path),
        )

    channels: dict[str, np.ndarray] = {}
    lengths: list[int] = []
    for col in chan_cols:
        sig = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        valid = np.flatnonzero(~np.isnan(sig))
        if valid.size == 0:
            warnings.append(f"Channel '{col}' contains no numeric samples; skipped.")
            continue
        sig = sig[: valid[-1] + 1]
        name = str(col).strip().strip('"')
        channels[name] = sig
        lengths.append(sig.size)
    if not channels:
        raise ParseError("No usable EMG channels in the CSV.", path=str(path))

    n = min(lengths)
    if len(set(lengths)) > 1:
        warnings.append(
            f"EMG channels have unequal lengths ({min(lengths)}-{max(lengths)} "
            f"samples); all channels truncated to {n} samples."
        )
        channels = {k: v[:n] for k, v in channels.items()}

    time_raw = pd.to_numeric(df[time_cols[0]], errors="coerce").to_numpy(dtype=float)[:n]
    diffs = np.diff(time_raw)
    good = diffs[diffs > 0]
    if fs_meta and fs_meta > 0:
        fs = fs_meta
    elif good.size:
        fs = float(1.0 / np.median(good))
        warnings.append("EMG sampling rate derived from the time column.")
    else:
        fs = float(config.get("sampling.emg_hz", 2000.0))
        warnings.append(f"EMG sampling rate unknown; assumed {fs:g} Hz.")

    time_s = time_raw if good.size else np.arange(n) / fs

    warnings.append(
        "No MVIC normalization values found; EMG amplitudes will be "
        "reported non-normalized and marked as such."
    )
    log.info(
        "Parsed EMG CSV %s: %d channels, %d samples @ %.1f Hz",
        path.name,
        len(channels),
        n,
        fs,
    )
    return EmgData(
        time_s=np.asarray(time_s, dtype=float),
        channels=channels,
        sampling_rate_hz=fs,
        mvic={},
        source_path=path,
        mat_version="csv",
        warnings=warnings,
    )
