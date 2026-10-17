#!/usr/bin/env python3
"""Apply an explicit, deterministic repair to one failed analysis candidate.

This tool never calls a provider and never retries a model request.  It only
normalizes a zero-length sampled beat that the schema can safely expand to the
next observed frame; the original failed receipt remains in history.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import learning, store


def repair(identity):
    if not re.fullmatch(r'[a-f0-9]{24}', identity):
        raise ValueError('invalid_item')
    with store.connection() as c:
        item = c.execute('SELECT id,revision FROM items WHERE id=?', (identity,)).fetchone()
        asset = c.execute('SELECT sha256,duration FROM assets WHERE item=?', (identity,)).fetchone()
    if not item or not asset:
        raise ValueError('item_or_asset_missing')
    evidence_dir = (store.ROOT / 'learning' / 'evidence' / identity).resolve()
    evidence_root = (store.ROOT / 'learning' / 'evidence').resolve()
    if not evidence_dir.is_relative_to(evidence_root) or evidence_dir.is_symlink():
        raise ValueError('invalid_evidence_path')
    candidate_path = evidence_dir / 'candidate.json'
    attempt_path = evidence_dir / 'analysis-attempt.json'
    evidence_path = evidence_dir / 'evidence.json'
    if not candidate_path.is_file() or not attempt_path.is_file() or not evidence_path.is_file():
        raise ValueError('repair_inputs_missing')
    attempt = json.loads(attempt_path.read_text())
    if attempt.get('state') != 'failed' or attempt.get('error_code') != 'ValueError':
        raise ValueError('repair_requires_failed_validation')
    with learning.connection() as c:
        if c.execute('SELECT 1 FROM analyses WHERE item=? AND media_sha256=?',
                     (identity, asset['sha256'])).fetchone():
            raise ValueError('analysis_already_saved')
    evidence = json.loads(evidence_path.read_text())
    frame_times = [f['time'] for f in evidence.get('frames', [])]
    candidate = json.loads(candidate_path.read_text())
    clean = learning.validate(candidate, asset['duration'], frame_times)
    repairs = clean.get('validation_repairs') or []
    if not repairs:
        raise ValueError('no_deterministic_repair')
    history = evidence_dir / 'analysis-attempt-history.jsonl'
    with history.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(dict(attempt, repaired_at=time.time()), ensure_ascii=False) + '\n')
    repaired_path = evidence_dir / 'candidate-repaired.json'
    repaired_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2))
    version = learning.save_analysis(identity, asset['sha256'], item['revision'],
                                     'cb-gpt-5.6-sol', clean, frame_times)
    attempt_path.write_text(json.dumps({'state': 'completed', 'version': version,
                                        'automatic_retry': False,
                                        'repair': 'deterministic_zero_length_beat'},
                                       ensure_ascii=False))
    (evidence_dir / 'analysis-repair.json').write_text(json.dumps({
        'schema': 'visualagent.ad-analysis-repair.v1',
        'item': identity,
        'media_sha256': asset['sha256'],
        'analysis_version': version,
        'reason': 'zero_length_sampled_beat',
        'repairs': repairs,
        'provider_called': False,
        'automatic_retry': False,
        'training_eligible': False,
    }, ensure_ascii=False, indent=2))
    return {'item': identity, 'state': 'completed', 'version': version,
            'repairs': repairs, 'provider_called': False, 'training_eligible': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--item', required=True)
    parser.add_argument('--confirm-repair', action='store_true',
                        help='explicitly authorize the deterministic local repair')
    args = parser.parse_args()
    if not args.confirm_repair:
        raise SystemExit('refusing repair without --confirm-repair')
    try:
        print(json.dumps(repair(args.item), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'state': 'failed', 'error_code': type(exc).__name__,
                          'provider_called': False, 'training_eligible': False},
                         ensure_ascii=False))
        raise SystemExit(1)
