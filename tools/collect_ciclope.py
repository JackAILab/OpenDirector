#!/usr/bin/env python3
"""Collect bounded CICLOPE advertising and craft winner metadata."""
import argparse
from contextlib import ExitStack
import fcntl, json, os, secrets, sys, time
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import ciclope
from harness.tools.award_archive import MAX_BATCHES, collect_archive, collect_archive_batches

SOURCE = 'CICLOPE Festival official advertising winners'
MAX_BYTES = 4 * 1024 * 1024
REQUEST_DELAY = 10

def _year(year):
    if year is None:
        return ciclope.YEARS[int(time.time() // (3 * 3600)) % len(ciclope.YEARS)]
    if type(year) is not int or year not in ciclope.YEARS:
        raise ValueError('invalid_ciclope_year')
    return year

def run(year=None, offset=None, batches=1):
    target_year = _year(year)
    if batches == 1:
        return collect_archive(ciclope, SOURCE, 'ciclope', target_year, offset, REQUEST_DELAY)
    return collect_archive_batches(
        ciclope, SOURCE, 'ciclope', target_year, max_batches=batches,
        offset=offset, request_delay=REQUEST_DELAY)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=ciclope.YEARS)
    parser.add_argument('--offset', type=int)
    parser.add_argument('--batches', type=int, default=1,
                        help=f'Maximum batches (1–{MAX_BATCHES}); stop at year end or first incomplete batch')
    args = parser.parse_args(argv)
    if not 1 <= args.batches <= MAX_BATCHES:
        parser.error(f'--batches must be 1–{MAX_BATCHES}')
    if args.batches > 1 and args.year is None:
        parser.error('--batches requires an explicit --year')
    if args.batches == 1:
        result = run(args.year, args.offset, args.batches)
        code = 1 if result['state'] == 'failed' else 0
    else:
        result = collect_archive_batches(
            ciclope, SOURCE, 'ciclope', args.year, max_batches=args.batches,
            offset=args.offset, request_delay=REQUEST_DELAY,
            on_batch=lambda batch: print(json.dumps({'batch': batch}, ensure_ascii=False), flush=True))
        code = 1 if result['state'] in ('failed', 'partial') else 0
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
