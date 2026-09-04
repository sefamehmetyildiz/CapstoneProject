"""Standardized bilingual (EN/TR) PDF report generation — clinical layout.

Compact clinical template for expert readers: a repeating page header
band and numbered footer, a patient-information style summary box, and
matrix tables that show all trials side by side (rows = parameters,
columns = trials) instead of one section per trial, keeping the whole
report to a few pages. DejaVu Sans (bundled with matplotlib) is
registered so Turkish characters render correctly; risk levels colour
the report (high = red, moderate = orange, low = green).
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from biomech_analyzer import __version__
from biomech_analyzer.core.constants import (
    RISK_BG_COLORS,
    RISK_COLORS,
    RiskLevel,
)
from biomech_analyzer.core.exceptions import ReportError
from biomech_analyzer.core.models import ParticipantResult, ProfileComparison, TrialResult
from biomech_analyzer.diagnostics.profile_comparison import REGIONS, region_status
from biomech_analyzer.reporting import plots
from biomech_analyzer.reporting.i18n import risk_label, tr
from biomech_analyzer.utils.file_utils import ensure_dir

log = logging.getLogger(__name__)

_FONTS_REGISTERED = False

# Clinical palette — one navy accent used consistently everywhere.
NAVY = "#1a3b5d"
NAVY_LIGHT = "#eef2f7"
RULE = "#d5dde8"
MUTED = "#6b7280"

CONTENT_W = 17.8 * cm
PLOT_GRID_W = 8.6 * cm

# closer_to → risk level used for cell colouring in the profile matrix
_CLOSER_LEVEL = {
    "control": RiskLevel.LOW,
    "between": RiskLevel.MODERATE,
    "aclr": RiskLevel.HIGH,
}


def _register_fonts() -> None:
    """Register DejaVu Sans (bundled with matplotlib) for Turkish glyphs."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    ttf_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(ttf_dir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf_dir / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "DejaVu", normal="DejaVu", bold="DejaVu-Bold",
        italic="DejaVu", boldItalic="DejaVu-Bold",
    )
    _FONTS_REGISTERED = True


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="DejaVu", fontSize=8.5, leading=11)
    return {
        "title": ParagraphStyle(
            "title", parent=base, fontName="DejaVu-Bold", fontSize=12.5, leading=16,
            alignment=1, spaceAfter=8, textColor=colors.HexColor(NAVY),
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName="DejaVu-Bold", fontSize=9, leading=12,
            spaceBefore=10, spaceAfter=4, textColor=colors.HexColor(NAVY),
        ),
        "body": base,
        "footnote": ParagraphStyle(
            "footnote", parent=base, fontSize=7, leading=9,
            textColor=colors.HexColor(MUTED),
        ),
    }


_CELL_STYLE = ParagraphStyle(
    "cell", fontName="DejaVu", fontSize=7.5, leading=9.5
)
_HDR_STYLE = ParagraphStyle(
    "hdr", fontName="DejaVu-Bold", fontSize=7.5, leading=9.5,
    textColor=colors.white,
)


def _wrap(text: str) -> Paragraph:
    """Wrappable table cell (plain strings do not wrap in ReportLab tables)."""
    return Paragraph(text, _CELL_STYLE)


def _table(data: list[list], col_widths: list[float] | None = None) -> Table:
    """Uniform clinical table: navy header band, light horizontal rules."""
    header = [
        Paragraph(str(c), _HDR_STYLE) if isinstance(c, str) else c for c in data[0]
    ]
    t = Table([header, *data[1:]], colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#1f2937")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor(RULE)),
                ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.HexColor(NAVY)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f5f8fb")]),
            ]
        )
    )
    return t


def _info_box(result: ParticipantResult, lang: str) -> Table:
    """Patient-information style summary box (label/value grid)."""
    label = ParagraphStyle(
        "ib_l", fontName="DejaVu-Bold", fontSize=7.5, leading=9.5,
        textColor=colors.HexColor(NAVY),
    )
    value = ParagraphStyle("ib_v", fontName="DejaVu", fontSize=7.5, leading=9.5)
    rows = [
        [
            Paragraph(tr("report.participant", lang), label),
            Paragraph(str(result.participant_id), value),
            Paragraph(tr("report.timestamp", lang), label),
            Paragraph(str(result.analysis_timestamp), value),
        ],
        [
            Paragraph(tr("report.software", lang), label),
            Paragraph(f"biomech-analyzer v{__version__}", value),
            Paragraph(tr("report.folder", lang), label),
            Paragraph(str(result.folder), value),
        ],
    ]
    t = Table(rows, colWidths=[3.0 * cm, 5.9 * cm, 3.0 * cm, 5.9 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(NAVY_LIGHT)),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor(NAVY_LIGHT)),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(NAVY)),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _risk_banner(text: str, level: RiskLevel, width: float) -> Table:
    style = ParagraphStyle(
        "banner", fontName="DejaVu-Bold", fontSize=11, leading=14,
        textColor=colors.HexColor(RISK_COLORS[level]), alignment=1,
    )
    t = Table([[Paragraph(text, style)]], colWidths=[width])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(RISK_BG_COLORS[level])),
                ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(RISK_COLORS[level])),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _scaled_image(path: Path, width: float) -> Image:
    from reportlab.lib.utils import ImageReader

    iw, ih = ImageReader(str(path)).getSize()
    img = Image(str(path), width=width, height=width * ih / iw)
    img.hAlign = "CENTER"
    return img


