#!/usr/bin/env python3
"""Materialize the explainable mechanism dimensions from an aggregate."""
import argparse, json, os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library.mechanism_report import build_mechanism_report

parser = argparse.ArgumentParser()
parser.add_argument('--aggregate', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists() or args.output.is_symlink():
    raise FileExistsError('Refusing to overwrite mechanism report')
payload = build_mechanism_report(json.loads(args.aggregate.read_text(encoding='utf-8')))
args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
print(json.dumps({'analysis_count': payload['analysis_count'], 'training_eligible': False}, ensure_ascii=False))
