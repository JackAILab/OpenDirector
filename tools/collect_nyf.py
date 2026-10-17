#!/usr/bin/env python3
"""Bounded, robots-aware NYF award metadata discovery; no media downloads."""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.robotparser import RobotFileParser

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import nyf

SOURCE = 'NYF official advertising winners'
MAX_PAGE_BYTES = 4 * 1024 * 1024
SAFE_ERRORS = {'robots_unavailable', 'robots_disallowed', 'source_layout_changed',
               'source_page_too_large'}


def _year(year):
    if year is None:
        years=sorted(nyf.ARCHIVES, reverse=True)
        return years[int(time.time() // (3 * 3600)) % len(years)]
    if type(year) is not int or year not in nyf.ARCHIVES:
        raise ValueError('invalid_nyf_year')
    return year


def run(year=None):
    year = _year(year)
    url = nyf.listing_url(year)
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
        identity, records, inserted = secrets.token_hex(12), [], 0
        with store.connection() as c:
            c.execute("UPDATE collection_runs SET state='interrupted',finished=?,error_code='worker_restarted' WHERE source=? AND state='running'", (time.time(), SOURCE))
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                      (identity, SOURCE, time.time(), 'running'))
        try:
            with httpx.Client(timeout=30, follow_redirects=False,
                              headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'}) as client:
                robots = client.get(nyf.ORIGIN + '/robots.txt')
                if robots.status_code not in (200, 404):
                    raise ValueError('robots_unavailable')
                policy = RobotFileParser()
                policy.parse(robots.text.splitlines() if robots.status_code == 200 else [])
                if robots.status_code == 200 and not policy.can_fetch('VisualAgent-ReferenceCollector', url):
                    raise ValueError('robots_disallowed')
                with client.stream('GET', url) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_PAGE_BYTES:
                            raise ValueError('source_page_too_large')
                    records = nyf.parse_listing(raw.decode('utf-8'), year)
            for record in records:
                _, added = store.ingest(record)
                inserted += int(added)
            state, error = 'completed', ''
        except (httpx.HTTPError, ValueError, KeyError):
            state, error = 'failed', 'source_unavailable'
            current = sys.exception()
            if str(current) in SAFE_ERRORS:
                error = str(current)
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                      (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'discovered': len(records),
                'inserted': inserted, 'error_code': error}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=sorted(nyf.ARCHIVES), help='指定年份；省略时按年份轮换')
    result = run(parser.parse_args().year)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
