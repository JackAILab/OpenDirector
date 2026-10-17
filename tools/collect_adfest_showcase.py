#!/usr/bin/env python3
"""Collect public ADFEST 2026 film metadata in bounded page batches."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import adfest_showcase as source
from harness.tools.adfest_showcase import collect


def run(category=None, page=None, batches=1, on_batch=None):
    if type(batches) is not int or not 1 <= batches <= 12:
        raise ValueError('invalid_adfest_batch_limit')
    if category is None:
        if page is not None or batches > 1:
            raise ValueError('adfest_category_required')
        category = tuple(source.CATEGORIES)[int(time.time() // (3 * 3600)) % len(source.CATEGORIES)]
    source.listing_url(category, 1 if page is None else page)
    if batches == 1:
        return collect(category, page)
    result = {'state': 'completed', 'category': category, 'batches': 0,
              'discovered': 0, 'inserted': 0, 'stop_reason': 'batch_limit'}
    for number in range(batches):
        batch = collect(category, page if number == 0 else None)
        result['batches'] += 1
        result['discovered'] += batch.get('discovered', 0)
        result['inserted'] += batch.get('inserted', 0)
        result['last_batch'] = batch
        if on_batch:
            on_batch(batch)
        if batch['state'] != 'completed':
            result.update(state=batch['state'], stop_reason=batch['state'], error_code=batch.get('error_code', ''))
            break
        if batch.get('category_scan_complete'):
            result['stop_reason'] = 'category_scan_complete'
            break
        if number and batch.get('cursor_reset'):
            result.update(state='partial', stop_reason='listing_changed')
            break
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--category', type=int, choices=source.CATEGORIES)
    parser.add_argument('--page', type=int, choices=range(1, source.MAX_PAGES + 1))
    parser.add_argument('--batches', type=int, choices=range(1, 13), default=1)
    args = parser.parse_args(argv)
    if args.category is None and (args.page is not None or args.batches > 1):
        parser.error('--page and --batches require --category')
    result = run(args.category, args.page, args.batches,
        lambda r: print(json.dumps({'batch': r}, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
