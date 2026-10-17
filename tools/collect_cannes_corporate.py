#!/usr/bin/env python3
"""Collect bounded Cannes Corporate marketing/product films from full categories."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import cannes_corporate as source
from harness.tools.award_archive import collect_archive, collect_archive_batches, MAX_BATCHES

SOURCE = 'Cannes Corporate official marketing and product films'
REQUEST_DELAY = 2


def run(year=None, category=None, batches=1, on_batch=None):
    choices = [(y, c) for c in source.CATEGORIES for y in source.YEARS]
    selected_year, selected_category = choices[int(time.time() // (3 * 3600)) % len(choices)]
    year = selected_year if year is None else year
    category = selected_category if category is None else category
    adapter = source.archive_adapter(category)
    adapter.listing_url(year)
    key = f'cannes_corporate:{category}'
    if batches == 1:
        return collect_archive(adapter, SOURCE, key, year, None, REQUEST_DELAY)
    return collect_archive_batches(adapter, SOURCE, key, year, max_batches=batches,
                                   request_delay=REQUEST_DELAY, on_batch=on_batch)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=source.YEARS)
    parser.add_argument('--category', type=int, choices=source.CATEGORIES,
                        help='4: product/launch films; 1: marketing communication')
    parser.add_argument('--batches', type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.batches <= MAX_BATCHES:
        parser.error(f'--batches must be 1–{MAX_BATCHES}')
    if args.batches > 1 and (args.year is None or args.category is None):
        parser.error('--batches requires --year and --category')
    result = run(args.year, args.category, args.batches,
                 lambda batch: print(json.dumps({'batch': batch}, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
