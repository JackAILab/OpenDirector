#!/usr/bin/env python3
"""Collect bounded Berlin Commercial official advertising winners with durable annual cursors."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import berlin_commercial
from harness.tools.award_archive import MAX_BATCHES, collect_archive, collect_archive_batches

SOURCE = 'Berlin Commercial official advertising winners'
REQUEST_DELAY = 10


def _year(year):
    if year is None:
        return berlin_commercial.YEARS[int(time.time() // (3 * 3600)) % len(berlin_commercial.YEARS)]
    if type(year) is not int or year not in berlin_commercial.YEARS:
        raise ValueError('invalid_berlin_commercial_year')
    return year


def run(year=None, offset=None, batches=1, on_batch=None):
    target_year = _year(year)
    if batches == 1:
        return collect_archive(berlin_commercial, SOURCE, 'berlin_commercial', target_year, offset, REQUEST_DELAY)
    return collect_archive_batches(
        berlin_commercial, SOURCE, 'berlin_commercial', target_year, max_batches=batches,
        offset=offset, request_delay=REQUEST_DELAY, on_batch=on_batch)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=berlin_commercial.YEARS)
    parser.add_argument('--offset', type=int)
    parser.add_argument('--batches', type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.batches <= MAX_BATCHES:
        parser.error(f'--batches must be 1–{MAX_BATCHES}')
    if args.batches > 1 and args.year is None:
        parser.error('--batches requires an explicit --year')
    result = run(args.year, args.offset, args.batches,
                 on_batch=lambda batch: print(json.dumps({'batch': batch}, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
