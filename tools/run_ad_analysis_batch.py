#!/usr/bin/env python3
"""Run one bounded, non-retrying batch of missing reference analyses.

The batch is deliberately limited to structure analysis. It never generates
video, marks a record training-eligible, or changes model parameters after a
failure.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path('/var/lib/visualstation-local/creative/learning')
LOCK = ROOT / 'ad-analysis-batch.lock'
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def select_unattempted_ids(rows, evidence_root, limit, *, now, stale_after=600,
                           excluded_ids=(), analyzed_media=()):
    """Do not let protected attempts consume every scheduled batch slot.

    Failed, completed and unreadable receipts stay untouched. Only a stale
    interrupted attempt has the same resume policy as analyze_ad_library.
    Prefer unseen videos over another source's copy of an analyzed film, and
    select each video at most once per batch. Other source records stay in the
    operator queue; this does not reuse or invent their analysis evidence.
    """
    selected = []
    skipped = 0
    seen_media = set()
    analyzed_media = set(analyzed_media)
    for row in sorted(rows, key=lambda r: r.get('media_sha256') in analyzed_media):
        if row['item'] in excluded_ids or 'analysis' not in row.get('missing', []):
            continue
        digest = row.get('media_sha256')
        if digest and digest in seen_media:
            continue
        attempt = evidence_root / row['item'] / 'analysis-attempt.json'
        try:
            receipt = json.loads(attempt.read_text())
        except FileNotFoundError:
            receipt = None
        except (OSError, ValueError):
            skipped += 1
            continue
        if receipt is not None:
            try:
                resumable = (receipt.get('state') == 'started' and
                             now - float(receipt.get('started_at', 0) or 0) >= stale_after)
            except (AttributeError, TypeError, ValueError):
                resumable = False
            if not resumable:
                skipped += 1
                continue
        selected.append(row['item'])
        if digest:
            seen_media.add(digest)
        if len(selected) == limit:
            break
    return selected, skipped


def choose_ids(limit):
    from harness.library.learning import analysis_review_queue
    from harness.library import store
    from harness.library.browse_groups import is_explicit_non_ad
    payload = analysis_review_queue(5000)
    if payload.get('state') != 'ready':
        raise RuntimeError('analysis_queue_unavailable')
    # Read only the covering source-category index, not thousands of private
    # payloads. The operator review queue remains complete and unchanged.
    with closing(sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',
                                 uri=True, timeout=2)) as db:
        excluded = {item for item, category in db.execute(
            'SELECT id,ad_type FROM items INDEXED BY item_type_recent') if is_explicit_non_ad(category)}
        current = dict(db.execute('SELECT item,sha256 FROM assets'))
    # Covering keys only: a replaced source file must not make its old digest
    # appear currently analyzed. No model payloads or review notes are read.
    with closing(sqlite3.connect(f'file:{store.ROOT / "learning" / "analyses.sqlite3"}?mode=ro',
                                 uri=True, timeout=2)) as db:
        analyzed = {digest for item, digest in db.execute('SELECT item,media_sha256 FROM analyses')
                    if current.get(item) == digest}
    return select_unattempted_ids(payload.get('items', []), store.ROOT / 'learning/evidence',
                                  limit, now=time.time(), excluded_ids=excluded, analyzed_media=analyzed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=24)
    ap.add_argument('--startup-timeout', type=int, default=60)
    args = ap.parse_args()
    if not 1 <= args.limit <= 24:
        raise ValueError('limit must be 1-24')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'state': 'skipped', 'reason': 'batch_already_running'}, ensure_ascii=False))
            return
        ids, skipped = choose_ids(args.limit)
        print(json.dumps({'state': 'selection', 'selected': len(ids),
                          'protected_attempts_skipped': skipped, 'video_generation': False}), flush=True)
        if not ids:
            print(json.dumps({'state': 'idle', 'selected': 0, 'video_generation': False}, ensure_ascii=False))
            return
        selection = ROOT / 'ad-analysis-selection-current.json'
        selection.write_text(json.dumps([{'id': item} for item in ids]), encoding='utf-8')
        try:
            command = [sys.executable, 'tools/analyze_ad_library.py', '--limit', str(args.limit),
                       '--selection', str(selection), '--startup-timeout', str(args.startup_timeout),
                       '--resume-stale-started', '600']
            completed = subprocess.run(command, check=False, timeout=3600)
            if completed.returncode:
                raise SystemExit(completed.returncode)
        finally:
            selection.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
