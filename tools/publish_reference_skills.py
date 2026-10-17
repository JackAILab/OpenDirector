#!/usr/bin/env python3
"""Publish a versioned set of real-video reference skills into the creative studio."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.studio import store as studio
from harness.tools.reference_skill_publish import candidates, select, publish, restore_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--minimum-sources', type=int, default=3)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--restore-release', help='Restore one explicit release from the library database')
    parser.add_argument('--database', type=Path, help='Verified database snapshot to restore from')
    args = parser.parse_args()
    if args.restore_release:
        if args.publish:
            parser.error('Choose publication or restoration')
        print(json.dumps(restore_release(args.restore_release, studio.DATA/'reference_skills', args.database)))
        return
    if args.database:
        parser.error('--database requires --restore-release')
    if not 1 <= args.limit <= 500 or not 1 <= args.minimum_sources <= args.limit:
        parser.error('Invalid publication bounds')
    pool = candidates()
    chosen = select(pool, args.limit, args.minimum_sources)
    print(json.dumps({'state': 'selected', 'eligible_pool': len(pool), 'selected': len(chosen),
                      'sources': dict(Counter(x['recipe']['reference_case']['source_name'] for x in chosen)),
                      'categories': dict(Counter(x['recipe']['category'] for x in chosen))}, ensure_ascii=False), flush=True)
    if args.publish:
        result = publish(chosen, studio.DATA/'reference_skills',
                         lambda event: print(json.dumps(event), flush=True))
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
