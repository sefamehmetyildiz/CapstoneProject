# Test Report

Date: 2026-08-26 (updated after real-data validation) · Python 3.10.12 ·
Windows 11 · biomech-analyzer v0.1.0

## Summary

| Gate | Result |
|---|---|
| `pytest` | **96 passed, 0 failed** |
| `coverage report` | **90 %** over `src/biomech_analyzer` (GUI + entry points excluded by config) |
| `ruff check .` | **All checks passed** (rules: E, F, W, I, UP, B) |
| `mypy src` | **No issues in 46 source files** |
| CLI end-to-end (`report`, `train`) | Manually executed against mock data — PDF and model produced |
| PyInstaller build | `scripts/build_exe.py` → `dist/BiomechAnalyzer/` |

## Test inventory (78 tests)

| Module | Focus | Notable edge cases |
|---|---|---|
| test_trial_matcher (6) | filename classification | short-token false positives, synonyms, extension-vs-keyword precedence, unclassifiable names |
| test_folder_scanner (5) | folder validation | missing folder, empty folder, incomplete/duplicate files, imperfect participant P003 |
| test_force_plate_parser (6) | CSV robustness | metadata header rows, `;` delimiter, negative-down Fz convention, missing Fz column, missing time column, empty file, NaN interpolation |
| test_emg_mat_parser (5) | MAT v5 + v7.3 | version sniffing, missing signal variable, missing MVIC (warning path), non-MAT bytes |
| test_xsens_mvnx_parser (5) | MVNX XML | with/without namespace, calibration-frame skipping, broken XML, missing joints |
| test_baseline_loader (5) | baseline CSV | scoped lookup precedence, missing columns, non-numeric rows |
| test_synchronization (5) | sync strategies | timestamp accept, event fallback recovers a 2 s clock skew (±0.3 s), forced-timestamp rejection, force-plate-only trial |
| test_event_detection (4) | Fz events | full jump profile, no flight phase, recording starting mid-air, jump-height formula |
| test_feature_extraction (7) | end-to-end features | all 18 features on mock data, z-score math, graceful degradation without EMG |
| test_risk_scoring (5) | rule engine | absolute + z-score thresholds, negative z thresholds, missing feature, missing baseline |
| test_ml (6) | Research Mode | LOSO round-trip, exploratory warnings, label errors, corrupt model file |
| test_pdf_report (3) | reporting | with/without plots, imperfect participant |
| test_storage (2) | SQLite | save/query round-trip, append across sessions, schema anonymity |
| test_cli (5) | CLI | validate/analyze/report/train exit codes and outputs |
| test_gui_smoke (3) | PySide6 (offscreen) | window construction, validation flow wiring, results refresh |
| test_math_utils (6) | filters/RMS | invalid cutoffs, Nyquist clamping, short-signal RMS |

## Defects found by the tests during development

1. `moving_rms` returned the **kernel's** length for signals shorter than the
   RMS window (`np.convolve(mode="same")` sizes to the longer input) — fixed
   by clamping the window to the signal length.
2. `np.trapz` deprecation (NumPy ≥ 2) — migrated to `np.trapezoid`.
3. ReportLab `Image(width=…, height=None)` distorts aspect ratio — replaced
   with proportional scaling via `ImageReader`.

## Real-data validation sweep (SubjectsData, 16 subjects)

The full pipeline was executed against every real participant folder:

| Subject | Result |
|---|---|
| S01–S08 | 6/6 trials analyzed; initial contact, body weight, and 74–96 features per subject |
| S09 | 3/6 (SLVJ ok; SLDJ force exports contain only Sync/Aux channels) |
| S10, S11, S12, S15 | 0 trials (all force exports contain only Sync/Aux — re-export required; reported with an actionable error) |
| S13 | 5/5 available force trials analyzed (EMG/Xsens not yet converted) |
| S14, S16 | 1 trial each (data mostly unconverted .hpf/.mvn) |

Real-data defects found and fixed during this sweep: wrong sign-flip on
mostly-empty-plate recordings (median rule → extreme-value rule), flight
detection picking the empty-plate interval on SLDJ (bounded-run candidates
with plausibility limits), unloaded-plate offset breaking contact detection
(auto-zero), Delsys EMG CSVs being parsed as force plate files
(content-aware modality resolution + dedicated parser), 2-D Delsys `Time`
matrices, `COPy` column not matching, and `correct`/`corect` condition
naming.

## Known gaps

* GUI covered by smoke tests only (construction + state wiring); no
  simulated click-through. Manual GUI walkthrough recommended before the
  demo.
* All signal-level assertions are calibrated to the synthetic mock
  generator; they must be revisited when real pilot exports arrive (see
  docs/developer_guide.md → Known limitations).
* Research-Mode LOSO accuracy on the 3-participant mock set is 0 % — the
  expected outcome for arbitrary labels on synthetic data; the pipeline
  correctly emits its "exploratory only" warning.
