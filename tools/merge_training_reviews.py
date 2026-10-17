#!/usr/bin/env python3
"""Collect exact candidate review receipts into a non-overwriting private bundle."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.learning.candidate_review import queue_digest, validate_receipt_shape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--receipts-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.queue.is_symlink() or not args.queue.is_file():
        raise ValueError('Invalid candidate queue')
    if args.receipts_dir.is_symlink() or not args.receipts_dir.is_dir():
        raise ValueError('Invalid receipts directory')
    queue = json.loads(args.queue.read_text(encoding='utf-8'))
    if queue.get('schema') != 'visualagent.training-candidate-queue.v1':
        raise ValueError('Unsupported candidate queue')
    receipts = []
    seen = set()
    for path in sorted(args.receipts_dir.glob('*.json')):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid receipt file')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        candidate = validate_receipt_shape(queue, receipt)
        candidate_sha = candidate['record_sha256']
        if candidate_sha in seen:
            raise ValueError('Duplicate candidate review receipt')
        seen.add(candidate_sha)
        receipts.append(receipt)
    if not receipts:
        raise ValueError('No candidate review receipts found')
    payload = {
        'schema': 'visualagent.training-candidate-review-bundle.v1',
        'queue_sha256': queue_digest(queue),
        'record_count': len(receipts),
        'training_eligible': False,
        'content_exported': False,
        'receipts': receipts,
    }
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError('Refusing to overwrite review bundle')
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(payload, out, ensure_ascii=False, indent=2)
        out.write('\n')
    print(json.dumps({'record_count': len(receipts), 'training_eligible': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
