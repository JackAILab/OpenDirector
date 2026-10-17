#!/usr/bin/env python3
"""Bounded Webby advertising winner discovery; no media downloads."""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import time

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import webby

SOURCE = 'Webby official advertising video winners'
MAX_BYTES = 2 * 1024 * 1024
SAFE_ERRORS = {'source_layout_changed', 'source_page_too_large', 'robots_unavailable', 'robots_disallowed'}


def _json(response):
    if len(response.content) > MAX_BYTES:
        raise ValueError('source_page_too_large')
    return response.json()


def _year(year):
    if year is None:
        # Rotate the three bounded award years across scheduled runs instead
        # of repeatedly querying the current year only.
        return webby.YEARS[int(time.time() // (3 * 3600)) % len(webby.YEARS)]
    if type(year) is not int or year not in webby.YEARS:
        raise ValueError('invalid_webby_year')
    return year


def run(year=None, page=1):
    year = _year(year)
    payload = webby.listing_payload(year, page)
    root = store.ROOT
    root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((root / '.backup.lock').open('a'))
        collector = locks.enter_context((root / '.collector.lock').open('a'))
        try:
            if backup:
                fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0, 'year': year, 'page': page}
        identity, records, inserted = secrets.token_hex(12), [], 0
        with store.connection() as c:
            c.execute("UPDATE collection_runs SET state='interrupted',finished=?,error_code='worker_restarted' WHERE source=? AND state='running'", (time.time(), SOURCE))
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)', (identity, SOURCE, time.time(), 'running'))
        try:
            with httpx.Client(timeout=30, follow_redirects=False,
                              headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0', 'Accept': 'application/json'}) as client:
                response = client.post(webby.API_ORIGIN + '/search/search', json=payload)
                response.raise_for_status()
                listing = _json(response)
                candidates = webby.parse_listing(listing, year, page)
                for candidate in candidates:
                    detail_response = client.get(webby.API_ORIGIN + '/entry/GetGalleryPiece/' + str(candidate['item_id']))
                    detail_response.raise_for_status()
                    records.append(webby.enrich(candidate, _json(detail_response)))
            for record in records:
                _, added = store.ingest(record)
                inserted += int(added)
            state, error = 'completed', ''
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            state, error = 'failed', 'source_unavailable'
            current = sys.exception()
            if str(current) in SAFE_ERRORS:
                error = str(current)
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                      (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'year': year, 'page': page,
                'discovered': len(records), 'inserted': inserted, 'error_code': error}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=webby.YEARS, help='指定年份；省略时按三年轮换')
    parser.add_argument('--page', type=int, choices=range(1, 21), default=1)
    args = parser.parse_args()
    result = run(args.year, args.page)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
