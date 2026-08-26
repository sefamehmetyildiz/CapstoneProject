# Developer Guide

## Environment

* Python **3.10+** (the machine this was developed on has 3.10.12 via `py`).
* `py -3.10 -m venv .venv` then `pip install -r requirements.txt`
  (or `pip install -e .[dev]`).

## Everyday commands

```powershell
.\.venv\Scripts\python -m pytest                 # full suite
.\.venv\Scripts\python -m pytest -m "not slow"   # skip end-to-end training
.\.venv\Scripts\python -m coverage run -m pytest; .\.venv\Scripts\python -m coverage report
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src
.\.venv\Scripts\python scripts\generate_mock_data.py   # regenerate mock data
.\.venv\Scripts\python scripts\build_exe.py            # PyInstaller build
```

The test suite regenerates `data/mock/` automatically if it is missing
(`tests/conftest.py`).

## Code map

See `docs/architecture.md` for the layer diagram. Ground rules:

* **All formulas and thresholds** go through `config/*.yaml` and
  `processing/feature_extraction.py` (the formula registry). Never hard-code
  a clinical threshold elsewhere.
* **New feature**: add its computation in `feature_extraction.py` with a
  `_add(...)` call (name, unit, modality, description). It automatically
  flows into baseline comparison, risk rules, reports, storage, and ML.
* **New risk rule**: add an entry to `config/risk_thresholds.yaml` — no code
  change needed. Use `threshold` (absolute) or `zscore_threshold` (baseline
  relative).
* **New file format**: add a parser in `io/` returning one of the canonical
  models in `core/models.py`, and wire it in `core/pipeline.py`.
* Production modules log via `logging` (never `print`); user-facing errors
  derive from `BiomechError` and set a readable `user_message`.

## Testing conventions

* One test module per production module (`tests/test_<module>.py`).
* Mock data covers the happy path; malformed inputs are built inline with
  `tmp_path`. Participant `P003` in the mock set is intentionally broken
  (missing EMG file, unclassifiable file name) to exercise degradation.
* GUI tests run headless with `QT_QPA_PLATFORM=offscreen` and only smoke-test
  construction + state wiring (no user-event simulation).

## Extending the mock data

`scripts/generate_mock_data.py` is deterministic (seeded per
participant/trial). If the Biomedical Engineering team delivers real pilot
exports, place a participant folder under `data/` and run
`biomech-analyzer validate` first — the validation report tells you which
naming/alias adjustments the config needs.

## Real-data findings (SubjectsData, 2026-08-26)

The system was validated against the 16-subject real dataset. What the
sweep established (and the code now handles):

* **Force plate = 1000 Hz** — verified by matching jump-to-jump spacing in
  Fz samples against Xsens footContacts seconds (993–1007 Hz across
  subjects). Bertec CSVs carry no time column (`Seq` is a sample counter).
* **~5 jump repetitions per recording** — event detection selects one
  repetition (config `events.repetition_selection`) from plausible flight
  candidates (below-threshold runs bounded by contact, 0.08–1.0 s).
* **SLDJ recordings start with an empty plate** (participant on the box) —
  the longest below-threshold run is *not* flight; body weight comes from
  the most stable contact window when there is no initial quiet stance.
* **Delsys EMG arrives as MAT (v5, `Channels/Fs/Time/Data`, 2148.15 Hz) or
  as "Plot and Store" CSV** — `.csv` modality is resolved by filename +
  parent folder + content sniffing (`io/trial_matcher.py`), and
  `io/emg_csv_parser.py` reads the CSV variant.
* **Some plates were not zeroed** (empty plate ≈ 41 N) — auto-zero in
  preprocessing removes a stable unloaded-plate offset.
* **Broken exports exist**: several subjects' force CSVs contain only
  `Sync,Aux` columns; the parser raises a dedicated, actionable error
  ("re-export with force channels").
* **Folder names contain personal names** — `subject 4 sefa` → anonymous
  `S04` with a privacy warning.

## Known limitations

* Streams are started independently (EMG ~11 s vs force plate ~35 s per
  recording) with no hardware trigger; event-based alignment may match
  different repetitions across modalities. Cross-modal timing features
  (pre-activation, onset latency) are approximate and flagged.
* Repetition selection (`longest_flight`) and every threshold remain
  PENDING_BME_VALIDATION.
* Per-repetition aggregation (mean over the ~5 jumps) is not implemented;
  one repetition per recording is analyzed and reported.
* MAT v7.3 parsing supports plain datasets; deeply nested MATLAB structs
  inside HDF5 would need parser extension.
* Subjects whose force exports contain only Sync/Aux channels cannot be
  analyzed until re-exported from the Bertec software.
