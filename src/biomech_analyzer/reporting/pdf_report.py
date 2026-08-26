"""Standardized English PDF report generation (one per participant ID).

Built with ReportLab (pure Python — no native GTK/Pango dependencies,
which keeps PyInstaller packaging on Windows simple). The report presents
decision-support findings only and carries an explicit disclaimer.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from biomech_analyzer import DISCLAIMER, __version__
from biomech_analyzer.core.constants import VALIDATION_PENDING
from biomech_analyzer.core.exceptions import ReportError
from biomech_analyzer.core.models import ParticipantResult, TrialResult
from biomech_analyzer.reporting import plots
from biomech_analyzer.utils.file_utils import ensure_dir

log = logging.getLogger(__name__)

_TITLE = (
    "Multimodal Biomechanical Data Acquisition and Automated Analysis of "
    "Single-Leg Jump Performance"
)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=14, leading=18),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=12, spaceBefore=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=10.5, spaceBefore=8),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=8.5, leading=11),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=7.5, leading=9.5,
                                textColor=colors.HexColor("#444444")),
        "warn": ParagraphStyle("warn", parent=base["BodyText"], fontSize=8,
                               textColor=colors.HexColor("#8a5a00")),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["BodyText"], fontSize=8.5, leading=11,
            borderColor=colors.HexColor("#8a5a00"), borderWidth=1, borderPadding=6,
            backColor=colors.HexColor("#fff6e5"),
        ),
    }


def _table(data: list[list], col_widths: list[float] | None = None) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b0b0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f7f9fc")]),
            ]
        )
    )
    return t


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _scaled_image(path: Path, width: float) -> Image:
    """ReportLab Image scaled to ``width`` with preserved aspect ratio."""
    from reportlab.lib.utils import ImageReader

    iw, ih = ImageReader(str(path)).getSize()
    return Image(str(path), width=width, height=width * ih / iw)


def _trial_story(trial: TrialResult, styles: dict, plot_dir: Path, include_plots: bool) -> list:
    story: list = [Paragraph(f"Trial {trial.trial_id}", styles["h1"])]

    ev = trial.features.events
    if ev is not None:
        story.append(Paragraph("Event detection", styles["h2"]))
        story.append(
            _table(
                [
                    ["Event", "Time (s)"],
                    ["Take-off", _fmt(ev.takeoff_s)],
                    ["Initial contact", _fmt(ev.initial_contact_s)],
                    ["Peak landing force", _fmt(ev.peak_force_s)],
                    ["Stabilization", _fmt(ev.stabilization_s)],
                ],
                [5 * cm, 4 * cm],
            )
        )

    if trial.sync is not None:
        story.append(Paragraph("Synchronization", styles["h2"]))
        story.append(
            Paragraph(
                f"Strategy: <b>{trial.sync.strategy}</b>. " + " ".join(trial.sync.notes),
                styles["small"],
            )
        )

    if trial.features.features:
        story.append(Paragraph("Extracted biomechanical features", styles["h2"]))
        rows = [["Feature", "Value", "Unit", "Source", "Validation"]]
        for fv in trial.features.features.values():
            rows.append(
                [fv.name, f"{fv.value:.4g}", fv.unit, fv.modality.value, fv.validation_status]
            )
        story.append(_table(rows, [5.2 * cm, 2.2 * cm, 1.8 * cm, 2.6 * cm, 4.6 * cm]))

    if trial.baseline_comparisons:
        story.append(Paragraph("Normative baseline comparison", styles["h2"]))
        rows = [["Feature", "Value", "Baseline mean", "SD", "z-score", "Interpretation"]]
        for c in trial.baseline_comparisons:
            rows.append(
                [
                    c.feature,
                    f"{c.participant_value:.4g}",
                    f"{c.baseline_mean:.4g}",
                    f"{c.baseline_std:.4g}",
                    "-" if c.z_score is None else f"{c.z_score:+.2f}",
                    c.interpretation,
                ]
            )
        story.append(_table(rows, [4.2 * cm, 1.9 * cm, 2.3 * cm, 1.5 * cm, 1.7 * cm, 4.8 * cm]))

    triggered = [r for r in trial.risk_indicators if r.triggered]
    story.append(Paragraph("Risk indicators (decision-support only)", styles["h2"]))
    if triggered:
        rows = [["Indicator", "Feature", "Observed", "Reference", "Level", "Validation"]]
        for r in triggered:
            rows.append(
                [r.name, r.feature, _fmt(r.observed_value), r.reference,
                 r.risk_level.value, r.validation_status]
            )
        story.append(_table(rows, [3.6 * cm, 3.0 * cm, 1.7 * cm, 3.6 * cm, 1.7 * cm, 2.8 * cm]))
        for r in triggered:
            story.append(Paragraph(f"<b>{r.name}:</b> {r.explanation}", styles["small"]))
    else:
        story.append(
            Paragraph("No configured risk indicator was triggered for this trial.",
                      styles["body"])
        )

    if include_plots and trial.data is not None:
        for maker in (plots.plot_fz_with_events, plots.plot_knee_flexion):
            img_path = maker(trial.data, trial, plot_dir)
            if img_path is not None:
                story.append(Spacer(1, 6))
                story.append(_scaled_image(img_path, 16.5 * cm))
        z_path = plots.plot_zscores(trial, plot_dir)
        if z_path is not None:
            story.append(Spacer(1, 6))
            story.append(_scaled_image(z_path, 16.5 * cm))

    if trial.warnings:
        story.append(Paragraph("Trial warnings", styles["h2"]))
        for w in dict.fromkeys(trial.warnings):  # de-duplicated, order kept
            story.append(Paragraph(f"• {w}", styles["warn"]))
    story.append(PageBreak())
    return story


def generate_pdf_report(
    result: ParticipantResult,
    output_dir: Path,
    include_plots: bool = True,
) -> Path:
    """Write the participant PDF report and return its path."""
    styles = _styles()
    ensure_dir(output_dir)
    out_path = Path(output_dir) / f"{result.participant_id}_biomech_report.pdf"

    story: list = [
        Paragraph(_TITLE, styles["title"]),
        Spacer(1, 4),
        Paragraph(
            f"Biomechanical Risk Report — Participant <b>{result.participant_id}</b>",
            styles["h1"],
        ),
        Paragraph(f"Analysis timestamp: {result.analysis_timestamp}", styles["body"]),
        Paragraph(f"Input folder: {result.folder}", styles["body"]),
        Paragraph(f"Software: biomech-analyzer v{__version__}", styles["body"]),
        Spacer(1, 6),
        Paragraph(f"<b>Disclaimer.</b> {DISCLAIMER}", styles["disclaimer"]),
        Spacer(1, 6),
        Paragraph("Input validation summary", styles["h1"]),
    ]

    rows = [["Trial", "Force plate", "sEMG", "Xsens", "Status"]]
    from biomech_analyzer.core.constants import Modality

    for pkg in sorted(result.validation.trials, key=lambda p: p.trial_id):
        def _cell(m: Modality, _pkg=pkg) -> str:
            f = _pkg.files.get(m)
            return f.path.name if f else "MISSING"

        rows.append(
            [
                pkg.trial_id,
                _cell(Modality.FORCE_PLATE),
                _cell(Modality.EMG),
                _cell(Modality.XSENS),
                "complete" if pkg.is_complete else "incomplete",
            ]
        )
    story.append(_table(rows, [3.0 * cm, 4.3 * cm, 4.3 * cm, 4.3 * cm, 2.0 * cm]))

    if result.validation.unmatched_files:
        story.append(Paragraph("Unassigned files", styles["h2"]))
        for p in result.validation.unmatched_files:
            story.append(Paragraph(f"• {p.name}", styles["warn"]))

    pending = any(
        fv.validation_status == VALIDATION_PENDING
        for t in result.trials
        for fv in t.features.features.values()
    )
    if pending:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                "Note: formulas and thresholds marked PENDING_BME_VALIDATION are "
                "configurable placeholders awaiting confirmation by the "
                "Biomedical Engineering team.",
                styles["warn"],
            )
        )
    story.append(PageBreak())

    with tempfile.TemporaryDirectory(prefix="biomech_plots_") as tmp:
        plot_dir = Path(tmp)
        for trial in result.trials:
            story.extend(_trial_story(trial, styles, plot_dir, include_plots))

        if result.ml_output:
            story.append(Paragraph("Research Mode / machine learning output", styles["h1"]))
            ml = result.ml_output
            story.append(
                Paragraph(
                    f"Majority prediction: <b>{ml.get('majority_prediction', '-')}</b> "
                    f"(model: {ml.get('model_path', '-')})",
                    styles["body"],
                )
            )
            rows = [["Trial", "Prediction", "Probabilities"]]
            for t in ml.get("trials", []):
                prob = ", ".join(f"{k}: {v}" for k, v in t.get("probabilities", {}).items())
                rows.append([t.get("trial_id", "-"), t.get("prediction", "-"), prob])
            story.append(_table(rows, [3.5 * cm, 3.5 * cm, 9 * cm]))
            for w in ml.get("warnings", []):
                story.append(Paragraph(f"• {w}", styles["warn"]))

        story.append(Paragraph("Warnings and limitations", styles["h1"]))
        all_warnings = list(
            dict.fromkeys(result.warnings + result.validation.warnings)
        )
        if all_warnings:
            for w in all_warnings:
                story.append(Paragraph(f"• {w}", styles["warn"]))
        else:
            story.append(Paragraph("No participant-level warnings.", styles["body"]))
        story.append(Spacer(1, 8))
        story.append(Paragraph(DISCLAIMER, styles["disclaimer"]))

        try:
            doc = SimpleDocTemplate(
                str(out_path),
                pagesize=A4,
                leftMargin=1.6 * cm,
                rightMargin=1.6 * cm,
                topMargin=1.4 * cm,
                bottomMargin=1.4 * cm,
                title=f"Biomechanical report {result.participant_id}",
            )
            doc.build(story)
        except Exception as exc:
            raise ReportError(f"PDF generation failed: {exc}") from exc

    log.info("Report written: %s", out_path)
    return out_path
