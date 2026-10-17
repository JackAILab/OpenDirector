#!/usr/bin/env python3
"""Collect bounded metadata from official Cannes Lions winner spotlights."""
import argparse
import fcntl
import json
import os
import secrets
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import cannes_lions


def run(pages=None, year=2025):
    selected_pages = tuple(cannes_lions.PAGES if pages is None else pages)
    if not selected_pages or any(not isinstance(page, str) or not page.startswith(cannes_lions.ORIGIN + '/') for page in selected_pages):
        raise ValueError('invalid_cannes_lions_selection')
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError('invalid_cannes_lions_year')
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((store.ROOT / '.backup.lock').open('a'))
        collector = locks.enter_context((store.ROOT / '.collector.lock').open('a'))
        try:
            if backup:
                fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0}
        identity, started, inserted = secrets.token_hex(12), time.time(), 0
        with store.connection() as c:
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                      (identity, 'Cannes Lions Winner Spotlight', started, 'running'))
        records, failures = [], []
        try:
            with httpx.Client(timeout=35, follow_redirects=True,
                              headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'}) as client:
                robots_response = client.get(cannes_lions.ORIGIN + '/robots.txt')
                if robots_response.status_code not in (200, 404):
                    raise ValueError('robots_unavailable')
                policy = RobotFileParser()
                policy.parse(robots_response.text.splitlines() if robots_response.status_code == 200 else [])
                for page in selected_pages:
                    if robots_response.status_code == 200 and not policy.can_fetch('VisualAgent-ReferenceCollector', page):
                        failures.append('robots_disallowed')
                        continue
                    try:
                        response = client.get(page)
                        response.raise_for_status()
                        records.extend(cannes_lions.parse_page(response.text, page, year=year))
                    except (httpx.HTTPError, ValueError, KeyError):
                        failures.append('page_fetch_or_parse_failed')
            records = list({record['source_url']: record for record in records}.values())
            for record in records:
                _, new = store.ingest(record)
                inserted += int(new)
            state = 'partial' if failures and records else ('failed' if failures else 'completed')
            error = 'source_unavailable' if failures else ''
        except (httpx.HTTPError, ValueError, KeyError):
            state, error = 'failed', 'source_unavailable'
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                      (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'discovered': len(records), 'inserted': inserted, 'error_code': error}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2025)
    args = parser.parse_args()
    result = run(year=args.year)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
