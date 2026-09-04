"""Standardized bilingual (EN/TR) PDF report generation — clinical layout.

Compact, table-driven template aimed at expert readers, styled like a
clinical/laboratory report: a repeating page header band and numbered
footer, a patient-information style summary box, uniform full-width
tables with a single header style, and a continuous flow (no forced page
break per trial) to avoid half-empty pages. DejaVu Sans (bundled with
matplotlib) is registered so Turkish characters render correctly; risk
levels colour the report (high = red, moderate = orange, low = green).
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
    KeepTogether,
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
from biomech_analyzer.core.models import ParticipantResult, TrialResult
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
PLOT_W = 14.2 * cm


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


def _trial_heading(trial: TrialResult, lang: str) -> Table:
    """Navy section band with the trial name and its risk chip."""
    level = trial.overall_risk
    left = Paragraph(
        f"{tr('report.trial', lang)} {trial.trial_id}",
        ParagraphStyle(
            "th", fontName="DejaVu-Bold", fontSize=9.5, leading=12,
            textColor=colors.white,
        ),
    )
    t = Table([[left, risk_label(level, lang)]], colWidths=[13.8 * cm, 4.0 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(NAVY)),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(RISK_BG_COLORS[level])),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor(RISK_COLORS[level])),
                ("FONTNAME", (1, 0), (1, 0), "DejaVu-Bold"),
                ("FONTSIZE", (1, 0), (1, 0), 9),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
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


def _trial_story(
    trial: TrialResult, styles: dict, plot_dir: Path, include_plots: bool, lang: str
) -> list:
    story: list = [Spacer(1, 12)]

    # ---- section band + events/SSC table kept together --------------------
    head: list = [_trial_heading(trial, lang), Spacer(1, 6)]
    ev = trial.features.events
    if ev is not None:
        ssc = trial.features.ssc_category
        ssc_text = tr(f"ssc.{ssc}", lang) if ssc else "-"
        head.append(
            _table(
                [
                    [
                        tr("report.initial_contact", lang),
                        tr("report.takeoff", lang),
                        tr("report.peak_force", lang),
                        tr("report.stabilization", lang),
                        "SSC",
                    ],
                    [
                        _fmt(ev.initial_contact_s),
                        _fmt(ev.takeoff_s),
                        _fmt(ev.peak_force_s),
                        _fmt(ev.stabilization_s),
                        ssc_text,
                    ],
                ],
                [3.6 * cm, 3.2 * cm, 4.2 * cm, 3.8 * cm, 3.0 * cm],
            )
        )
    story.append(KeepTogether(head))

    # ---- features (baseline z merged in) ----------------------------------
    if trial.features.features:
        story.append(Paragraph(tr("report.features", lang), styles["h2"]))
        z_by_feature = {
            c.feature: c.z_score
            for c in trial.baseline_comparisons
            if c.z_score is not None
        }
        headers = [tr("report.feature", lang), tr("report.value", lang),
                   tr("report.unit", lang)]
        widths = [9.8 * cm, 4.4 * cm, 3.6 * cm]
        if z_by_feature:  # z column only when a normative baseline was given
            headers.append(tr("report.zscore", lang))
            widths = [8.6 * cm, 3.6 * cm, 2.8 * cm, 2.8 * cm]
        rows = [headers]
        for fv in trial.features.features.values():
            row = [fv.name, f"{fv.value:.4g}", fv.unit]
            if z_by_feature:
                z = z_by_feature.get(fv.name)
                row.append("-" if z is None else f"{z:+.2f}")
            rows.append(row)
        story.append(_table(rows, widths))

    # ---- literature profile comparison ------------------------------------
    if trial.profile_comparisons:
        story.append(Paragraph(tr("report.profile_comparison", lang), styles["h2"]))
        rows = [[
            tr("report.feature", lang),
            tr("report.region", lang),
            tr("report.value", lang),
            f"{tr('report.control_short', lang)} (μ±σ)",
            f"{tr('report.aclr_short', lang)} (μ±σ)",
            tr("report.closer_to", lang),
        ]]
        closer_levels: list[RiskLevel] = []
        for pc in trial.profile_comparisons:
            closer_levels.append(
                RiskLevel.LOW if pc.closer_to == "control"
                else (RiskLevel.MODERATE if pc.closer_to == "between" else RiskLevel.HIGH)
            )
            rows.append(
                [
                    _wrap(pc.feature),
                    tr(f"region_short.{pc.region}", lang),
                    f"{pc.value:.4g} {pc.unit}",
                    f"{pc.control_mean:g} ± {pc.control_sd:g} (z={pc.z_control:+.1f})",
                    f"{pc.aclr_mean:g} ± {pc.aclr_sd:g} (z={pc.z_aclr:+.1f})",
                    tr(f"closer.{pc.closer_to}", lang),
                ]
            )
        table = _table(rows, [3.9 * cm, 1.6 * cm, 2.1 * cm, 3.6 * cm, 3.6 * cm, 3.0 * cm])
        table.setStyle(TableStyle(_risk_cell_style(closer_levels)))
        story.append(table)

    # ---- triggered risk indicators (table only, no prose) -----------------
    triggered = [r for r in trial.risk_indicators if r.triggered]
    if triggered:
        story.append(Paragraph(tr("report.risk_indicators", lang), styles["h2"]))
        rows = [[
            tr("report.indicator", lang), tr("report.feature", lang),
            tr("report.observed", lang), tr("report.reference", lang),
            tr("report.level", lang),
        ]]
        levels = []
        for r in triggered:
            name = r.name_tr if (lang == "tr" and r.name_tr) else r.name
            rows.append([_wrap(name), _wrap(r.feature), _fmt(r.observed_value),
                         _wrap(r.reference), risk_label(r.risk_level, lang)])
            levels.append(r.risk_level)
        table = _table(rows, [4.6 * cm, 3.2 * cm, 2.2 * cm, 5.2 * cm, 2.6 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)

    if include_plots and trial.data is not None:
        for maker in (plots.plot_fz_with_events, plots.plot_knee_flexion):
            img_path = maker(trial.data, trial, plot_dir)
            if img_path is not None:
                story.append(Spacer(1, 8))
                story.append(_scaled_image(img_path, PLOT_W))
        z_path = plots.plot_zscores(trial, plot_dir)
        if z_path is not None:
            story.append(Spacer(1, 8))
            story.append(_scaled_image(z_path, PLOT_W))

    return story


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
        rows = [[
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

    with tempfile.TemporaryDirectory(prefix="biomech_plots_") as tmp:
        plot_dir = Path(tmp)
        for trial in result.trials:
            story.extend(_trial_story(trial, styles, plot_dir, include_plots, lang))

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
