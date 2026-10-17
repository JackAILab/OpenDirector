import pytest
from harness.library.mechanism_report import build_mechanism_report


def test_mechanism_report_is_explainable_and_fail_closed():
    report = build_mechanism_report({'analysis_count': 10,
        'mechanism_taxonomy_counts': {'visible_proof': 8, 'audio_dependency': 10}})
    assert report['schema'] == 'visualagent.ad-mechanism-report.v1'
    assert report['dimensions'][0]['coverage_rate'] == 0.8
    assert report['dimensions'][0]['agent_action']
    assert report['training_eligible'] is False


def test_mechanism_report_rejects_counts_above_total():
    with pytest.raises(ValueError):
        build_mechanism_report({'analysis_count': 2, 'mechanism_coverage': {'visible_proof': 3}})
