#!/usr/bin/env python3
"""Associate bounded references with verified existing local award videos."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.tools.reference_media_reuse import MAX_REUSES, reuse_cached_media

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, choices=range(1, MAX_REUSES + 1), default=MAX_REUSES)
    args = parser.parse_args()
    result = reuse_cached_media(args.limit)
    print(json.dumps(result), flush=True)
    # An unusable duplicate stays available for the ordinary download queue;
    # the bounded partial receipt remains visible without failing good caches.
    sys.exit(1 if result['state'] == 'failed' else 0)
