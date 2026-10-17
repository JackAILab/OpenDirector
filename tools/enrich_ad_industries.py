#!/usr/bin/env python3
"""Map official industry categories for browsing; default to a read-only preview."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.tools.reference_industries import enrich_industries

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-records', type=int, default=10000)
    args = parser.parse_args()
    report = lambda value: print(json.dumps(value, ensure_ascii=False), flush=True)
    report(enrich_industries(apply=args.apply, max_records=args.max_records, progress=report))
