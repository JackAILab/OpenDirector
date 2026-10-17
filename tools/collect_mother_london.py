#!/usr/bin/env python3
"""Collect bounded official campaign references; never download or generate media."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import mother_london
from harness.tools.award_archive import collect_archive

SOURCE = 'Mother London official campaign portfolio'
REQUEST_DELAY = 10


def run(year=None, offset=None):
    year = mother_london.YEARS[int(time.time() // (3 * 3600)) % len(mother_london.YEARS)] if year is None else year
    return collect_archive(mother_london, SOURCE, 'mother_london', year, offset, REQUEST_DELAY)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=mother_london.YEARS)
    parser.add_argument('--offset', type=int)
    args = parser.parse_args(argv)
    result = run(args.year, args.offset)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
