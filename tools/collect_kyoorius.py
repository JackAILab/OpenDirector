#!/usr/bin/env python3
"""Collect bounded Kyoorius film metadata with a durable listing cursor."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import kyoorius
from harness.tools.award_archive import MAX_BATCHES, collect_archive, collect_archive_batches

SOURCE = 'Kyoorius Creative Awards official film winners'
REQUEST_DELAY = 10


def run(paths=None, offset=None, batches=1, on_batch=None):
    paths = tuple((kyoorius.LISTING_PATHS[0],) if paths is None else paths)
    if (not paths or len(set(paths)) != len(paths)
            or any(path not in kyoorius.LISTING_PATHS for path in paths)):
        raise ValueError('invalid_kyoorius_selection')
    if type(batches) is not int or not 1 <= batches <= MAX_BATCHES:
        raise ValueError('invalid_archive_batch_limit')
    if len(paths) > 1 and (offset is not None or batches > 1):
        raise ValueError('kyoorius_burst_requires_one_listing')
    results = []
    for path in paths:
        adapter = kyoorius.ArchiveListing(path)
        if batches == 1:
            result = collect_archive(adapter, SOURCE, adapter.cursor_key, 2025,
                                     offset, REQUEST_DELAY)
        else:
            result = collect_archive_batches(
                adapter, SOURCE, adapter.cursor_key, 2025, max_batches=batches,
                offset=offset, request_delay=REQUEST_DELAY,
                on_batch=(lambda batch: on_batch({'path': path, **batch})) if on_batch else None)
        results.append({'path': path, **result})
        if result['state'] == 'already_running':
            break
    if len(results) == 1:
        return results[0]
    discovered = sum(result.get('discovered', 0) for result in results)
    incomplete = [result for result in results if result['state'] != 'completed']
    state = ('partial' if discovered else 'failed') if incomplete else 'completed'
    return {'state': state, 'discovered': discovered,
            'inserted': sum(result.get('inserted', 0) for result in results),
            'results': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', action='append', choices=kyoorius.LISTING_PATHS,
                        help='默认从年度目录续采；可指定 Advertising 或 Craft 分区')
    parser.add_argument('--offset', type=int)
    parser.add_argument('--batches', type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.batches <= MAX_BATCHES:
        parser.error(f'--batches must be 1–{MAX_BATCHES}')
    if args.path and len(args.path) > 1 and (args.batches > 1 or args.offset is not None):
        parser.error('--batches / --offset require one listing')
    result = run(args.path, args.offset, args.batches,
                 on_batch=lambda batch: print(json.dumps({'batch': batch}, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
