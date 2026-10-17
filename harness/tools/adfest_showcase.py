"""Collect one public ADFEST showcase page with a durable category cursor."""
from contextlib import ExitStack
import fcntl
import json
import os
import secrets
import sqlite3
import time
from urllib.robotparser import RobotFileParser

import httpx

from harness.library import store
from harness.models.reference_sources import adfest_showcase as source

USER_AGENT = 'VisualAgent-ReferenceCollector/1.0'


def _read(client, url, *, robots=False):
    with client.stream('GET', url) as response:
        if robots and response.status_code == 404:
            return ''
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > source.MAX_BYTES:
                raise ValueError('source_page_too_large')
            chunks.append(chunk)
        return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')


def collect(category, page=None):
    source.listing_url(category, 1 if page is None else page)
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        names = ['.collector.lock']
        if os.getenv('AD_LIBRARY_METADATA_OVERLAP') != '1':
            names.insert(0, '.backup.lock')
        try:
            for name in names:
                handle = locks.enter_context((store.ROOT / name).open('a'))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0}
        rid, started = secrets.token_hex(12), time.time()
        try:
            with store.connection() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS adfest_showcase_cursors (
                    year INTEGER NOT NULL, category INTEGER NOT NULL, page INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(year,category))''')
                saved = db.execute('SELECT page,fingerprint FROM adfest_showcase_cursors WHERE year=? AND category=?',
                                   (source.YEAR, category)).fetchone()
                db.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                    (rid, f'ADFEST {source.YEAR} {source.CATEGORIES[category][0]} public showcase', started, 'running'))
        except sqlite3.Error:
            return {'state': 'failed', 'error_code': 'database_unavailable', 'discovered': 0, 'inserted': 0}
        target = page if page is not None else saved['page'] if saved else 1
        state, error, records, inserted, failures = 'completed', '', [], 0, []
        next_page, total_pages, reset, attempted = target, None, False, 0
        try:
            with httpx.Client(timeout=30, follow_redirects=False, headers={'User-Agent': USER_AGENT}) as client:
                policy = RobotFileParser()
                policy.parse(_read(client, source.ORIGIN + '/robots.txt', robots=True).splitlines())
                media_policy = RobotFileParser()
                media_policy.parse(_read(client, 'https://adfest.d-energy.cn/robots.txt', robots=True).splitlines())
                delay = max(2, policy.crawl_delay(USER_AGENT) or 0)

                def read(url):
                    if not policy.can_fetch(USER_AGENT, url):
                        raise ValueError('robots_disallowed')
                    time.sleep(delay)
                    return _read(client, url)

                first = source.parse_listing(read(source.listing_url(category)), category)
                total_pages = first['pages']
                if page is None and saved and (saved['fingerprint'] != first['fingerprint'] or target > total_pages):
                    target, next_page, reset = 1, 1, True
                if target > total_pages:
                    raise ValueError('source_page_mismatch')
                current = first if target == 1 else source.parse_listing(
                    read(source.listing_url(category, target)), category, target)
                if current['pages'] != total_pages:
                    raise ValueError('source_page_mismatch')
                if target > 1 and {r['source_url'] for r in first['records']} & {r['source_url'] for r in current['records']}:
                    raise ValueError('page_repeated')
                for candidate in current['records']:
                    attempted += 1
                    try:
                        record = source.apply_detail(candidate, read(candidate['detail_url']))
                        if record:
                            if any(not media_policy.can_fetch(USER_AGENT, v['url'])
                                   for v in record['creative_structure']['public_video_variants']):
                                raise ValueError('robots_disallowed')
                            records.append(record)
                    except (httpx.HTTPError, ValueError) as exc:
                        failures.append({'candidate': attempted, 'error_code': _code(exc)})
            for record in records:
                inserted += int(store.ingest(record)[1])
            if failures:
                state, error = ('partial' if records else 'failed'), 'source_unavailable'
            else:
                next_page = target + 1 if target < total_pages else 1
                with store.connection() as db:
                    db.execute('''INSERT INTO adfest_showcase_cursors VALUES(?,?,?,?,?)
                        ON CONFLICT(year,category) DO UPDATE SET page=excluded.page,
                        fingerprint=excluded.fingerprint,updated=excluded.updated''',
                        (source.YEAR, category, next_page, first['fingerprint'], time.time()))
        except (httpx.HTTPError, ValueError, sqlite3.Error) as exc:
            state, error = 'failed', _code(exc)
        with store.connection() as db:
            db.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                (time.time(), state, len(records), inserted, error, rid))
        return {'id': rid, 'state': state, 'year': source.YEAR, 'category': category,
            'page': target, 'next_page': next_page, 'total_pages': total_pages,
            'cursor_reset': reset, 'category_scan_complete': state == 'completed' and target == total_pages,
            'attempted': attempted, 'discovered': len(records), 'inserted': inserted,
            'error_code': error, 'failure_details': failures}


def _code(exc):
    if isinstance(exc, sqlite3.Error):
        return 'database_unavailable'
    if isinstance(exc, ValueError) and str(exc) in (
            'source_page_too_large', 'source_edition_changed', 'source_category_mismatch',
            'source_page_mismatch', 'source_detail_identity_mismatch', 'robots_disallowed',
            'page_repeated', 'unrecognized_listing', 'invalid_source_detail', 'repeated_source_entry'):
        return str(exc)
    return 'source_unavailable'
