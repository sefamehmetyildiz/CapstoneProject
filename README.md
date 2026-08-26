# Biomech Analyzer

Software Engineering component of the capstone project **"Multimodal
Biomechanical Data Acquisition and Automated Analysis of Single-Leg Jump
Performance"** (Bahçeşehir University, Biomedical + Software Engineering).

An **offline Windows desktop application** (PySide6) with a **command-line
interface** that turns participant folders of exported sensor files —
force plate CSV, sEMG/Delsys MAT, Xsens MVNX — into synchronized signals,
biomechanical features, normative baseline comparisons, rule-based risk
indicators, exploratory ML outputs, and a standardized English **PDF report**
per anonymous participant ID.

> **Disclaimer.** All outputs are biomechanical findings and decision-support
> information only. The software does **not** provide a medical diagnosis and
> does not replace the judgment of qualified clinicians or researchers.

**Türkçe kullanım kılavuzu:** [KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md) —
program `BiomechAnalyzer-Baslat.bat` ile açılır; tüm denekler
`scripts\analyze_all_subjects.ps1` ile tek komutla analiz edilir.

## Quick start

```powershell
# 1. Create the environment (Python 3.10+)
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2. Generate the synthetic mock dataset (no real data ships with the repo)
.\.venv\Scripts\python scripts\generate_mock_data.py

# 3. Run the CLI against a mock participant
.\.venv\Scripts\python -m biomech_analyzer.cli validate data\mock\P001
.\.venv\Scripts\python -m biomech_analyzer.cli report data\mock\P001 --baseline data\mock\baseline\normative_baseline.csv

# 4. Or start the desktop GUI
.\.venv\Scripts\python -m biomech_analyzer.main
```

(When running from a source checkout, either `pip install -e .` or prefix
commands with `$env:PYTHONPATH="src"` — the test suite and the commands
above work out of the box after an editable install.)

## Main user workflow (GUI)

```
1. Select Participant Folder  →  2. Validate Files  →  3. Run Analysis
                              →  4. Review Results   →  5. Generate PDF Report
```

Advanced settings (filter cutoffs, Fz contact threshold, EMG RMS window,
baseline/model paths) and the exploratory **Research Mode** (Random Forest
with leave-one-subject-out validation) live on a separate screen, away from
the standard clinical workflow.

## CLI commands

```text
biomech-analyzer validate <participant_folder>
biomech-analyzer analyze  <participant_folder> [--baseline FILE] [--save-db]
biomech-analyzer report   <participant_folder> [--baseline FILE] [--out DIR] [--model FILE]
biomech-analyzer train    <dataset_folder> --labels FILE [--model-out FILE]
```

## Repository layout

```
config/            YAML configuration (analysis parameters, risk thresholds, baseline schema)
data/mock/         generated synthetic test data (never real participants)
docs/              inspection report, architecture, user & developer guides, test report
scripts/           mock-data generator, PyInstaller build script
src/biomech_analyzer/
  core/            config, models, exceptions, logging, pipeline orchestrator
  io/              folder scanner, trial matcher, CSV/MAT/MVNX/baseline parsers
  processing/      synchronization, preprocessing, event detection, feature extraction
  diagnostics/     baseline comparison, rule-based risk scoring
  ml/              Research Mode (dataset builder, LOSO evaluation, training, inference)
  reporting/       plots and PDF report generation
  storage/         optional SQLite persistence (anonymized)
  app/             PySide6 GUI (4 screens)
tests/             pytest suite (78 tests)
```

## Quality tooling

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m coverage run -m pytest; .\.venv\Scripts\python -m coverage report
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src
```

## Packaging

```powershell
.\.venv\Scripts\python scripts\build_exe.py
# → dist/BiomechAnalyzer/BiomechAnalyzer.exe
```

## Data ethics

Only anonymous participant IDs are processed; the SQLite schema and PDF
reports contain no personally identifying fields. Everything runs offline.
All clinically sensitive formulas/thresholds are configurable and marked
`PENDING_BME_VALIDATION` until confirmed by the Biomedical Engineering team.
