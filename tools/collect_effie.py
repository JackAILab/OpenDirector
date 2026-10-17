#!/usr/bin/env python3
"""Collect one bounded page of Effie case-film metadata."""
import argparse
import fcntl
import json
import os
import secrets
import sys
import time
from contextlib import ExitStack
from urllib.robotparser import RobotFileParser
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import effie

SOURCE = 'Effie Worldwide official case archive'
USER_AGENT = 'VisualAgent-ReferenceCollector/1.0'


def _page_number(page):
    if page is None:
        # Rotate one bounded page per scheduled interval; after the last page,
        # the cursor wraps and normal ingest de-duplicates the source URL.
        return int(time.time() // (3 * 3600)) % effie.ARCHIVE_PAGES + 1
    if type(page) is not int or not 1 <= page <= effie.ARCHIVE_PAGES:
        raise ValueError('invalid_effie_page')
    return page


def run(page=None):
    page = _page_number(page)
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((store.ROOT / '.backup.lock').open('a'))
        collector = locks.enter_context((store.ROOT / '.collector.lock').open('a'))
        try:
            if backup:
                fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0, 'page': page}
        identity, started = secrets.token_hex(12), time.time()
        with store.connection() as c:
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                      (identity, f'{SOURCE} · page {page}', started, 'running'))
        records, failures = [], []
        state, error = 'completed', ''
        try:
            robots = RobotFileParser()
            with httpx.Client(timeout=30, follow_redirects=True,
                              headers={'User-Agent': USER_AGENT,
                                       'X-Requested-With': 'XMLHttpRequest'}) as client:
                robots_response = client.get(effie.ORIGIN + '/robots.txt')
                if (robots_response.status_code not in (200, 404)
                        or len(robots_response.content) > effie.MAX_PAGE_BYTES):
                    raise ValueError('robots_unavailable')
                if robots_response.status_code == 200:
                    robots.parse(robots_response.text.splitlines())
                    if not robots.can_fetch(USER_AGENT, effie.ORIGIN + '/cases/'):
                        raise ValueError('robots_disallowed')
                delay = max(1, robots.crawl_delay(USER_AGENT) or 0)

                def read(url):
                    if robots_response.status_code == 200 and not robots.can_fetch(USER_AGENT, url):
                        raise ValueError('robots_disallowed')
                    time.sleep(delay)
                    return effie.read_page(client, url)

                # Numbered HTML paths repeat the first page. The public UI
                # instead loads its ten-card grid via this anonymous action.
                cards = effie.parse_archive(read(effie.archive_url(page)))
                if not cards:
                    raise ValueError('source_layout_changed')
                # Keep the independent page-identity check after changing the
                # transport; a repeated AJAX response is still not progress.
                if page > 1:
                    first_cards = effie.parse_archive(read(effie.archive_url(1)))
                    if not first_cards:
                        raise ValueError('source_layout_changed')
                    if {r['source_url'] for r in cards} == {r['source_url'] for r in first_cards}:
                        cards = []
                        state, error = 'partial', 'page_repeated'
                for record in cards:
                    try:
                        media = effie.parse_detail(read(record['source_url']), record['source_url'])
                        if not media['has_video']:
                            continue
                        if media['embed_url']:
                            record['embed_url'] = media['embed_url']
                        if media['thumbnail_url']:
                            record['thumbnail_url'] = media['thumbnail_url']
                        record['creative_structure']['video_available'] = True
                        records.append(record)
                    except (httpx.HTTPError, ValueError):
                        failures.append(record['source_url'])
            inserted = sum(store.ingest(record)[1] for record in records)
            if failures and not records:
                state, error = 'failed', 'source_unavailable'
            elif failures:
                state, error = 'partial', 'detail_unavailable'
        except (httpx.HTTPError, ValueError):
            state, error, inserted = 'failed', 'source_unavailable', 0
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                      (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'page': page, 'discovered': len(records),
                'inserted': inserted, 'error_code': error}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page', type=int, help=f'Archive page 1-{effie.ARCHIVE_PAGES}; default rotates by schedule')
    args = parser.parse_args()
    result = run(args.page)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
