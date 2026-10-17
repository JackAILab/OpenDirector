#!/usr/bin/env python3
"""Audit aggregate state of local research pilot runs without exposing raw payloads."""
import argparse
import json
from pathlib import Path
import hashlib


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def audit(root: Path):
    rows = []
    errors = []
    for run in sorted(root.glob('paper-*')):
        manifest_path, summary_path = run / 'manifest.json', run / 'summary.json'
        if not run.is_dir() or not manifest_path.exists() or not summary_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
            summary = json.loads(summary_path.read_text())
            if manifest.get('training_eligible') is not False:
                errors.append({'run': run.name, 'error': 'training_gate'}); continue
            if summary.get('training_eligible') is not False:
                errors.append({'run': run.name, 'error': 'summary_training_gate'}); continue
            conditions = summary.get('conditions', [])
            rows.append({
                'run': run.name,
                'card_id': manifest.get('card_id'),
                'reference_id': manifest.get('reference_id'),
                'model': manifest.get('model'),
                'protocol_version': manifest.get('protocol_version'),
                'question_budget': manifest.get('max_questions_per_condition'),
                'fixed_decision_turns': manifest.get('fixed_decision_turns'),
                'calls': summary.get('calls', 0),
                'failed_calls': summary.get('failed_calls', 0),
                'completed_plans': sum(bool(c.get('plan_completed')) for c in conditions),
                'conditions': conditions,
                'semantic_review': summary.get('semantic_review'),
                'training_eligible': False,
                'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            })
        except Exception as exc:
            errors.append({'run': run.name, 'error': type(exc).__name__})
    aggregate = {
        'schema': 'visualagent.pilot-evidence-audit.v1',
        'root_label': 'private_local_learning_runs',
        'run_count': len(rows),
        'calls': sum(r['calls'] for r in rows),
        'failed_calls': sum(r['failed_calls'] for r in rows),
        'completed_plans': sum(r['completed_plans'] for r in rows),
        'training_eligible': False,
        'independent_review_completed': 0,
        'errors': errors,
        'rows': rows,
    }
    aggregate['audit_sha256'] = digest({k: v for k, v in aggregate.items() if k != 'audit_sha256'})
    return aggregate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/var/lib/visualstation-local/creative/learning'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('run_count', 'calls', 'failed_calls', 'completed_plans', 'independent_review_completed', 'errors')}, ensure_ascii=False))
