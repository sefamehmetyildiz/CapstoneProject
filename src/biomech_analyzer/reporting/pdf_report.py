"""Standardized bilingual (EN/TR) PDF report generation.

Built with ReportLab. The DejaVu Sans fonts bundled with matplotlib are
registered so Turkish characters render correctly. Risk levels colour the
report (high = red, moderate = orange, low = green). The report presents
decision-support findings only and carries an explicit disclaimer.
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
    VALIDATION_PENDING,
    Modality,
    RiskLevel,
)
from biomech_analyzer.core.exceptions import ReportError
from biomech_analyzer.core.models import ParticipantResult, TrialResult
from biomech_analyzer.diagnostics.profile_comparison import (
    REGIONS,
    load_reference_profiles,
    region_status,
)
from biomech_analyzer.reporting import plots
from biomech_analyzer.reporting.i18n import risk_label, tr, tr_interpretation
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
            alignment=1, spaceAfter=4,
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
        "warn": ParagraphStyle(
            "warn", parent=base, fontSize=8, textColor=colors.HexColor("#8a5a00"),
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base, borderColor=colors.HexColor("#8a5a00"),
            borderWidth=1, borderPadding=6, backColor=colors.HexColor("#fff6e5"),
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
    """A single-cell colour-coded banner for risk levels."""
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
    return Image(str(path), width=width, height=width * ih / iw)


def _risk_cell_style(rows: list[RiskLevel], header_offset: int = 1) -> list[tuple]:
    """Colour the 'level' column cells of a table by risk level."""
    cmds: list[tuple] = []
    for i, level in enumerate(rows):
        cmds.append(
            ("TEXTCOLOR", (-1, i + header_offset), (-1, i + header_offset),
             colors.HexColor(RISK_COLORS[level]))
        )
        cmds.append(
            ("BACKGROUND", (-1, i + header_offset), (-1, i + header_offset),
             colors.HexColor(RISK_BG_COLORS[level]))
        )
        cmds.append(
            ("FONTNAME", (-1, i + header_offset), (-1, i + header_offset),
             "DejaVu-Bold")
        )
    return cmds


def _trial_story(
    trial: TrialResult, styles: dict, plot_dir: Path, include_plots: bool, lang: str
) -> list:
    story: list = [
        Paragraph(
            f"{tr('report.trial', lang)} {trial.trial_id} — "
            f"{tr('report.level', lang)}: "
            f"<font color='{RISK_COLORS[trial.overall_risk]}'>"
            f"{risk_label(trial.overall_risk, lang)}</font>",
            styles["h1"],
        )
    ]

    ev = trial.features.events
    if ev is not None:
        story.append(Paragraph(tr("report.events", lang), styles["h2"]))
        ssc = trial.features.ssc_category
        ssc_text = tr(f"ssc.{ssc}", lang) if ssc else tr("ssc.unknown", lang)
        story.append(
            _table(
                [
                    [tr("report.event", lang), tr("report.time_s", lang)],
                    [tr("report.takeoff", lang), _fmt(ev.takeoff_s)],
                    [tr("report.initial_contact", lang), _fmt(ev.initial_contact_s)],
                    [tr("report.peak_force", lang), _fmt(ev.peak_force_s)],
                    [tr("report.stabilization", lang), _fmt(ev.stabilization_s)],
                    [tr("report.ssc", lang), ssc_text],
                ],
                [7 * cm, 5 * cm],
            )
        )

    if trial.sync is not None:
        story.append(Paragraph(tr("report.sync", lang), styles["h2"]))
        story.append(
            Paragraph(
                f"{tr('report.sync_strategy', lang)}: <b>{trial.sync.strategy}</b>. "
                + " ".join(trial.sync.notes),
                styles["small"],
            )
        )

    if trial.features.features:
        story.append(Paragraph(tr("report.features", lang), styles["h2"]))
        rows = [[
            tr("report.feature", lang), tr("report.value", lang),
            tr("report.unit", lang), tr("report.source", lang),
            tr("report.validation", lang),
        ]]
        for fv in trial.features.features.values():
            rows.append(
                [fv.name, f"{fv.value:.4g}", fv.unit,
                 tr(f"modality.{fv.modality.value}", lang), fv.validation_status]
            )
        story.append(_table(rows, [5.2 * cm, 2.2 * cm, 1.8 * cm, 3.0 * cm, 4.2 * cm]))

    if trial.profile_comparisons:
        story.append(Paragraph(tr("report.profile_comparison", lang), styles["h2"]))
        rows = [[
            tr("report.feature", lang), tr("report.region", lang),
            tr("report.value", lang),
            f"{tr('report.control_profile', lang)} (μ±σ)",
            f"{tr('report.aclr_profile', lang)} (μ±σ)",
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
                    pc.feature,
                    tr(f"region.{pc.region}", lang),
                    f"{pc.value:.4g} {pc.unit}",
                    f"{pc.control_mean:g} ± {pc.control_sd:g} (z={pc.z_control:+.1f})",
                    f"{pc.aclr_mean:g} ± {pc.aclr_sd:g} (z={pc.z_aclr:+.1f})",
                    tr(f"closer.{pc.closer_to}", lang),
                ]
            )
        table = _table(rows, [3.4 * cm, 2.2 * cm, 2.4 * cm, 3.7 * cm, 3.7 * cm, 3.0 * cm])
        table.setStyle(TableStyle(_risk_cell_style(closer_levels)))
        story.append(table)

    if trial.baseline_comparisons:
        story.append(Paragraph(tr("report.baseline_comparison", lang), styles["h2"]))
        rows = [[
            tr("report.feature", lang), tr("report.value", lang),
            tr("report.baseline_mean", lang), tr("report.sd", lang),
            tr("report.zscore", lang), tr("report.interpretation", lang),
        ]]
        for c in trial.baseline_comparisons:
            rows.append(
                [
                    c.feature, f"{c.participant_value:.4g}",
                    f"{c.baseline_mean:.4g}", f"{c.baseline_std:.4g}",
                    "-" if c.z_score is None else f"{c.z_score:+.2f}",
                    tr_interpretation(c.interpretation, lang),
                ]
            )
        story.append(_table(rows, [4.2 * cm, 1.9 * cm, 2.3 * cm, 1.5 * cm, 1.7 * cm, 4.8 * cm]))

    triggered = [r for r in trial.risk_indicators if r.triggered]
    story.append(Paragraph(tr("report.risk_indicators", lang), styles["h2"]))
    if triggered:
        rows = [[
            tr("report.indicator", lang), tr("report.feature", lang),
            tr("report.observed", lang), tr("report.reference", lang),
            tr("report.level", lang),
        ]]
        levels = []
        for r in triggered:
            name = r.name_tr if (lang == "tr" and r.name_tr) else r.name
            rows.append([name, r.feature, _fmt(r.observed_value), r.reference,
                         risk_label(r.risk_level, lang)])
            levels.append(r.risk_level)
        table = _table(rows, [4.4 * cm, 3.0 * cm, 1.8 * cm, 4.6 * cm, 2.6 * cm])
        table.setStyle(TableStyle(_risk_cell_style(levels)))
        story.append(table)
        for r in triggered:
            name = r.name_tr if (lang == "tr" and r.name_tr) else r.name
            expl = r.explanation_tr if (lang == "tr" and r.explanation_tr) else r.explanation
            story.append(Paragraph(f"<b>{name}:</b> {expl}", styles["small"]))
    else:
        story.append(Paragraph(tr("report.no_indicator", lang), styles["body"]))

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
        story.append(Paragraph(tr("report.trial_warnings", lang), styles["h2"]))
        for w in dict.fromkeys(trial.warnings):
            story.append(Paragraph(f"• {w}", styles["warn"]))
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
        Spacer(1, 4),
        Paragraph(
            f"{tr('report.subtitle', lang)} <b>{result.participant_id}</b>",
            styles["h1"],
        ),
        Paragraph(f"{tr('report.timestamp', lang)}: {result.analysis_timestamp}", styles["body"]),
        Paragraph(f"{tr('report.folder', lang)}: {result.folder}", styles["body"]),
        Paragraph(
            f"{tr('report.software', lang)}: biomech-analyzer v{__version__}",
            styles["body"],
        ),
        Spacer(1, 8),
        _risk_banner(
            f"{tr('report.overall_risk', lang)}: {risk_label(result.overall_risk, lang)}",
            result.overall_risk,
            content_width,
        ),
        Spacer(1, 8),
    ]

    # ---- Regional assessment ---------------------------------------------
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
        story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            f"<b>{tr('report.disclaimer_title', lang)}.</b> "
            f"{tr('report.disclaimer', lang)}",
            styles["disclaimer"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph(tr("report.validation_summary", lang), styles["h1"]))

    rows = [[
        tr("report.trial", lang), tr("report.forceplate", lang),
        tr("report.emg", lang), tr("report.xsens", lang), tr("report.status", lang),
    ]]
    for pkg in sorted(result.validation.trials, key=lambda p: p.trial_id):
        def _cell(m: Modality, _pkg=pkg) -> str:
            f = _pkg.files.get(m)
            return f.path.name if f else tr("report.missing", lang)

        rows.append(
            [
                pkg.trial_id,
                _cell(Modality.FORCE_PLATE),
                _cell(Modality.EMG),
                _cell(Modality.XSENS),
                tr("report.complete", lang) if pkg.is_complete
                else tr("report.incomplete", lang),
            ]
        )
    story.append(_table(rows, [3.0 * cm, 4.3 * cm, 4.3 * cm, 4.3 * cm, 2.0 * cm]))

    if result.validation.unmatched_files:
        story.append(Paragraph(tr("report.unassigned", lang), styles["h2"]))
        for p in result.validation.unmatched_files:
            story.append(Paragraph(f"• {p.name}", styles["warn"]))

    pending = any(
        fv.validation_status == VALIDATION_PENDING
        for t in result.trials
        for fv in t.features.features.values()
    )
    if pending:
        story.append(Spacer(1, 4))
        story.append(Paragraph(tr("report.pending_note", lang), styles["warn"]))
    story.append(PageBreak())

    with tempfile.TemporaryDirectory(prefix="biomech_plots_") as tmp:
        plot_dir = Path(tmp)
        for trial in result.trials:
            story.extend(_trial_story(trial, styles, plot_dir, include_plots, lang))

        if result.ml_output:
            story.append(Paragraph(tr("report.ml_output", lang), styles["h1"]))
            ml = result.ml_output
            story.append(
                Paragraph(
                    f"{tr('report.ml_majority', lang)}: "
                    f"<b>{ml.get('majority_prediction', '-')}</b> "
                    f"({tr('report.ml_model', lang)}: {ml.get('model_path', '-')})",
                    styles["body"],
                )
            )
            rows = [[tr("report.trial", lang), tr("report.prediction", lang),
                     tr("report.probabilities", lang)]]
            for t in ml.get("trials", []):
                prob = ", ".join(f"{k}: {v}" for k, v in t.get("probabilities", {}).items())
                rows.append([t.get("trial_id", "-"), t.get("prediction", "-"), prob])
            story.append(_table(rows, [3.5 * cm, 3.5 * cm, 9 * cm]))
            for w in ml.get("warnings", []):
                story.append(Paragraph(f"• {w}", styles["warn"]))

        story.append(Paragraph(tr("report.warnings_limitations", lang), styles["h1"]))
        all_warnings = list(dict.fromkeys(result.warnings + result.validation.warnings))
        if all_warnings:
            for w in all_warnings:
                story.append(Paragraph(f"• {w}", styles["warn"]))
        else:
            story.append(Paragraph(tr("report.no_warnings", lang), styles["body"]))

        # ---- References ---------------------------------------------------
        used_sources = sorted({pc.source for pc in all_profile_comps if pc.source})
        if used_sources:
            try:
                profiles = load_reference_profiles()
                story.append(Paragraph(tr("report.references", lang), styles["h1"]))
                for key in used_sources:
                    citation = profiles.sources.get(key, key)
                    story.append(Paragraph(f"• {citation}", styles["small"]))
            except Exception:  # references are optional decoration
                pass

        story.append(Spacer(1, 8))
        story.append(Paragraph(tr("report.disclaimer", lang), styles["disclaimer"]))

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
