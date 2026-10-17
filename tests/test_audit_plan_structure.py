import json
from tools.audit_plan_structure import inspect_plan


def test_structural_audit_accepts_contiguous_plan(tmp_path):
    p = tmp_path / 'plan.json'
    p.write_text(json.dumps({'result': {'claim': 'claim',
        'shots': [{'start': 0, 'end': 1, 'visual': 'v', 'audio': 'a', 'caption': 'c'},
                  {'start': 1, 'end': 2, 'visual': 'v2', 'audio': 'a2', 'caption': ''}],
        'fact_basis': ['f'], 'unresolved': []}}))
    assert inspect_plan(p)['complete'] is True


def test_structural_audit_reports_gaps(tmp_path):
    p = tmp_path / 'plan.json'; p.write_text(json.dumps({'result': {'claim': '', 'shots': []}}))
    result = inspect_plan(p)
    assert result['complete'] is False
    assert 'missing_claim' in result['issues'] and 'missing_shots' in result['issues']
