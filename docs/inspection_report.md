# Inspection Report — Phase 0

Project: Multimodal Biomechanical Data Acquisition and Automated Analysis of
Single-Leg Jump Performance (Software Engineering component)

Date: 2026-08-26
Author: Software Engineering team (automated inspection)

---

## 1. Workspace inventory

The working directory `c:\Users\ysefa\Desktop\CapstoneProject` was inspected
recursively. Result:

| Item | Status |
|---|---|
| Capstone proposal report | **Available** (provided as `CapstoneReportTemplate.pdf` in the task context; not present on disk) |
| Checklist document | **Not found** |
| GUI wireframe file | **Not found** (wireframe is embedded as Figure 1 in the proposal) |
| Gantt chart / risk tables | Embedded in the proposal only |
| Mock data (Force Plate CSV) | **Not found** |
| Mock data (sEMG/Delsys MAT) | **Not found** |
| Mock data (Xsens MVNX) | **Not found** |
| Normative baseline dataset | **Not found** |
| ML labels | **Not found** |

**The workspace contained no files at all.** Every conclusion below about file
content is therefore derived from the proposal document and from public
knowledge of the instruments (Bertec force plate, Delsys Trigno, Xsens MVN),
not from real exported files.

## 2. What the proposal specifies

From the proposal (sections 1.2, 3.2–3.5, 5.2, 7.2):

- Input: participant-based folders; per participant, six trial packages
  (SLVJ/SLDJ × baseline / upright trunk / cognitive dual-task).
- Each trial package: 1 force plate **CSV**, 1 sEMG/Delsys **MAT**,
  1 Xsens **MVNX** (XML).
- Pipeline: folder validation → trial matching → parsing → synchronization
  (timestamp-based primary, force-plate Fz event fallback) → preprocessing →
  event detection (initial contact, take-off, peak landing force,
  stabilization) → feature extraction (peak vGRF, RFD, RSI, TTS, impulse,
  CoP; sEMG RMS/onset/pre-activation/MVIC-normalized; joint angles/ROM) →
  baseline comparison (z-scores) → rule-based risk indicators → optional ML
  (Random Forest, leave-one-subject-out CV) → PDF report → optional SQLite.
- Stack: Python, NumPy, Pandas, SciPy, h5py, lxml/ElementTree, scikit-learn,
  Matplotlib, PySide6 (explicitly not PyQt6), ReportLab/WeasyPrint, SQLite,
  PyInstaller, pytest.
- Outputs: one English PDF risk report per anonymous participant ID;
  decision-support only, no medical diagnosis.

## 3. Detected naming conventions

None could be detected (no mock data). The proposal's example implies names
like `SLVJ_baseline_force.csv`, `SLVJ_baseline_emg.mat`,
`SLVJ_baseline_xsens.mvnx` under a folder named by participant ID (`P001`).

**Decision:** implement a *flexible, token-based trial matcher* that
recognizes task (`SLVJ`/`SLDJ`, plus synonyms like `vertical`/`drop`),
condition (`baseline`/`natural`, `upright`, `cognitive`/`dualtask`/`dt`) and
modality (by extension and by keywords `force`/`fp`/`grf`, `emg`/`delsys`,
`xsens`/`mvnx`/`imu`) anywhere in the file name, case-insensitively, with
separators `_`, `-`, or space. Unmatched files are reported, never silently
dropped.

## 4. Missing information and how each gap is handled

| Missing item | Handling |
|---|---|
| Real export column names / units for Bertec CSV | Parser accepts configurable column aliases (`config/default_config.yaml`), auto-detects delimiter and header rows, tolerates unit rows. |
| MAT file version (v5 vs v7.3/HDF5) | Version sniffed from the 128-byte MAT header; `scipy.io.loadmat` for ≤v7.2, `h5py` for v7.3. Clear error if neither works. |
| MVNX schema version / namespaces | Namespace-agnostic XML parsing (local-name matching); optional fields tolerated. |
| Biomechanical formulas' final definitions | Implemented in a dedicated `FormulaRegistry`-style module (`processing/feature_extraction.py`) with every threshold/window sourced from config and flagged `requires_bme_validation: true`. |
| Risk thresholds | Placeholders in `config/risk_thresholds.yaml`, each carrying `validation_status: PENDING_BME_VALIDATION`; surfaced verbatim in reports. |
| Normative baseline dataset | Loader supports CSV/XLSX with a documented schema (`config/baseline_schema.yaml`); a synthetic example baseline ships with the mock data. |
| ML labels | Research Mode reads labels from a `labels.csv` (participant_id, label); a synthetic example is generated for the mock dataset. |
| Mock data itself | A deterministic generator (`scripts/generate_mock_data.py`) creates physically plausible synthetic force-plate CSV, Delsys-style MAT (both v5 and v7.3), and MVNX files for participants P001–P003. **All synthetic — for pipeline testing only, not biomechanically valid reference data.** |

## 5. Technical assumptions (documented per Development Rule 20)

1. **Python 3.10.12** is the only interpreter on this machine; the project
   targets Python **3.10+** instead of the suggested 3.11+ (no 3.11-only
   features are used).
2. Force plate sampling rate assumed ~1000 Hz, sEMG ~2000 Hz (Delsys Trigno
   typical), Xsens ~60 Hz — all configurable, never hard-coded in logic.
3. Fz is positive upward (vertical GRF ≥ 0 during stance); a landing is a
   rising crossing of a configurable Fz threshold (default 20 N), take-off a
   falling crossing. Thresholds require BME validation.
4. Body weight for normalization is estimated from a quiet-stance segment of
   Fz when available, otherwise taken from optional participant metadata;
   otherwise features are reported unnormalized with a warning.
5. When no cross-modal trigger exists, streams are aligned by event
   (initial-contact) anchoring, and this assumption is written into report
   metadata as required by the proposal.
6. ML is exploratory only (n≈30 subjects); rule-based scoring remains the
   primary output. Leave-one-subject-out grouping is enforced.
7. ReportLab chosen over WeasyPrint (pure-Python, no GTK/Pango native
   dependencies on Windows — safer for PyInstaller packaging).

## 6. Recommended architecture

The layered pipeline from the proposal §3.2 is kept: `io` (scan/match/parse)
→ `processing` (sync/preprocess/events/features) → `diagnostics`
(baseline/risk) → `reporting` (plots/PDF) → `storage` (SQLite), with `app`
(PySide6 GUI) and `cli` as thin front-ends over a shared
`AnalysisPipeline` orchestrator in `core`. Structure follows §17 of the
project brief, with two justified additions:

- `scripts/generate_mock_data.py` — because no mock data was provided.
- `src/biomech_analyzer/core/pipeline.py` — a single orchestrator so the
  GUI, CLI, and tests execute the identical analysis path.

## 7. First implementation steps

1. Project skeleton, `pyproject.toml`, config files, logging (Phase 1).
2. Mock-data generator, so every later phase has data to test against.
3. Folder scanner + trial matcher with validation report (Phase 2).
4. Parsers with version/format sniffing (Phase 3).
5. Continue per roadmap phases 4–12.
