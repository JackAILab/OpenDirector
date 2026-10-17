#!/usr/bin/env python3
"""Collect the new official Kyoorius 2026 Film gallery in bounded batches."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.models.reference_sources import kyoorius_current
from harness.tools.award_archive import MAX_BATCHES, collect_archive, collect_archive_batches

SOURCE = 'Kyoorius Creative Awards 2026 official film gallery'


def run(offset=None, batches=1, on_batch=None):
    if type(batches) is not int or not 1 <= batches <= MAX_BATCHES:
        raise ValueError('invalid_archive_batch_limit')
    if batches == 1:
        return collect_archive(kyoorius_current, SOURCE, 'kyoorius:current', 2026, offset, 10)
    return collect_archive_batches(kyoorius_current, SOURCE, 'kyoorius:current', 2026,
        max_batches=batches, offset=offset, request_delay=10, on_batch=on_batch)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offset', type=int)
    parser.add_argument('--batches', type=int, choices=range(1, MAX_BATCHES + 1), default=1)
    args = parser.parse_args(argv)
    result = run(args.offset, args.batches,
                 lambda batch: print(json.dumps({'batch': batch}, ensure_ascii=False), flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result['state'] in ('failed', 'partial') else 0


if __name__ == '__main__':
    sys.exit(main())
