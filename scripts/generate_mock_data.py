"""Generate synthetic mock data for pipeline testing.

No mock data was provided in the workspace (see docs/inspection_report.md),
so this script fabricates physically plausible — but NOT biomechanically
valid — files mimicking the expected exports:

* Bertec-style force plate CSV (1000 Hz) with metadata header rows
* Delsys-style sEMG MAT files, both MATLAB v5 and v7.3 (HDF5)
* Xsens MVNX (XML) files with joint angle frames (60 Hz)
* A normative baseline CSV and a Research-Mode labels CSV

Participants: P001, P002 (complete), P003 (deliberately imperfect: one
missing EMG file, one unrecognizable file name) to exercise validation.

Deterministic: fixed RNG seed per participant/trial.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import savemat

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "mock"

TASKS = ["SLVJ", "SLDJ"]
CONDITIONS = ["baseline", "upright", "cognitive"]

FORCE_FS = 1000.0
EMG_FS = 2000.0
XSENS_FS = 60.0
DURATION_S = 5.0

EMG_CHANNELS = [
    "R Vastus Lateralis",
    "R Rectus Femoris",
    "R Biceps Femoris",
    "R Semitendinosus",
    "R Gastrocnemius Med",
    "R Tibialis Anterior",
    "R Gluteus Medius",
    "R Vastus Medialis",
]

XSENS_JOINTS = ["jRightHip", "jRightKnee", "jRightAnkle"]


def _jump_fz_profile(t: np.ndarray, bw_n: float, rng: np.random.Generator) -> np.ndarray:
    """Quiet stance -> countermovement -> push-off -> flight -> landing -> settle."""
    fz = np.full_like(t, bw_n)
    # countermovement dip 1.0-1.4 s
    dip = (t >= 1.0) & (t < 1.4)
    fz[dip] = bw_n * (1 - 0.4 * np.sin(np.pi * (t[dip] - 1.0) / 0.4))
    # push-off peak 1.4-1.8 s
    push = (t >= 1.4) & (t < 1.8)
    fz[push] = bw_n * (1 + 1.2 * np.sin(np.pi * (t[push] - 1.4) / 0.4))
    # flight 1.8-2.2 s
    flight = (t >= 1.8) & (t < 2.2)
    fz[flight] = 0.0
    # landing spike 2.2-2.35 s (~2.8 BW)
    land = (t >= 2.2) & (t < 2.35)
    fz[land] = bw_n * 2.8 * np.exp(-((t[land] - 2.24) ** 2) / (2 * 0.02**2))
    # damped oscillation back to BW
    settle = t >= 2.35
    ts = t[settle] - 2.35
    fz[settle] = bw_n * (1 + 0.5 * np.exp(-3 * ts) * np.cos(2 * np.pi * 4 * ts))
    fz += rng.normal(0, 2.0, size=t.size)
    return np.clip(fz, 0, None)


def write_force_csv(path: Path, seed: int, bw_n: float) -> None:
    rng = np.random.default_rng(seed)
    t = np.arange(0, DURATION_S, 1 / FORCE_FS)
    fz = _jump_fz_profile(t, bw_n, rng)
    fx = rng.normal(0, 15, t.size) * (fz > 10)
    fy = rng.normal(0, 15, t.size) * (fz > 10)
    cop_x = 0.02 * np.sin(2 * np.pi * 0.5 * t) + rng.normal(0, 0.002, t.size)
    cop_y = 0.015 * np.cos(2 * np.pi * 0.3 * t) + rng.normal(0, 0.002, t.size)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("Bertec Force Plate Export\n")
        fh.write(f"Sample Rate:,{FORCE_FS}\n")
        fh.write("\n")
        fh.write("Time (s),Fx (N),Fy (N),Fz (N),COP X (m),COP Y (m)\n")
        for i in range(t.size):
            fh.write(
                f"{t[i]:.4f},{fx[i]:.3f},{fy[i]:.3f},{fz[i]:.3f},"
                f"{cop_x[i]:.5f},{cop_y[i]:.5f}\n"
            )


def _emg_signals(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.arange(0, DURATION_S, 1 / EMG_FS)
    n_ch = len(EMG_CHANNELS)
    data = np.zeros((n_ch, t.size))
    for ch in range(n_ch):
        noise = rng.normal(0, 0.01, t.size)
        # activation bursts around push-off (1.4-1.8) and landing (2.15-2.6),
        # slight pre-activation before contact at 2.2 s
        burst = np.zeros_like(t)
        burst += 0.4 * np.exp(-((t - 1.6) ** 2) / (2 * 0.15**2))
        burst += (0.6 + 0.05 * ch) * np.exp(-((t - 2.3) ** 2) / (2 * 0.12**2))
        carrier = rng.normal(0, 1, t.size)
        data[ch] = noise + burst * carrier * 0.5
    return t, data


def write_emg_mat_v5(path: Path, seed: int) -> None:
    t, data = _emg_signals(seed)
    mvic = 0.8 + 0.05 * np.arange(len(EMG_CHANNELS))
    savemat(
        str(path),
        {
            "Fs": EMG_FS,
            "Time": t,
            "Data": data,
            "Channels": np.array(EMG_CHANNELS, dtype=object),
            "MVIC_names": np.array(EMG_CHANNELS, dtype=object),
            "MVIC_values": mvic,
        },
    )


def write_emg_mat_v73(path: Path, seed: int) -> None:
    t, data = _emg_signals(seed)
    mvic = 0.8 + 0.05 * np.arange(len(EMG_CHANNELS))
    str_dt = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w", userblock_size=512) as f:
        f.create_dataset("Fs", data=np.array([[EMG_FS]]))
        f.create_dataset("Time", data=t.reshape(1, -1))
        f.create_dataset("Data", data=data)
        f.create_dataset("Channels", data=np.array(EMG_CHANNELS, dtype=str_dt))
        f.create_dataset("MVIC_names", data=np.array(EMG_CHANNELS, dtype=str_dt))
        f.create_dataset("MVIC_values", data=mvic)
    # Stamp a MATLAB v7.3 header into the userblock so version sniffing works.
    header = b"MATLAB 7.3 MAT-file, Platform: mock generator"
    block = header + b" " * (116 - len(header)) + b"\x00" * 8 + b"\x02\x00" + b"IM"
    with path.open("r+b") as fh:
        fh.write(block)


def write_mvnx(path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    t = np.arange(0, DURATION_S, 1 / XSENS_FS)
    # knee flexion trace: small during stance, deep flexion at landing
    knee = 15 + 45 * np.exp(-((t - 2.35) ** 2) / (2 * 0.15**2))
    knee += 20 * np.exp(-((t - 1.3) ** 2) / (2 * 0.2**2))
    hip = 10 + 30 * np.exp(-((t - 2.35) ** 2) / (2 * 0.2**2))
    ankle = 5 + 20 * np.exp(-((t - 2.3) ** 2) / (2 * 0.1**2))
    joints_xyz = {
        "jRightHip": hip,
        "jRightKnee": knee,
        "jRightAnkle": ankle,
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<mvnx xmlns="http://www.xsens.com/mvn/mvnx" version="4">',
        f'  <subject label="Mock" frameRate="{int(XSENS_FS)}">',
        "    <joints>",
    ]
    for j in XSENS_JOINTS:
        lines.append(f'      <joint label="{j}"/>')
    lines.append("    </joints>")
    lines.append("    <frames>")
    for i, ti in enumerate(t):
        vals: list[str] = []
        for j in XSENS_JOINTS:
            flex = joints_xyz[j][i] + rng.normal(0, 0.3)
            abd = rng.normal(0, 1.5)
            rot = rng.normal(0, 1.5)
            # MVNX order per joint: abduction(X), rotation(Y), flexion(Z)
            vals += [f"{abd:.3f}", f"{rot:.3f}", f"{flex:.3f}"]
        lines.append(
            f'      <frame time="{int(ti * 1000)}" index="{i}" type="normal">'
            f"<jointAngle>{' '.join(vals)}</jointAngle></frame>"
        )
    lines += ["    </frames>", "  </subject>", "</mvnx>"]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_baseline_csv(path: Path) -> None:
    rows = [
        ("peak_vgrf_bw", 2.6, 0.4, "ALL", "ALL", "BW"),
        ("rfd_n_per_s", 12000.0, 3500.0, "ALL", "ALL", "N/s"),
        ("rsi", 1.1, 0.3, "SLDJ", "ALL", "m/s"),
        ("time_to_stabilization_s", 0.9, 0.3, "ALL", "ALL", "s"),
        ("landing_impulse_ns", 180.0, 40.0, "ALL", "ALL", "N*s"),
        ("cop_path_length_m", 0.35, 0.12, "ALL", "ALL", "m"),
        ("peak_knee_flexion_deg", 58.0, 10.0, "ALL", "ALL", "deg"),
        ("knee_rom_deg", 40.0, 9.0, "ALL", "ALL", "deg"),
        ("preactivation_ratio", 0.25, 0.10, "ALL", "ALL", "ratio"),
        ("hq_activation_ratio", 0.9, 0.25, "ALL", "ALL", "ratio"),
        ("jump_height_m", 0.18, 0.05, "ALL", "ALL", "m"),
    ]
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("feature,mean,std,task,condition,unit\n")
        for r in rows:
            fh.write(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}\n")


def write_labels_csv(path: Path, participants: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("participant_id,label\n")
        for i, pid in enumerate(participants):
            fh.write(f"{pid},{'high_risk' if i % 2 else 'low_risk'}\n")


def generate(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    participants = ["P001", "P002", "P003"]
    for p_idx, pid in enumerate(participants):
        pdir = out_dir / pid
        pdir.mkdir(exist_ok=True)
        bw = 650 + 60 * p_idx
        for t_idx, task in enumerate(TASKS):
            for c_idx, cond in enumerate(CONDITIONS):
                seed = 1000 * (p_idx + 1) + 10 * t_idx + c_idx
                stem = f"{task}_{cond}"
                # P003 imperfections: missing EMG for SLDJ_cognitive and a
                # cryptic file name for SLVJ_upright force data.
                force_name = f"{stem}_force.csv"
                if pid == "P003" and stem == "SLVJ_upright":
                    force_name = "trial_007_export.csv"  # unclassifiable on purpose
                write_force_csv(pdir / force_name, seed, bw)
                skip_emg = pid == "P003" and stem == "SLDJ_cognitive"
                if not skip_emg:
                    # Alternate MAT versions to exercise both readers.
                    if (t_idx + c_idx) % 2 == 0:
                        write_emg_mat_v5(pdir / f"{stem}_emg.mat", seed + 1)
                    else:
                        write_emg_mat_v73(pdir / f"{stem}_emg.mat", seed + 1)
                write_mvnx(pdir / f"{stem}_xsens.mvnx", seed + 2)
        print(f"Generated {pid}")
    baseline_dir = out_dir / "baseline"
    baseline_dir.mkdir(exist_ok=True)
    write_baseline_csv(baseline_dir / "normative_baseline.csv")
    write_labels_csv(baseline_dir / "labels.csv", participants)
    print(f"Baseline + labels written to {baseline_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    generate(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
