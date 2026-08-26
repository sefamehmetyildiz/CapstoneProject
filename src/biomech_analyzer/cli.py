"""Command-line interface for batch processing and developer testing.

Commands:
    biomech-analyzer validate <participant_folder>
    biomech-analyzer analyze  <participant_folder> [--baseline FILE] [--save-db]
    biomech-analyzer report   <participant_folder> [--baseline FILE] [--out DIR]
    biomech-analyzer train    <dataset_folder> --labels FILE [--model-out FILE]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from biomech_analyzer import DISCLAIMER, __version__
from biomech_analyzer.core.config import Config, load_config
from biomech_analyzer.core.exceptions import BiomechError
from biomech_analyzer.core.logging_config import setup_logging
from biomech_analyzer.core.pipeline import AnalysisPipeline

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biomech-analyzer",
        description="Offline biomechanical analysis platform (decision-support only).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument(
        "--config", type=Path, default=None, help="YAML file overriding the default config"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate a participant folder")
    p_val.add_argument("folder", type=Path)
    p_val.add_argument("--participant-id", default=None)

    p_an = sub.add_parser("analyze", help="run the full analysis")
    p_an.add_argument("folder", type=Path)
    p_an.add_argument("--participant-id", default=None)
    p_an.add_argument("--baseline", type=Path, default=None, help="normative baseline CSV/XLSX")
    p_an.add_argument("--save-db", action="store_true", help="store results in SQLite")

    p_rep = sub.add_parser("report", help="analyze and generate the PDF report")
    p_rep.add_argument("folder", type=Path)
    p_rep.add_argument("--participant-id", default=None)
    p_rep.add_argument("--baseline", type=Path, default=None)
    p_rep.add_argument("--out", type=Path, default=None, help="report output directory")
    p_rep.add_argument("--model", type=Path, default=None, help="trained ML model for inference")
    p_rep.add_argument("--no-plots", action="store_true")
    p_rep.add_argument("--save-db", action="store_true")

    p_tr = sub.add_parser("train", help="Research Mode: train and evaluate a model")
    p_tr.add_argument("dataset_folder", type=Path, help="folder of participant subfolders")
    p_tr.add_argument("--labels", type=Path, required=True, help="participant_id,label CSV")
    p_tr.add_argument("--baseline", type=Path, default=None)
    p_tr.add_argument("--model-out", type=Path, default=None, help="export path (.joblib)")
    return parser


def _print(*lines: str) -> None:
    for line in lines:
        sys.stdout.write(line + "\n")


def _cmd_validate(args: argparse.Namespace, config: Config) -> int:
    pipeline = AnalysisPipeline(config)
    report = pipeline.validate(args.folder, args.participant_id)
    _print(*report.summary_lines())
    return 1 if report.errors else 0


def _analyze(args: argparse.Namespace, config: Config):
    pipeline = AnalysisPipeline(config, baseline_path=args.baseline)
    if args.baseline is None:
        _print("Note: no baseline file given; baseline comparison skipped.")
    return pipeline.analyze(args.folder, args.participant_id, progress=lambda m: _print(m))


def _print_analysis_summary(result) -> None:
    _print("", f"=== Analysis summary for {result.participant_id} ===")
    for trial in result.trials:
        triggered = [r.name for r in trial.risk_indicators if r.triggered]
        _print(
            f"  {trial.trial_id}: {len(trial.features.features)} features, "
            f"risk indicators: {', '.join(triggered) if triggered else 'none'}"
        )
    for w in result.warnings:
        _print(f"  WARNING: {w}")
    _print("", DISCLAIMER)


def _maybe_save_db(args: argparse.Namespace, config: Config, result) -> None:
    if getattr(args, "save_db", False):
        from biomech_analyzer.storage.sqlite_repository import SqliteRepository

        db_path = Path(config.get("storage.sqlite_path", "output/results.sqlite3"))
        with SqliteRepository(db_path) as repo:
            analysis_id = repo.save_participant_result(result)
        _print(f"Results stored in {db_path} (analysis id {analysis_id}).")


def _cmd_analyze(args: argparse.Namespace, config: Config) -> int:
    result = _analyze(args, config)
    _print_analysis_summary(result)
    _maybe_save_db(args, config, result)
    return 0 if result.trials else 1


def _cmd_report(args: argparse.Namespace, config: Config) -> int:
    from biomech_analyzer.reporting.pdf_report import generate_pdf_report

    result = _analyze(args, config)
    if not result.trials:
        _print("No analyzable trials; report not generated.")
        _print_analysis_summary(result)
        return 1
    if args.model is not None:
        from biomech_analyzer.ml.inference import predict_participant

        result.ml_output = predict_participant(result, args.model)
    out_dir = args.out or Path(config.get("report.output_dir", "output/reports"))
    report_path = generate_pdf_report(
        result, out_dir, include_plots=not args.no_plots
    )
    result.report_path = report_path
    _print_analysis_summary(result)
    _print(f"PDF report written to {report_path}")
    _maybe_save_db(args, config, result)
    return 0


def _cmd_train(args: argparse.Namespace, config: Config) -> int:
    from biomech_analyzer.ml.dataset_builder import (
        build_feature_table,
        load_labels,
        split_xy,
    )
    from biomech_analyzer.ml.train import export_model, train_and_evaluate

    dataset_folder = Path(args.dataset_folder)
    participant_dirs = sorted(
        p for p in dataset_folder.iterdir() if p.is_dir() and p.name.lower() != "baseline"
    )
    if not participant_dirs:
        _print(f"No participant subfolders found in {dataset_folder}.")
        return 1

    pipeline = AnalysisPipeline(config, baseline_path=args.baseline)
    results = []
    for pdir in participant_dirs:
        _print(f"Analyzing {pdir.name}…")
        results.append(pipeline.analyze(pdir))

    labels = load_labels(args.labels)
    table = build_feature_table(results, labels)
    x, y, groups = split_xy(table)
    output = train_and_evaluate(x, y, groups, config)
    _print(*output.evaluation.summary_lines())
    _print("Top feature importances:")
    for name, imp in list(output.feature_importances.items())[:10]:
        _print(f"  {name}: {imp:.3f}")

    model_out = args.model_out or (
        Path(config.get("ml.model_dir", "output/models")) / "random_forest.joblib"
    )
    export_model(output, model_out)
    _print(f"Model exported to {model_out}")
    _print(
        "Reminder: the ML module is exploratory/supportive; rule-based scoring "
        "and baseline comparison remain the primary outputs."
    )
    return 0


_COMMANDS = {
    "validate": _cmd_validate,
    "analyze": _cmd_analyze,
    "report": _cmd_report,
    "train": _cmd_train,
}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.WARNING)
    try:
        config = load_config(args.config)
        return _COMMANDS[args.command](args, config)
    except BiomechError as exc:
        _print(f"ERROR: {exc.user_message}")
        return 2
    except KeyboardInterrupt:
        _print("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
