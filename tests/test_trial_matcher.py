from pathlib import Path

from biomech_analyzer.core.constants import Condition, Modality, Task
from biomech_analyzer.io.trial_matcher import classify_file


def test_standard_names():
    c = classify_file(Path("SLVJ_baseline_force.csv"))
    assert c.modality is Modality.FORCE_PLATE
    assert c.task is Task.SLVJ
    assert c.condition is Condition.BASELINE
    assert c.is_trial_file


def test_case_and_separator_variants():
    c = classify_file(Path("sldj-Cognitive EMG.mat"))
    assert c.modality is Modality.EMG
    assert c.task is Task.SLDJ
    assert c.condition is Condition.COGNITIVE


def test_synonyms():
    c = classify_file(Path("drop_jump_dualtask_delsys.mat"))
    assert c.task is Task.SLDJ
    assert c.condition is Condition.COGNITIVE
    c2 = classify_file(Path("vertical_natural_xsens.mvnx"))
    assert c2.task is Task.SLVJ
    assert c2.condition is Condition.BASELINE
    assert c2.modality is Modality.XSENS


def test_short_tokens_do_not_false_positive():
    # "dt" must not be found inside "width"; "vj" not inside "svjq..." etc.
    c = classify_file(Path("width_report_force.csv"))
    assert c.condition is None


def test_unrecognizable_name():
    c = classify_file(Path("trial_007_export.csv"))
    assert c.modality is Modality.FORCE_PLATE  # by extension
    assert c.task is None
    assert not c.is_trial_file


def test_extension_beats_keywords():
    # .mvnx file that mentions 'force' in the name stays Xsens.
    c = classify_file(Path("SLVJ_upright_force_xsens.mvnx"))
    assert c.modality is Modality.XSENS
