#!/usr/bin/env python3
"""Read-only aggregate research inventory. No media, private text or model calls."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def read_db(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    connection.execute('PRAGMA query_only=ON')
    return connection


def audit(library_root, report_dir):
    with read_db(library_root / 'library.sqlite3') as c:
        c.execute('BEGIN')
        sources = c.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        assets = dict(c.execute('SELECT item,sha256 FROM assets'))
    with read_db(library_root / 'learning' / 'analyses.sqlite3') as c:
        c.execute('BEGIN')
        rows = c.execute('SELECT item,media_sha256,version,data FROM analyses ORDER BY item,version DESC').fetchall()
    selected = {}; invalid = 0
    for item, sha, version, text in rows:
        if item in selected or assets.get(item) != sha:
            continue
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, TypeError):
            invalid += 1
            # Do not substitute an older successful version for a malformed latest row.
            selected[item] = None
            continue
        selected[item] = data
    current = [d for d in selected.values() if d is not None]
    report = {
        'schema': 'visualagent.paper-readiness.v1',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'inventory': {
            'source_records': sources,
            'asset_records': len(assets),
            'distinct_asset_sha256': len(set(assets.values())),
            'extra_records_sharing_sha256': len(assets) - len(set(assets.values())),
            'analysis_versions': len(rows),
            'current_media_analysis_records': len(current),
            'current_media_unique_analyzed_sha256': len({assets[k] for k,v in selected.items() if v is not None}),
            'invalid_latest_records': invalid,
            'roles': dict(collections.Counter(d.get('media_role','unknown') for d in current)),
            'audio_semantics_reviewed': sum(d.get('audio_semantics_reviewed') is True for d in current),
            'full_motion_reviewed': sum(d.get('full_motion_reviewed') is True for d in current),
        },
        'historical_user_preparation': None,
        'comparison_experiment_completed': False,
        'training_eligibility_inferred': False,
        'limitations': [
            'Cross-database reads are sequential snapshots, not one atomic snapshot.',
            'Digest deduplication does not remove re-encodes, alternate edits or campaign families.',
            'Review flags are stored evidence state, not an independent re-review.',
            'Counts and format validity do not measure advertising effectiveness.'
        ],
    }
    snapshots = list(report_dir.glob('private-dataset-preparation-*.json'))
    if snapshots:
        newest = max(snapshots, key=lambda p:p.stat().st_mtime)
        raw = newest.read_bytes(); data = json.loads(raw)
        summary = data.get('summary', {})
        safe = {key:summary[key] for key in ('projects','versions','families','actual_artifacts','training_eligible','release_ready') if key in summary}
        report['historical_user_preparation'] = {
            'snapshot': newest.name,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'summary': safe,
            'scope': 'Historical preparation snapshot; not a live user-database audit.'
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library-root', type=Path)
    parser.add_argument('--report-dir', type=Path, default=Path('/var/lib/visualstation-local/creative/learning'))
    parser.add_argument('--out', type=Path, help='Optional new file; refuses to overwrite.')
    args = parser.parse_args()
    if args.library_root is None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from harness.library.store import ROOT
        args.library_root = ROOT
    result = audit(args.library_root, args.report_dir)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.out:
        with args.out.open('x') as stream:
            stream.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
