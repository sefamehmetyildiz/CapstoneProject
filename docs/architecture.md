# Architecture

## Overview

The system is a modular, layered pipeline (proposal §3.2). One orchestrator —
`core/pipeline.py::AnalysisPipeline` — executes the identical analysis path
for the GUI, the CLI, and the tests:

```
participant folder
      │
      ▼
┌──────────────┐   io/folder_scanner + io/trial_matcher
│ Input layer  │   scan files → classify (modality, task, condition) →
└──────┬───────┘   TrialPackages + FolderValidationReport
       ▼
┌──────────────┐   io/force_plate_csv_parser (CSV, delimiter/header sniffing)
│ Parser layer │   io/emg_mat_parser (MAT v5 via scipy.io, v7.3 via h5py)
└──────┬───────┘   io/xsens_mvnx_parser (namespace-agnostic XML)
       ▼
┌──────────────┐   processing/preprocessing  (Butterworth filters, RMS, MVIC)
│ Processing   │   processing/synchronization (timestamp primary, Fz-event fallback)
│ layer        │   processing/event_detection (flight phase → IC/take-off/peak/stab.)
└──────┬───────┘   processing/feature_extraction (formula registry)
       ▼
┌──────────────┐   diagnostics/baseline_comparison (z-scores, no risk)
│ Diagnostics  │   diagnostics/risk_scoring (config-driven rules)
└──────┬───────┘   ml/* (Research Mode, exploratory only)
       ▼
┌──────────────┐   reporting/plots + reporting/pdf_report (ReportLab)
│ Output layer │   storage/sqlite_repository (optional, anonymized)
└──────────────┘
```

## Key design decisions

1. **Single orchestrator.** GUI/CLI are thin front-ends over
   `AnalysisPipeline`; behavior cannot diverge between them.
2. **Graceful degradation.** A trial missing EMG or Xsens is still analyzed
   with the remaining modalities; a failing trial is skipped with a recorded
   warning instead of aborting the participant. Only "no force plate file
   anywhere" is a hard error, because Fz is the temporal anchor.
3. **Configuration-driven formulas.** Every filter cutoff, threshold, and
   window lives in `config/*.yaml`. Features and risk rules carry a
   `validation_status` (`PENDING_BME_VALIDATION` until the BME team signs
   off) that is surfaced in the GUI and the PDF.
4. **Flexible trial matching.** No official naming convention existed at
   development time, so classification is keyword-based (task, condition,
   modality tokens anywhere in the file name, case-insensitive). Unmatched
   files are listed, never silently dropped.
5. **Synchronization honesty.** When all streams share a consistent time
   base, timestamp sync is used with zero offsets. Otherwise the Fz landing
   peak anchors EMG (summed-envelope peak) and Xsens (peak knee flexion);
   every applied offset and its assumption is written into `SyncInfo.notes`
   and printed in the report.
6. **ML is exploratory.** Leave-one-subject-out grouping is enforced
   (`sklearn.LeaveOneGroupOut` on participant IDs) to prevent trial-level
   leakage; small-cohort and class-imbalance warnings are attached to every
   evaluation; rule-based scoring remains the primary output.
7. **ReportLab over WeasyPrint.** Pure-Python, no GTK/Pango native
   dependencies — significantly simpler PyInstaller packaging on Windows.
8. **Anonymity by schema.** The SQLite schema has no columns for personal
   data; reports and the database only ever see the anonymous participant ID.

## Data models

`core/models.py` defines the standardized dataclasses passed between layers:
`TrialPackage` → `ForcePlateData`/`EmgData`/`XsensData` → `SyncInfo` +
`EventSet` → `TrialFeatures` (of `FeatureValue`) → `BaselineComparison` +
`RiskIndicatorResult` → `TrialResult` → `ParticipantResult`.

## Threading (GUI)

Long-running work (analysis, Research-Mode training) runs in `QThread`
workers that communicate with the UI via signals; the UI thread never blocks.

## Error handling

`core/exceptions.py` defines a `BiomechError` hierarchy with `user_message`
(plain-language, with hints). CLI exit codes: 0 success, 1 empty result,
2 expected application error, 130 interrupt.
