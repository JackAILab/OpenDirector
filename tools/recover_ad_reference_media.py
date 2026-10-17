#!/usr/bin/env python3
"""Explicitly recover one already downloaded reference after database failure."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.tools.reference_media_recovery import recover_cached_media
from tools.cache_ad_reference_media import library_budget, _item_identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--item', required=True, type=_item_identity)
    args = parser.parse_args(argv)
    result = recover_cached_media(args.item, budget=library_budget())
    print(json.dumps(result))
    return 1 if result['state'] in ('failed', 'storage_limit') else 0


if __name__ == '__main__':
    sys.exit(main())
