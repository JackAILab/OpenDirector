#!/usr/bin/env python3
"""Build a non-overwriting, offline research manifest. Makes no model calls."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import build_manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--briefs', type=Path, default=Path(__file__).resolve().parents[1] / 'data/research/advertising_briefs_v1.json')
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    manifest = build_manifest(json.loads(args.briefs.read_text()))
    with args.out.open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: manifest[k] for k in ('state','task_count','family_count','execution_ready','paid_calls')}))


if __name__ == '__main__':
    main()
