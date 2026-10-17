#!/usr/bin/env python3
"""Audit structural completeness of completed plan observations only."""
import argparse
import json
from pathlib import Path


def inspect_plan(path: Path):
    data = json.loads(path.read_text())
    result = data.get('result') if isinstance(data, dict) else None
    issues = []
    if not isinstance(result, dict):
        return {'complete': False, 'issues': ['result_not_object']}
    if not isinstance(result.get('claim'), str) or not result['claim'].strip():
        issues.append('missing_claim')
    shots = result.get('shots')
    if not isinstance(shots, list) or not shots:
        issues.append('missing_shots')
    else:
        previous = None
        for i, shot in enumerate(shots):
            if not isinstance(shot, dict):
                issues.append(f'shot_{i}_not_object'); continue
            start, end = shot.get('start'), shot.get('end')
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
                issues.append(f'shot_{i}_invalid_interval')
            if previous is not None and start != previous:
                issues.append(f'shot_{i}_not_contiguous')
            previous = end if isinstance(end, (int, float)) else previous
            for field in ('visual', 'audio', 'caption'):
                if not isinstance(shot.get(field), str):
                    issues.append(f'shot_{i}_missing_{field}')
    if not isinstance(result.get('fact_basis'), list):
        issues.append('missing_fact_basis')
    if not isinstance(result.get('unresolved'), list):
        issues.append('missing_unresolved')
    return {'complete': not issues, 'issues': sorted(set(issues))}


def audit(root: Path):
    rows, errors = [], []
    for run in sorted(root.glob('paper-*')):
        summary_path = run / 'summary.json'
        if not run.is_dir() or not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text())
            for path in sorted(run.glob('*-plan-observation.json')):
                event_path = run / path.name.replace('-observation.json', '-event.json')
                if not event_path.exists():
                    errors.append({'run': run.name, 'file': path.name, 'error': 'missing_event'}); continue
                event = json.loads(event_path.read_text())
                if event.get('state') != 'completed':
                    continue
                result = inspect_plan(path)
                rows.append({'run': run.name, 'file': path.name,
                             'condition': event.get('condition'), **result,
                             'training_eligible': False})
        except Exception as exc:
            errors.append({'run': run.name, 'error': type(exc).__name__})
    return {'schema': 'visualagent.plan-structure-audit.v1',
            'plan_count': len(rows), 'structurally_complete': sum(r['complete'] for r in rows),
            'incomplete': sum(not r['complete'] for r in rows),
            'training_eligible': False, 'errors': errors, 'rows': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('/var/lib/visualstation-local/creative/learning'))
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); result = audit(args.root)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('plan_count','structurally_complete','incomplete','errors')}, ensure_ascii=False))
