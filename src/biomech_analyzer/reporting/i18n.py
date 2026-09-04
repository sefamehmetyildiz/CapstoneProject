"""Bilingual (English / Turkish) string tables for report generation.

``tr(key, language)`` returns the localized string; unknown keys fall back
to the key itself so a missing translation never breaks report generation.
"""

from __future__ import annotations

from biomech_analyzer.core.constants import RiskLevel

LANGUAGES = ("en", "tr")

_STRINGS: dict[str, dict[str, str]] = {
    "report.title": {
        "en": "Multimodal Biomechanical Data Acquisition and Automated "
              "Analysis of Single-Leg Jump Performance",
        "tr": "Çok Modaliteli Biyomekanik Veri Toplama ve Tek Bacak Sıçrama "
              "Performansının Otomatik Analizi",
    },
    "report.subtitle": {
        "en": "Biomechanical Risk Report — Participant",
        "tr": "Biyomekanik Risk Raporu — Katılımcı",
    },
    "report.timestamp": {"en": "Analysis timestamp", "tr": "Analiz zamanı"},
    "report.folder": {"en": "Input folder", "tr": "Girdi klasörü"},
    "report.software": {"en": "Software", "tr": "Yazılım"},
    "report.disclaimer_title": {"en": "Disclaimer", "tr": "Yasal Uyarı"},
    "report.disclaimer": {
        "en": "This software provides biomechanical findings, baseline "
              "comparisons and risk indicators as decision-support "
              "information only. It does NOT provide a medical diagnosis "
              "and does not replace the judgment of qualified clinicians "
              "or researchers.",
        "tr": "Bu yazılım; biyomekanik bulguları, referans "
              "karşılaştırmalarını ve risk göstergelerini yalnızca "
              "karar-destek bilgisi olarak sunar. Tıbbi tanı KOYMAZ ve "
              "yetkin klinisyen veya araştırmacıların değerlendirmesinin "
              "yerine geçmez.",
    },
    "report.overall_risk": {
        "en": "Overall biomechanical risk level",
        "tr": "Genel biyomekanik risk düzeyi",
    },
    "report.region_summary": {
        "en": "Regional assessment (literature profile comparison)",
        "tr": "Bölgesel değerlendirme (literatür profil karşılaştırması)",
    },
    "report.validation_summary": {
        "en": "Input validation summary",
        "tr": "Girdi doğrulama özeti",
    },
    "report.unassigned": {"en": "Unassigned files", "tr": "Eşleştirilemeyen dosyalar"},
    "report.pending_note": {
        "en": "Note: formulas and thresholds marked PENDING_BME_VALIDATION "
              "are configurable placeholders awaiting confirmation by the "
              "Biomedical Engineering team.",
        "tr": "Not: PENDING_BME_VALIDATION olarak işaretlenen formül ve "
              "eşikler, Biyomedikal Mühendisliği ekibinin onayını bekleyen "
              "yapılandırılabilir yer tutuculardır.",
    },
    "report.trial": {"en": "Trial", "tr": "Deneme"},
    "report.events": {"en": "Event detection", "tr": "Olay tespiti"},
    "report.event": {"en": "Event", "tr": "Olay"},
    "report.time_s": {"en": "Time (s)", "tr": "Zaman (s)"},
    "report.takeoff": {"en": "Take-off", "tr": "Kalkış"},
    "report.initial_contact": {"en": "Initial contact", "tr": "İlk temas"},
    "report.peak_force": {"en": "Peak landing force", "tr": "Maksimum iniş kuvveti"},
    "report.stabilization": {"en": "Stabilization", "tr": "Stabilizasyon"},
    "report.ssc": {
        "en": "Stretch-shortening cycle (SSC) category",
        "tr": "Gerilme-kısalma döngüsü (SSC) kategorisi",
    },
    "report.sync": {"en": "Synchronization", "tr": "Senkronizasyon"},
    "report.sync_strategy": {"en": "Strategy", "tr": "Strateji"},
    "report.features": {
        "en": "Extracted biomechanical features",
        "tr": "Çıkarılan biyomekanik parametreler",
    },
    "report.feature": {"en": "Feature", "tr": "Parametre"},
    "report.value": {"en": "Value", "tr": "Değer"},
    "report.unit": {"en": "Unit", "tr": "Birim"},
    "report.source": {"en": "Source", "tr": "Kaynak"},
    "report.validation": {"en": "Validation", "tr": "Doğrulama"},
    "report.baseline_comparison": {
        "en": "Normative baseline comparison",
        "tr": "Normatif referans karşılaştırması",
    },
    "report.baseline_mean": {"en": "Baseline mean", "tr": "Referans ort."},
    "report.sd": {"en": "SD", "tr": "SS"},
    "report.zscore": {"en": "z-score", "tr": "z-skoru"},
    "report.interpretation": {"en": "Interpretation", "tr": "Yorum"},
    "report.profile_comparison": {
        "en": "Literature profile comparison (Control vs ACLR)",
        "tr": "Literatür profil karşılaştırması (Kontrol vs ÖÇB)",
    },
    "report.control_profile": {"en": "Control profile", "tr": "Kontrol profili"},
    "report.aclr_profile": {"en": "ACLR profile", "tr": "ÖÇB profili"},
    "report.closer_to": {"en": "Closer to", "tr": "Yakın olduğu profil"},
    "report.region": {"en": "Region", "tr": "Bölge"},
    "report.risk_indicators": {
        "en": "Risk indicators (decision-support only)",
        "tr": "Risk göstergeleri (yalnızca karar-destek)",
    },
    "report.indicator": {"en": "Indicator", "tr": "Gösterge"},
    "report.observed": {"en": "Observed", "tr": "Gözlenen"},
    "report.reference": {"en": "Reference", "tr": "Referans"},
    "report.level": {"en": "Level", "tr": "Düzey"},
    "report.no_indicator": {
        "en": "No configured risk indicator was triggered for this trial.",
        "tr": "Bu deneme için tanımlı hiçbir risk göstergesi tetiklenmedi.",
    },
    "report.trial_warnings": {"en": "Trial warnings", "tr": "Deneme uyarıları"},
    "report.ml_output": {
        "en": "Research Mode / machine learning output",
        "tr": "Araştırma Modu / makine öğrenmesi çıktısı",
    },
    "report.ml_majority": {"en": "Majority prediction", "tr": "Çoğunluk tahmini"},
    "report.ml_model": {"en": "model", "tr": "model"},
    "report.prediction": {"en": "Prediction", "tr": "Tahmin"},
    "report.probabilities": {"en": "Probabilities", "tr": "Olasılıklar"},
    "report.warnings_limitations": {
        "en": "Warnings and limitations",
        "tr": "Uyarılar ve sınırlılıklar",
    },
    "report.no_warnings": {
        "en": "No participant-level warnings.",
        "tr": "Katılımcı düzeyinde uyarı yok.",
    },
    "report.references": {"en": "Literature references", "tr": "Literatür kaynakları"},
    "report.forceplate": {"en": "Force plate", "tr": "Kuvvet platformu"},
    "report.emg": {"en": "sEMG", "tr": "sEMG"},
    "report.xsens": {"en": "Xsens", "tr": "Xsens"},
    "report.status": {"en": "Status", "tr": "Durum"},
    "report.complete": {"en": "complete", "tr": "tam"},
    "report.incomplete": {"en": "incomplete", "tr": "eksik"},
    "report.missing": {"en": "MISSING", "tr": "EKSİK"},
    # Modalities / regions / misc values
    "modality.force_plate": {"en": "force plate", "tr": "kuvvet platformu"},
    "modality.emg": {"en": "sEMG", "tr": "sEMG"},
    "modality.xsens": {"en": "Xsens", "tr": "Xsens"},
    "region.knee": {"en": "Knee", "tr": "Diz"},
    "region.hip": {"en": "Hip", "tr": "Kalça"},
    "region.ankle": {"en": "Ankle", "tr": "Ayak bileği"},
    "region.global": {"en": "Global (whole limb)", "tr": "Genel (tüm bacak)"},
    "ssc.good": {"en": "Good", "tr": "İyi"},
    "ssc.moderate": {"en": "Moderate", "tr": "Orta"},
    "ssc.poor": {"en": "Poor", "tr": "Zayıf"},
    "ssc.unknown": {"en": "Not classifiable", "tr": "Sınıflandırılamadı"},
    "closer.control": {"en": "Control", "tr": "Kontrol"},
    "closer.aclr": {"en": "ACLR-associated", "tr": "ÖÇB ile ilişkili"},
    "closer.between": {"en": "Between profiles", "tr": "Profiller arası"},
    "risk.LOW": {"en": "LOW", "tr": "DÜŞÜK"},
    "risk.MODERATE": {"en": "MODERATE", "tr": "ORTA"},
    "risk.HIGH": {"en": "HIGH", "tr": "YÜKSEK"},
    "risk.NONE": {"en": "NONE", "tr": "YOK"},
    # Baseline interpretation templates (mirror diagnostics/baseline_comparison)
    "interp.within the baseline range": {
        "en": "within the baseline range",
        "tr": "referans aralığın içinde",
    },
    "interp.moderately above the baseline range": {
        "en": "moderately above the baseline range",
        "tr": "referans aralığın orta düzeyde üzerinde",
    },
    "interp.moderately below the baseline range": {
        "en": "moderately below the baseline range",
        "tr": "referans aralığın orta düzeyde altında",
    },
    "interp.markedly above the baseline range": {
        "en": "markedly above the baseline range",
        "tr": "referans aralığın belirgin üzerinde",
    },
    "interp.markedly below the baseline range": {
        "en": "markedly below the baseline range",
        "tr": "referans aralığın belirgin altında",
    },
    "interp.baseline SD is zero; z-score unavailable": {
        "en": "baseline SD is zero; z-score unavailable",
        "tr": "referans SS sıfır; z-skoru hesaplanamadı",
    },
}


def tr(key: str, language: str = "en") -> str:
    """Localized string for ``key`` (falls back to English, then the key)."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(language) or entry.get("en") or key


def tr_interpretation(text: str, language: str) -> str:
    """Translate a baseline-comparison interpretation sentence."""
    if language == "en":
        return text
    return tr(f"interp.{text}", language) if f"interp.{text}" in _STRINGS else text


def risk_label(level: RiskLevel, language: str) -> str:
    return tr(f"risk.{level.value}", language)
