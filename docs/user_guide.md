# User Guide

Audience: researchers and clinicians using the desktop application.
No programming knowledge is required.

> The application provides biomechanical findings, baseline comparisons, and
> risk indicators as **decision-support information only**. It does not
> provide a medical diagnosis.

## 1. Starting the application

Double-click `BiomechAnalyzer.exe` (packaged build), or from a source
checkout run `python -m biomech_analyzer.main`.

## 2. Preparing a participant folder

Create one folder per participant, named with the **anonymous ID** (e.g.
`P001`). Place the exported files for each trial inside. The file names
should mention the task, the condition, and the data source, for example:

```
P001/
  SLVJ_baseline_force.csv     SLVJ_baseline_emg.mat     SLVJ_baseline_xsens.mvnx
  SLVJ_upright_force.csv      SLVJ_upright_emg.mat      SLVJ_upright_xsens.mvnx
  SLVJ_cognitive_force.csv    …
  SLDJ_baseline_force.csv     …                          (6 trials in total)
```

Recognized name fragments (case-insensitive, `_`/`-`/space all fine):

| What | Accepted fragments |
|---|---|
| Task | `SLVJ`, `vertical`, `vj` / `SLDJ`, `drop`, `dj` |
| Condition | `baseline`, `natural` / `upright`, `trunk` / `cognitive`, `dualtask`, `dt` |
| Source | `.csv` = force plate, `.mat` = sEMG, `.mvnx` = Xsens (keywords such as `force`, `emg`, `xsens` also help) |

Never put participant names or personal information in file or folder names.

## 3. The three-step workflow

### Step 1 — Folder Selection
Enter the anonymous ID (or leave empty to use the folder name), choose the
participant folder, optionally choose the normative baseline file provided
by the Biomedical Engineering team, then press **Validate Files**. The tree
shows each detected trial and any missing or unrecognized files.

### Step 2 — Analysis Dashboard
Press **Run Analysis**. The log shows progress per trial plus any warnings
(missing channels, non-normalized EMG, synchronization notes, …). The
analysis continues even when a trial is incomplete; it simply reports what
was skipped and why.

### Step 3 — Results and Report
Review the tabs: **Trial summary**, **Features** (with baseline z-scores),
**Risk indicators** (only triggered ones), and **Feature plots** (select a
trial row to preview its force curve). Tick *Save results to local SQLite
database* if you want the anonymized results stored, then press
**Generate PDF Report**. One English PDF per participant is written to
`output/reports/`.

## 4. Reading the report

* **Input validation summary** — which files were used per trial.
* **Event detection** — take-off, initial contact, peak force, stabilization.
* **Extracted features** — each with unit, source, and validation status.
  `PENDING_BME_VALIDATION` means the formula/threshold is a configurable
  placeholder still awaiting Biomedical Engineering confirmation.
* **Baseline comparison** — your participant vs. the normative mean ± SD
  with a z-score and a plain-language interpretation.
* **Risk indicators** — which rule triggered, on which feature, and why.
* **Warnings and limitations** — read this section before interpreting
  anything else.

## 5. Advanced / Research screen

For the project team only. Adjust analysis parameters (low-pass cutoff,
contact threshold, RMS window), select a trained model for report inference,
or run Research Mode: analyze a whole dataset folder, train a Random Forest
with leave-one-subject-out validation, and export the model. ML outputs are
exploratory and clearly labeled as such.

## 6. Command line (batch processing)

```
biomech-analyzer validate <folder>
biomech-analyzer analyze  <folder> --baseline baseline.csv --save-db
biomech-analyzer report   <folder> --baseline baseline.csv --out reports/
biomech-analyzer train    <dataset_folder> --labels labels.csv
```

## 7. Troubleshooting

| Message | Meaning / fix |
|---|---|
| "No data files (.csv, .mat, .mvnx) were found" | Wrong folder selected, or exports not copied in yet. |
| "Could not assign '…' to a trial" | The file name lacks a task/condition keyword — rename it (see §2). |
| "No vertical force (Fz) column was found" | The CSV uses an unexpected column name; add it under `force_plate.column_aliases.fz` in `config/default_config.yaml`. |
| "No flight phase found in Fz" | The recording may not contain a jump, or the contact threshold needs adjusting (Advanced screen). |
| "MVIC values unavailable" | EMG amplitudes are reported non-normalized; provide MVIC data in the MAT export for normalized values. |
