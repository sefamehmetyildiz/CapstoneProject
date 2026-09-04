"""Analysis pipeline orchestrator.

A single execution path shared by the GUI, the CLI, and the tests:
scan -> parse -> preprocess -> synchronize -> detect events -> extract
features -> baseline comparison -> risk rules. Per-trial failures degrade
gracefully: the failing trial is skipped with a recorded warning instead of
aborting the whole participant.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from biomech_analyzer.core.config import Config, load_risk_rules
from biomech_analyzer.core.constants import Modality
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.core.models import (
    FolderValidationReport,
    ParticipantResult,
    TrialData,
    TrialPackage,
    TrialResult,
)
from biomech_analyzer.diagnostics.baseline_comparison import compare_with_baseline
from biomech_analyzer.diagnostics.overall_risk import (
    load_overall_config,
    participant_risk_level,
    trial_risk_level,
)
from biomech_analyzer.diagnostics.profile_comparison import (
    ReferenceProfiles,
    compare_with_profiles,
    load_reference_profiles,
)
from biomech_analyzer.diagnostics.risk_scoring import evaluate_risk_rules
from biomech_analyzer.io.baseline_loader import BaselineDataset, load_baseline
from biomech_analyzer.io.emg_mat_parser import parse_emg_mat
from biomech_analyzer.io.folder_scanner import scan_participant_folder
from biomech_analyzer.io.force_plate_csv_parser import parse_force_plate_csv
from biomech_analyzer.io.xsens_mvnx_parser import parse_xsens_mvnx
from biomech_analyzer.processing.event_detection import detect_events
from biomech_analyzer.processing.feature_extraction import extract_features
from biomech_analyzer.processing.preprocessing import (
    EmgEnvelopes,
    preprocess_emg,
    preprocess_force_plate,
    preprocess_xsens,
)
from biomech_analyzer.processing.synchronization import synchronize_trial

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


def _noop(_msg: str) -> None:
    return None


def _load_participants_meta() -> dict:
    """Load participant anthropometrics from config/participants.yaml."""
    import yaml

    from biomech_analyzer.core.config import _config_root

    path = _config_root() / "config" / "participants.yaml"
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return dict(data.get("participants") or {})
    except Exception as exc:
        log.warning("participants.yaml could not be read: %s", exc)
        return {}


class AnalysisPipeline:
    """Runs the full offline analysis for one participant folder."""

    def __init__(
        self,
        config: Config,
        baseline: BaselineDataset | None = None,
        baseline_path: Path | None = None,
        risk_rules: list | None = None,
        reference_profiles: ReferenceProfiles | None = None,
    ) -> None:
        self.config = config
        self.baseline = baseline
        if self.baseline is None and baseline_path is not None:
            self.baseline = load_baseline(baseline_path)
        self.risk_rules = risk_rules if risk_rules is not None else load_risk_rules()
        self.overall_cfg = load_overall_config()
        self.profiles: ReferenceProfiles | None = reference_profiles
        if self.profiles is None:
            try:
                self.profiles = load_reference_profiles()
            except Exception as exc:  # missing file must not block analysis
                log.warning("Reference profiles unavailable: %s", exc)
        self.participants_meta = _load_participants_meta()
        self._current_participant_id: str = ""

    # ------------------------------------------------------------------ API

    def validate(self, folder: Path, participant_id: str | None = None) -> FolderValidationReport:
        return scan_participant_folder(folder, participant_id)

    def analyze(
        self,
        folder: Path,
        participant_id: str | None = None,
        progress: ProgressCallback = _noop,
    ) -> ParticipantResult:
        """Validate and analyze every analyzable trial in ``folder``."""
        progress("Validating participant folder…")
        validation = self.validate(folder, participant_id)
        result = ParticipantResult(
            participant_id=validation.participant_id,
            folder=Path(folder),
            validation=validation,
            analysis_timestamp=datetime.now().isoformat(timespec="seconds"),
        )
        if validation.errors:
            result.warnings.extend(validation.errors)
            return result

        self._current_participant_id = validation.participant_id
        for package in sorted(validation.trials, key=lambda p: p.trial_id):
            if Modality.FORCE_PLATE not in package.files:
                result.warnings.append(
                    f"Trial {package.trial_id} skipped (no force plate file)."
                )
                continue
            progress(f"Analyzing trial {package.trial_id}…")
            try:
                trial_result = self._analyze_trial(package)
                result.trials.append(trial_result)
            except BiomechError as exc:
                msg = f"Trial {package.trial_id} failed: {exc.user_message}"
                log.warning(msg)
                result.warnings.append(msg)
            except Exception as exc:  # unexpected: recorded, not swallowed silently
                msg = f"Trial {package.trial_id} failed unexpectedly: {exc!r}"
                log.exception(msg)
                result.warnings.append(msg)

        if not result.trials:
            result.warnings.append("No trial could be analyzed.")
        result.overall_risk = participant_risk_level(
            [t.overall_risk for t in result.trials]
        )
        progress("Analysis complete.")
        return result

    # ------------------------------------------------------------ internals

    def _analyze_trial(self, package: TrialPackage) -> TrialResult:
        trial = TrialData(package=package)

        fp_file = package.files[Modality.FORCE_PLATE]
        trial.force_plate = preprocess_force_plate(
            parse_force_plate_csv(fp_file.path, self.config), self.config
        )

        emg_env: EmgEnvelopes | None = None
        if Modality.EMG in package.files:
            emg_path = package.files[Modality.EMG].path
            try:
                if emg_path.suffix.lower() == ".csv":
                    from biomech_analyzer.io.emg_csv_parser import parse_emg_csv

                    trial.emg = parse_emg_csv(emg_path, self.config)
                else:
                    trial.emg = parse_emg_mat(emg_path, self.config)
                emg_env = preprocess_emg(trial.emg, self.config)
            except BiomechError as exc:
                trial.warnings.append(f"EMG unavailable: {exc.user_message}")
        else:
            trial.warnings.append("EMG file missing; muscle features unavailable.")

        if Modality.XSENS in package.files:
            try:
                trial.xsens = preprocess_xsens(
                    parse_xsens_mvnx(package.files[Modality.XSENS].path, self.config),
                    self.config,
                )
            except BiomechError as exc:
                trial.warnings.append(f"Xsens unavailable: {exc.user_message}")
        else:
            trial.warnings.append("Xsens file missing; kinematic features unavailable.")

        trial.sync = synchronize_trial(trial, emg_env, self.config)
        meta = self.participants_meta.get(self._current_participant_id) or {}
        known_bw = None
        if isinstance(meta, dict) and meta.get("mass_kg"):
            known_bw = float(meta["mass_kg"]) * 9.81
        events = detect_events(trial.force_plate, self.config, known_body_weight_n=known_bw)
        features = extract_features(trial, emg_env, events, self.config)

        # Collect stream-level warnings into the feature set for reporting.
        for source in (trial.force_plate, trial.emg, trial.xsens):
            if source is not None:
                features.warnings.extend(source.warnings)
        features.warnings.extend(trial.warnings)
        features.warnings.extend(events.warnings)
        if emg_env is not None:
            features.warnings.extend(emg_env.warnings)

        comparisons = (
            compare_with_baseline(features, self.baseline) if self.baseline else []
        )
        indicators = evaluate_risk_rules(features, comparisons, self.risk_rules)
        profile_comps = (
            compare_with_profiles(features, self.profiles) if self.profiles else []
        )

        return TrialResult(
            trial_id=package.trial_id,
            task=package.task,
            condition=package.condition,
            features=features,
            baseline_comparisons=comparisons,
            risk_indicators=indicators,
            profile_comparisons=profile_comps,
            overall_risk=trial_risk_level(indicators, self.overall_cfg),
            sync=trial.sync,
            warnings=list(features.warnings),
            data=trial,
        )
