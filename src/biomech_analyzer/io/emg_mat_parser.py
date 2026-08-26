"""sEMG / Delsys MAT parser with MATLAB version detection.

Standard MAT files (<= v7.2) are read with ``scipy.io.loadmat``; MATLAB
v7.3 files are HDF5 containers and are read with ``h5py``. The version is
sniffed from the 128-byte MAT header, with an HDF5-signature fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

from biomech_analyzer.core.config import Config
from biomech_analyzer.core.exceptions import ParseError
from biomech_analyzer.core.models import EmgData

log = logging.getLogger(__name__)

#: Key-name candidates (case-insensitive) for each expected field.
_FIELD_CANDIDATES = {
    "data": ["data", "signals", "emg", "channels_data"],
    "fs": ["fs", "samplingfrequency", "sampling_rate", "samplerate", "srate", "frequency"],
    "time": ["time", "t", "timestamps"],
    "channels": ["channels", "channel_names", "labels", "names", "muscles"],
    "mvic_names": ["mvic_names", "mvicnames"],
    "mvic_values": ["mvic_values", "mvic", "mvicvalues"],
}


def detect_mat_version(path: Path) -> str:
    """Return ``'v7.3'``, ``'v5'``, or ``'unknown'`` for a .mat file."""
    try:
        with path.open("rb") as fh:
            header = fh.read(128)
    except OSError as exc:
        raise ParseError(f"Cannot read file: {exc}", path=str(path)) from exc
    if header.startswith(b"\x89HDF\r\n\x1a\n"):
        return "v7.3"
    text = header[:116].decode("ascii", errors="replace")
    if "MATLAB 7.3" in text:
        return "v7.3"
    if "MATLAB" in text:
        return "v5"
    return "unknown"


def _match_key(available: dict[str, Any], candidates: list[str]) -> str | None:
    lowered = {k.lower(): k for k in available}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    # substring fallback
    for cand in candidates:
        for low, orig in lowered.items():
            if cand in low:
                return orig
    return None


def _decode_names(raw: Any) -> list[str]:
    """Normalize channel-name containers from either reader into strings."""
    names: list[str] = []
    arr = np.asarray(raw).ravel()
    for item in arr:
        if isinstance(item, bytes):
            names.append(item.decode("utf-8", errors="replace"))
        elif isinstance(item, str):
            names.append(item)
        elif isinstance(item, np.ndarray):
            # scipy cell arrays nest strings inside object arrays
            flat = item.ravel()
            names.append(str(flat[0]) if flat.size else "")
        else:
            names.append(str(item))
    return [n.strip() for n in names]


def _load_v5(path: Path) -> dict[str, Any]:
    try:
        return {
            k: v
            for k, v in loadmat(str(path), squeeze_me=False).items()
            if not k.startswith("__")
        }
    except Exception as exc:
        raise ParseError(
            f"scipy.io could not read the MAT file: {exc}", path=str(path)
        ) from exc


def _load_v73(path: Path) -> dict[str, Any]:
    try:
        out: dict[str, Any] = {}
        with h5py.File(path, "r") as f:

            def visit(name: str, obj: Any) -> None:
                if isinstance(obj, h5py.Dataset):
                    out[name.split("/")[-1]] = obj[()]

            f.visititems(visit)
        return out
    except Exception as exc:
        raise ParseError(
            f"h5py could not read the MATLAB v7.3 file: {exc}", path=str(path)
        ) from exc


def parse_emg_mat(path: Path, config: Config) -> EmgData:
    """Parse a Delsys-style MAT export into :class:`EmgData`."""
    path = Path(path)
    warnings: list[str] = []
    version = detect_mat_version(path)

    if version == "v7.3":
        contents = _load_v73(path)
    else:
        if version == "unknown":
            warnings.append(
                "MAT header not recognized; attempted standard reader first."
            )
        try:
            contents = _load_v5(path)
        except ParseError:
            contents = _load_v73(path)  # last-resort fallback
            version = "v7.3"

    if not contents:
        raise ParseError("MAT file contains no variables.", path=str(path))

    data_key = _match_key(contents, _FIELD_CANDIDATES["data"])
    if data_key is None:
        raise ParseError(
            "No EMG signal matrix found in the MAT file.",
            path=str(path),
            hint=f"Variables present: {', '.join(sorted(contents))}.",
        )
    data = np.atleast_2d(np.asarray(contents[data_key], dtype=float))
    # Convention: channels on the shorter axis.
    if data.shape[0] > data.shape[1]:
        data = data.T

    fs_key = _match_key(contents, _FIELD_CANDIDATES["fs"])
    if fs_key is not None:
        fs = float(np.asarray(contents[fs_key]).ravel()[0])
    else:
        fs = float(config.get("sampling.emg_hz", 2000.0))
        warnings.append(f"No sampling-rate variable found; assumed {fs:g} Hz.")
    if fs <= 0:
        raise ParseError("EMG sampling rate is non-positive.", path=str(path))

    time_key = _match_key(contents, _FIELD_CANDIDATES["time"])
    time_s: np.ndarray
    if time_key is not None:
        time_arr = np.asarray(contents[time_key], dtype=float)
        n_samples = data.shape[1]
        if time_arr.ndim == 2 and n_samples in time_arr.shape:
            # Delsys exports store one time row per channel; rows are equal,
            # so the first row along the sample axis is the time base.
            time_s = time_arr[0] if time_arr.shape[1] == n_samples else time_arr[:, 0]
        else:
            time_s = time_arr.ravel()
        if time_s.size != n_samples:
            warnings.append(
                "Time vector length differs from signal length; rebuilt from Fs."
            )
            time_s = np.arange(n_samples) / fs
    else:
        time_s = np.arange(data.shape[1]) / fs

    chan_key = _match_key(contents, _FIELD_CANDIDATES["channels"])
    if chan_key is not None:
        names = _decode_names(contents[chan_key])
        if len(names) != data.shape[0]:
            warnings.append(
                f"{len(names)} channel names for {data.shape[0]} signals; "
                "generic names used."
            )
            names = [f"CH{i + 1}" for i in range(data.shape[0])]
    else:
        names = [f"CH{i + 1}" for i in range(data.shape[0])]
        warnings.append("No channel-name variable found; generic names used.")

    channels = {name: data[i] for i, name in enumerate(names)}

    mvic: dict[str, float] = {}
    mn_key = _match_key(contents, _FIELD_CANDIDATES["mvic_names"])
    mv_key = _match_key(contents, _FIELD_CANDIDATES["mvic_values"])
    if mn_key is not None and mv_key is not None:
        mvic_names = _decode_names(contents[mn_key])
        mvic_values = np.asarray(contents[mv_key], dtype=float).ravel()
        # strict=False: name/value lists of unequal length pair as far as
        # possible; the mismatch case is handled by lookup misses downstream.
        mvic = dict(zip(mvic_names, mvic_values.tolist(), strict=False))
    else:
        warnings.append(
            "No MVIC normalization values found; EMG amplitudes will be "
            "reported non-normalized and marked as such."
        )

    log.info(
        "Parsed EMG MAT %s (%s): %d channels @ %.1f Hz",
        path.name,
        version,
        len(channels),
        fs,
    )
    return EmgData(
        time_s=time_s,
        channels=channels,
        sampling_rate_hz=fs,
        mvic=mvic,
        source_path=path,
        mat_version=version,
        warnings=warnings,
    )
