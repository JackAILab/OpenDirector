#!/usr/bin/env python3
"""Correct finalist/shortlist labels using already collected official evidence."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.tools.award_evidence import repair_award_evidence

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    report = lambda value: print(json.dumps(value), flush=True)
    report(repair_award_evidence(apply=args.apply, progress=report))
