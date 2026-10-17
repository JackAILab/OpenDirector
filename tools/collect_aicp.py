#!/usr/bin/env python3
"""Collect stable AICP shortlist metadata without persisting signed media URLs."""
import fcntl, json, os, secrets, sqlite3, sys, time
from contextlib import ExitStack
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import aicp

# Public shortlist categories covering the AICP Show and craft categories.
# Keep the IDs explicit so a layout change cannot silently widen collection.
CATEGORIES = (20, 21, 5, 38, 15, 4, 14, 7, 28, 6, 3, 11, 35, 9, 2, 12, 13, 16, 10, 19, 8, 1)
NEXT_CATEGORIES = (27, 98, 99, 96, 26, 24, 37, 34, 23, 100, 30, 31, 25)


def run():
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((store.ROOT/'.backup.lock').open('a'))
        collector = locks.enter_context((store.ROOT/'.collector.lock').open('a'))
        try:
            if backup: fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {'state': 'already_running', 'discovered': 0, 'inserted': 0}
        identity = secrets.token_hex(12); started = time.time(); records = []; inserted = 0
        with store.connection() as c: c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)', (identity, 'AICP official shortlist', started, 'running'))
        state, error = 'failed', 'collector_error'
        try:
            robots = RobotFileParser(); response = httpx.get(aicp.ORIGIN + '/robots.txt', timeout=20, follow_redirects=True, headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'})
            if response.status_code == 200: robots.parse(response.text.splitlines())
            seen = set()
            with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'}) as client:
                for award_type, category_ids in (('aicp', CATEGORIES), ('next', NEXT_CATEGORIES)):
                  for category in category_ids:
                    url = aicp.ORIGIN + f'/shortlist/list.php?catID={category}&type={award_type}'
                    if response.status_code == 200 and not robots.can_fetch('VisualAgent-ReferenceCollector', url): raise ValueError('robots_disallowed')
                    page = client.get(url); page.raise_for_status()
                    for record in aicp.parse_shortlist(page.text, category, award_type=award_type):
                        key = record['source_url'].split('&entry=')[-1]
                        if key not in seen: records.append(record); seen.add(key)
            for record in records: _, new = store.ingest(record); inserted += int(new)
            state, error = 'completed', ''
        except (httpx.HTTPError, ValueError, KeyError): state, error = 'failed', 'source_unavailable'
        except sqlite3.Error: state, error = 'failed', 'database_unavailable'
        except Exception: state, error = 'failed', 'collector_error'
        # Persist failure if the database is writable again. If even this
        # update fails, the runner continues later sources and reconciles
        # the receipt only after acquiring the worker locks next time.
        with store.connection() as c: c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?', (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'discovered': len(records), 'inserted': inserted, 'error_code': error}


if __name__ == '__main__': print(json.dumps(run(), ensure_ascii=False))
