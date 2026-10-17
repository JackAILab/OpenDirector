#!/usr/bin/env python3
"""Read-only budget stratification; never reads provider payloads or credentials."""
import argparse
import hashlib
import json
from pathlib import Path


def audit(root):
    rows = []
    for path in sorted(root.glob('paper-*/manifest.json')):
        m = json.loads(path.read_text())
        if m.get('fixed_decision_turns') != 2:
            continue
        summary_path = path.parent / 'summary.json'
        s = json.loads(summary_path.read_text()) if summary_path.exists() else None
        errors = []
        for event_path in sorted(path.parent.glob('*-event.json')):
            e = json.loads(event_path.read_text())
            if e.get('state') == 'failed':
                errors.append({'stage': e.get('stage'), 'error_code': e.get('error_code'),
                               'finish_reason': e.get('diagnostics', {}).get('finish_reason')})
        rows.append({'run': path.parent.name, 'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'model': m.get('model'), 'max_output_tokens': m.get('max_output_tokens'),
                     'fixed_decision_turns': m['fixed_decision_turns'],
                     'question_budget': m.get('max_questions_per_condition'),
                     'card_id': m.get('card_id'), 'reference_id': m.get('reference_id'),
                     'terminal_summary_present': s is not None,
                     'calls': s['calls'] if s else None,
                     'completed_plans': sum(bool(c['plan_completed']) for c in s['conditions']) if s else None,
                     'failures': errors})
    return {'schema': 'visualagent.research-budget-audit.v1', 'rows': rows,
            'training_eligible': False, 'semantic_review': 'pending',
            'warning': 'Different model identifiers/output caps are separate strata; no causal comparison from these counts.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('/var/lib/visualstation-local/creative/learning'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = audit(a.root)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(result['rows']), 'terminal': sum(r['terminal_summary_present'] for r in result['rows'])}))