def _risk_cell_style(rows: list[RiskLevel], header_offset: int = 1) -> list[tuple]:
    cmds: list[tuple] = []
    for i, level in enumerate(rows):
        r = i + header_offset
        cmds.append(("TEXTCOLOR", (-1, r), (-1, r), colors.HexColor(RISK_COLORS[level])))
        cmds.append(("BACKGROUND", (-1, r), (-1, r), colors.HexColor(RISK_BG_COLORS[level])))
        cmds.append(("FONTNAME", (-1, r), (-1, r), "DejaVu-Bold"))
    return cmds


def _page_decorator(
    result: ParticipantResult, lang: str
) -> Callable[[Canvas, Any], None]:
    """Repeating header band + numbered footer on every page."""

    def draw(canvas: Canvas, doc: Any) -> None:
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(colors.HexColor(NAVY))
        canvas.rect(0, h - 0.95 * cm, w, 0.95 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("DejaVu-Bold", 8)
        canvas.drawString(
            1.6 * cm, h - 0.63 * cm,
            f"{tr('report.subtitle', lang)} {result.participant_id}",
        )
        canvas.setFont("DejaVu", 7.5)
        canvas.drawRightString(
            w - 1.6 * cm, h - 0.63 * cm, str(result.analysis_timestamp)
        )
        canvas.setStrokeColor(colors.HexColor(RULE))
        canvas.setLineWidth(0.6)
        canvas.line(1.6 * cm, 1.15 * cm, w - 1.6 * cm, 1.15 * cm)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.setFont("DejaVu", 7)
        canvas.drawString(1.6 * cm, 0.75 * cm, f"biomech-analyzer v{__version__}")
        canvas.drawRightString(
            w - 1.6 * cm, 0.75 * cm, f"{tr('report.page', lang)} {doc.page}"
        )
        canvas.restoreState()

    return draw


def _tasks_in_order(result: ParticipantResult) -> list[str]:
    tasks: list[str] = []
    for trial in result.trials:
        if trial.task.value not in tasks:
            tasks.append(trial.task.value)
    return tasks


def _events_table(result: ParticipantResult, lang: str) -> Table:
    """All trials in one events table (rows = trials)."""
    rows: list[list] = [[
        tr("report.trial", lang),
        tr("report.initial_contact", lang),
        tr("report.takeoff", lang),
        tr("report.peak_force", lang),
        tr("report.stabilization", lang),
        "SSC",
    ]]
    for trial in result.trials:
        ev = trial.features.events
        ssc = trial.features.ssc_category
        rows.append([
            trial.trial_id,
            _fmt(ev.initial_contact_s) if ev else "-",
            _fmt(ev.takeoff_s) if ev else "-",
            _fmt(ev.peak_force_s) if ev else "-",
            _fmt(ev.stabilization_s) if ev else "-",
            tr(f"ssc.{ssc}", lang) if ssc else "-",
        ])
    return _table(rows, [4.2 * cm, 2.6 * cm, 2.4 * cm, 3.4 * cm, 2.8 * cm, 2.4 * cm])


def _feature_matrix(trials: list[TrialResult], lang: str) -> Table:
    """One table per task: rows = features, one value column per trial."""
    names: list[str] = []
    units: dict[str, str] = {}
    for trial in trials:
        for fv in trial.features.features.values():
            if fv.name not in names:
                names.append(fv.name)
                units[fv.name] = fv.unit
    header: list = [tr("report.feature", lang), tr("report.unit", lang)]
    header += [t.condition.value for t in trials]
    rows: list[list] = [header]
    for name in names:
        row: list = [_wrap(name), units[name]]
        for trial in trials:
            found = trial.features.features.get(name)
            row.append("-" if found is None else f"{found.value:.4g}")
        rows.append(row)
    trial_w = (CONTENT_W - 7.6 * cm) / max(len(trials), 1)
    widths = [5.8 * cm, 1.8 * cm] + [trial_w] * len(trials)
    return _table(rows, widths)


def _profile_matrix(trials: list[TrialResult], lang: str) -> Table | None:
    """Literature comparison, all trials side by side; cells coloured by
    the closer profile (green = control, orange = between, red = ACLR)."""
    by_feature: dict[str, dict[str, ProfileComparison]] = {}
    reference: dict[str, ProfileComparison] = {}
    for trial in trials:
        for pc in trial.profile_comparisons:
            by_feature.setdefault(pc.feature, {})[trial.trial_id] = pc
            reference.setdefault(pc.feature, pc)
    if not by_feature:
        return None
    header: list = [
        tr("report.feature", lang),
        f"{tr('report.control_short', lang)} (μ±σ)",
        f"{tr('report.aclr_short', lang)} (μ±σ)",
    ]
    header += [t.condition.value for t in trials]
    rows: list[list] = [header]
    cell_cmds: list[tuple] = []
    for r, (feature, per_trial) in enumerate(by_feature.items(), start=1):
        ref = reference[feature]
        row: list = [
            _wrap(f"{feature} ({ref.unit})"),
            f"{ref.control_mean:g} ± {ref.control_sd:g}",
            f"{ref.aclr_mean:g} ± {ref.aclr_sd:g}",
        ]
        for c, trial in enumerate(trials, start=3):
            found = per_trial.get(trial.trial_id)
            if found is None:
                row.append("-")
                continue
            row.append(f"{found.value:.4g}")
            level = _CLOSER_LEVEL.get(found.closer_to, RiskLevel.MODERATE)
            cell_cmds.append(
                ("BACKGROUND", (c, r), (c, r), colors.HexColor(RISK_BG_COLORS[level]))
            )
            cell_cmds.append(
                ("TEXTCOLOR", (c, r), (c, r), colors.HexColor(RISK_COLORS[level]))
            )
            cell_cmds.append(("FONTNAME", (c, r), (c, r), "DejaVu-Bold"))
        rows.append(row)
    trial_w = (CONTENT_W - 11.4 * cm) / max(len(trials), 1)
    widths = [5.4 * cm, 3.0 * cm, 3.0 * cm] + [trial_w] * len(trials)
    table = _table(rows, widths)
    table.setStyle(TableStyle(cell_cmds))
    return table


def _indicator_table(result: ParticipantResult, lang: str) -> Table | None:
    """All triggered risk indicators of all trials in one table."""
    rows: list[list] = [[
        tr("report.trial", lang), tr("report.indicator", lang),
        tr("report.observed", lang), tr("report.reference", lang),
        tr("report.level", lang),
    ]]
    levels: list[RiskLevel] = []
    for trial in result.trials:
        for r in trial.risk_indicators:
            if not r.triggered:
                continue
            name = r.name_tr if (lang == "tr" and r.name_tr) else r.name
            rows.append([trial.trial_id, _wrap(name), _fmt(r.observed_value),
                         _wrap(r.reference), risk_label(r.risk_level, lang)])
            levels.append(r.risk_level)
    if not levels:
        return None
    table = _table(rows, [3.2 * cm, 4.8 * cm, 2.0 * cm, 5.2 * cm, 2.6 * cm])
    table.setStyle(TableStyle(_risk_cell_style(levels)))
    return table


def _plot_grid(result: ParticipantResult, plot_dir: Path) -> Table | None:
    """Fz/event plots for all trials, two per row."""
    images: list[Image] = []
    for trial in result.trials:
        if trial.data is None:
            continue
        img_path = plots.plot_fz_with_events(trial.data, trial, plot_dir)
        if img_path is not None:
            images.append(_scaled_image(img_path, PLOT_GRID_W))
    if not images:
        return None
    rows = [images[i:i + 2] for i in range(0, len(images), 2)]
    if len(rows[-1]) == 1:
        rows[-1].append("")
    t = Table(rows, colWidths=[CONTENT_W / 2] * 2)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def generate_pdf_report(
    result: ParticipantResult,
    output_dir: Path,
    include_plots: bool = True,
    language: str = "en",
) -> Path:
    """Write the participant PDF report (``language``: ``en`` or ``tr``)."""
    lang = language if language in ("en", "tr") else "en"
    _register_fonts()
    styles = _styles()
    ensure_dir(output_dir)
    suffix = "" if lang == "en" else f"_{lang}"
    out_path = Path(output_dir) / f"{result.participant_id}_biomech_report{suffix}.pdf"

    story: list = [
        Paragraph(tr("report.title", lang), styles["title"]),
        _info_box(result, lang),
        Spacer(1, 10),
        _risk_banner(
            f"{tr('report.overall_risk', lang)}: {risk_label(result.overall_risk, lang)}",
            result.overall_risk,
            CONTENT_W,
        ),
    ]

    # ---- findings summary (one row per trial) -----------------------------
    if result.trials:
        story.append(Paragraph(tr("report.trial_overview", lang), styles["h2"]))
        rows: list[list] = [[
            tr("report.trial", lang), "SSC",
            tr("report.triggered_count", lang), tr("report.level", lang),
        ]]
        levels = []
        for trial in result.trials:
            ssc = trial.features.ssc_category
            triggered = [r for r in trial.risk_indicators if r.triggered]
            rows.append([
                trial.trial_id,
                tr(f"ssc.{ssc}", lang) if ssc else "-",
                str(len(triggered)),
                risk_label(trial.overall_risk, lang),
            ])
            levels.append(trial.overall_risk)
        table = _table(rows, [6.4 * cm, 4.0 * cm, 3.6 * cm, 3.8 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)

    # ---- regional assessment ---------------------------------------------
    all_profile_comps = [pc for t in result.trials for pc in t.profile_comparisons]
    if all_profile_comps:
        statuses = region_status(all_profile_comps)
        story.append(Paragraph(tr("report.region_summary", lang), styles["h2"]))
        rows = [[tr("report.region", lang), tr("report.status", lang)]]
        levels = []
        for region in REGIONS:
            if region not in statuses:
                continue
            rows.append([tr(f"region.{region}", lang),
                         risk_label(statuses[region], lang)])
            levels.append(statuses[region])
        table = _table(rows, [8.9 * cm, 8.9 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)

    # ---- events, one row per trial ----------------------------------------
    if any(t.features.events for t in result.trials):
        story.append(Paragraph(tr("report.events", lang), styles["h2"]))
        story.append(_events_table(result, lang))

    # ---- feature matrix per task (rows = features, cols = trials) ---------
    trials_by_task = {
        task: [t for t in result.trials if t.task.value == task]
        for task in _tasks_in_order(result)
    }
    for task, trials in trials_by_task.items():
        if not any(t.features.features for t in trials):
            continue
        story.append(
            Paragraph(f"{task} — {tr('report.features', lang)}", styles["h2"])
        )
        story.append(_feature_matrix(trials, lang))

    # ---- literature profile matrix per task -------------------------------
    for task, trials in trials_by_task.items():
        table_or_none = _profile_matrix(trials, lang)
        if table_or_none is None:
            continue
        story.append(
            Paragraph(
                f"{task} — {tr('report.profile_comparison', lang)}", styles["h2"]
            )
        )
        story.append(table_or_none)

    # ---- triggered risk indicators, all trials ----------------------------
    indicator_table = _indicator_table(result, lang)
    if indicator_table is not None:
        story.append(Paragraph(tr("report.risk_indicators", lang), styles["h2"]))
        story.append(indicator_table)

    with tempfile.TemporaryDirectory(prefix="biomech_plots_") as tmp:
        plot_dir = Path(tmp)

        # ---- ML output (compact) -----------------------------------------
        if result.ml_output:
            story.append(Paragraph(tr("report.ml_output", lang), styles["h2"]))
            ml = result.ml_output
            story.append(
                Paragraph(
                    f"{tr('report.ml_majority', lang)}: "
                    f"<b>{ml.get('majority_prediction', '-')}</b> "
                    f"({Path(str(ml.get('model_path', '-'))).name})",
                    styles["body"],
                )
            )
            story.append(Spacer(1, 4))
            rows = [[tr("report.trial", lang), tr("report.prediction", lang),
                     tr("report.probabilities", lang)]]
            for t in ml.get("trials", []):
                prob = ", ".join(f"{k}: {v}" for k, v in t.get("probabilities", {}).items())
                rows.append([t.get("trial_id", "-"), t.get("prediction", "-"), prob])
            story.append(_table(rows, [4.0 * cm, 4.0 * cm, 9.8 * cm]))

        # ---- Fz plots, two per row ---------------------------------------
        if include_plots:
            grid = _plot_grid(result, plot_dir)
            if grid is not None:
                story.append(Paragraph(tr("report.plots", lang), styles["h2"]))
                story.append(grid)

        # ---- single-line footnote ----------------------------------------
        story.append(Spacer(1, 12))
        story.append(Paragraph(tr("report.pending_note", lang), styles["footnote"]))

        try:
            decorate = _page_decorator(result, lang)
            doc = SimpleDocTemplate(
                str(out_path),
                pagesize=A4,
                leftMargin=1.6 * cm,
                rightMargin=1.6 * cm,
                topMargin=1.9 * cm,
                bottomMargin=1.7 * cm,
                title=f"Biomechanical report {result.participant_id}",
            )
            doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
        except Exception as exc:
            raise ReportError(f"PDF generation failed: {exc}") from exc

    log.info("Report written: %s (language=%s)", out_path, lang)
    return out_path
