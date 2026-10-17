import json
from pathlib import Path
from tools.audit_pilot_evidence import audit


def test_audit_keeps_failures_and_training_gate(tmp_path):
    run = tmp_path / 'paper-demo'; run.mkdir()
    (run / 'manifest.json').write_text(json.dumps({
        'card_id': 'c1', 'reference_id': 'r1', 'model': 'm',
        'protocol_version': 'v', 'max_questions_per_condition': 0,
        'fixed_decision_turns': 2, 'training_eligible': False}))
    (run / 'summary.json').write_text(json.dumps({
        'calls': 3, 'failed_calls': 1,
        'conditions': [{'plan_completed': False}],
        'semantic_review': 'pending', 'training_eligible': False}))
    result = audit(tmp_path)
    assert result['run_count'] == 1
    assert result['calls'] == 3 and result['failed_calls'] == 1
    assert result['completed_plans'] == 0
    assert result['training_eligible'] is False
    assert result['independent_review_completed'] == 0
