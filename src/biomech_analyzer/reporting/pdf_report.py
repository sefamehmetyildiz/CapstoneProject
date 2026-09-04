"""Standardized bilingual (EN/TR) PDF report generation — expert layout.

Compact, table-driven template aimed at expert readers: descriptive
headings, no explanatory prose, no boilerplate sections (disclaimer,
validation summary, sync details, warnings and references are omitted).
DejaVu Sans (bundled with matplotlib) is registered so Turkish characters
render correctly; risk levels colour the report (high = red,
moderate = orange, low = green).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
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
            "title", parent=base, fontName="DejaVu-Bold", fontSize=13, leading=17,
            alignment=1, spaceAfter=2,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base, fontName="DejaVu-Bold", fontSize=11.5, leading=15,
            spaceBefore=10, spaceAfter=3, textColor=colors.HexColor("#1a3b5d"),
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName="DejaVu-Bold", fontSize=9.5, leading=12,
            spaceBefore=8, spaceAfter=2, textColor=colors.HexColor("#2e4d6b"),
        ),
        "body": base,
        "small": ParagraphStyle(
            "small", parent=base, fontSize=7.5, leading=9.5,
            textColor=colors.HexColor("#444444"),
        ),
        "footnote": ParagraphStyle(
            "footnote", parent=base, fontSize=7, leading=9,
            textColor=colors.HexColor("#6b7280"),
        ),
    }


def _table(data: list[list], col_widths: list[float] | None = None) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b0b0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f7f9fc")]),
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


_CELL_STYLE = ParagraphStyle(
    "cell", fontName="DejaVu", fontSize=7.5, leading=9.5
)
_CELL_BOLD_STYLE = ParagraphStyle(
    "cellb", fontName="DejaVu-Bold", fontSize=7.5, leading=9.5
)


def _wrap(text: str, bold: bool = False) -> Paragraph:
    """Wrappable table cell (plain strings do not wrap in ReportLab tables)."""
    return Paragraph(text, _CELL_BOLD_STYLE if bold else _CELL_STYLE)


def _scaled_image(path: Path, width: float) -> Image:
    from reportlab.lib.utils import ImageReader

    iw, ih = ImageReader(str(path)).getSize()
    return Image(str(path), width=width, height=width * ih / iw)


def _risk_cell_style(rows: list[RiskLevel], header_offset: int = 1) -> list[tuple]:
    cmds: list[tuple] = []
    for i, level in enumerate(rows):
        r = i + header_offset
        cmds.append(("TEXTCOLOR", (-1, r), (-1, r), colors.HexColor(RISK_COLORS[level])))
        cmds.append(("BACKGROUND", (-1, r), (-1, r), colors.HexColor(RISK_BG_COLORS[level])))
        cmds.append(("FONTNAME", (-1, r), (-1, r), "DejaVu-Bold"))
    return cmds


def _trial_story(
    trial: TrialResult, styles: dict, plot_dir: Path, include_plots: bool, lang: str
) -> list:
    story: list = [
        Paragraph(
            f"{tr('report.trial', lang)} {trial.trial_id} — "
            f"<font color='{RISK_COLORS[trial.overall_risk]}'>"
            f"{risk_label(trial.overall_risk, lang)}</font>",
            styles["h1"],
        )
    ]

    # ---- events + SSC in one compact table --------------------------------
    ev = trial.features.events
    if ev is not None:
        ssc = trial.features.ssc_category
        ssc_text = tr(f"ssc.{ssc}", lang) if ssc else "-"
        story.append(
            _table(
                [
                    [
                        _wrap(tr("report.initial_contact", lang), bold=True),
                        _wrap(tr("report.takeoff", lang), bold=True),
                        _wrap(tr("report.peak_force", lang), bold=True),
                        _wrap(tr("report.stabilization", lang), bold=True),
                        _wrap("SSC", bold=True),
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
        widths = [8.0 * cm, 3.4 * cm, 2.6 * cm]
        if z_by_feature:  # z column only when a normative baseline was given
            headers.append(tr("report.zscore", lang))
            widths = [7.0 * cm, 3.0 * cm, 2.4 * cm, 2.4 * cm]
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
        table = _table(rows, [3.5 * cm, 1.7 * cm, 2.2 * cm, 3.7 * cm, 3.7 * cm, 3.0 * cm])
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
        table = _table(rows, [4.8 * cm, 3.0 * cm, 1.8 * cm, 5.6 * cm, 2.6 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)

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

    story.append(PageBreak())
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

    content_width = 17.8 * cm
    story: list = [
        Paragraph(tr("report.title", lang), styles["title"]),
        Paragraph(
            f"{tr('report.subtitle', lang)} <b>{result.participant_id}</b> · "
            f"{result.analysis_timestamp} · biomech-analyzer v{__version__}",
            styles["small"],
        ),
        Paragraph(f"{tr('report.folder', lang)}: {result.folder}", styles["small"]),
        Spacer(1, 8),
        _risk_banner(
            f"{tr('report.overall_risk', lang)}: {risk_label(result.overall_risk, lang)}",
            result.overall_risk,
            content_width,
        ),
        Spacer(1, 8),
    ]

    # ---- regional assessment ---------------------------------------------
    all_profile_comps = [pc for t in result.trials for pc in t.profile_comparisons]
    if all_profile_comps:
        statuses = region_status(all_profile_comps)
        story.append(Paragraph(tr("report.region_summary", lang), styles["h1"]))
        rows = [[tr("report.region", lang), tr("report.status", lang)]]
        levels = []
        for region in REGIONS:
            if region not in statuses:
                continue
            rows.append([tr(f"region.{region}", lang),
                         risk_label(statuses[region], lang)])
            levels.append(statuses[region])
        table = _table(rows, [8 * cm, 5 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)

    story.append(PageBreak())

    with tempfile.TemporaryDirectory(prefix="biomech_plots_") as tmp:
        plot_dir = Path(tmp)
        for trial in result.trials:
            story.extend(_trial_story(trial, styles, plot_dir, include_plots, lang))

        # ---- ML output (compact) -----------------------------------------
        if result.ml_output:
            story.append(Paragraph(tr("report.ml_output", lang), styles["h1"]))
            ml = result.ml_output
            story.append(
                Paragraph(
                    f"{tr('report.ml_majority', lang)}: "
                    f"<b>{ml.get('majority_prediction', '-')}</b> "
                    f"({Path(str(ml.get('model_path', '-'))).name})",
                    styles["body"],
                )
            )
            rows = [[tr("report.trial", lang), tr("report.prediction", lang),
                     tr("report.probabilities", lang)]]
            for t in ml.get("trials", []):
                prob = ", ".join(f"{k}: {v}" for k, v in t.get("probabilities", {}).items())
                rows.append([t.get("trial_id", "-"), t.get("prediction", "-"), prob])
            story.append(_table(rows, [3.5 * cm, 3.5 * cm, 9 * cm]))

        # ---- single-line footnote ----------------------------------------
        story.append(Spacer(1, 10))
        story.append(Paragraph(tr("report.pending_note", lang), styles["footnote"]))

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

    log.info("Report written: %s (language=%s)", out_path, lang)
    return out_path
