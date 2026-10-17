"""Bounded annual award-list collection with a durable, per-year cursor.

Adapters own source parsing. This action owns the collection lock, request
budget, normalized ingestion and receipt. The cursor lives in library.sqlite3
so the existing verified database backup also protects crawl progress.
"""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import time
from urllib.robotparser import RobotFileParser

import httpx
from httpx import HTTPError, HTTPStatusError, TimeoutException

from harness.library import store

MAX_BYTES = 4 * 1024 * 1024
MAX_CANDIDATES = 5000
BATCH_SIZE = 12
USER_AGENT = 'VisualAgent-ReferenceCollector/1.0'
MAX_BATCHES = 32


def _failure_detail(error, phase):
    """Bound diagnostics without logging request URLs or exception messages."""
    code = 'invalid_source'
    if isinstance(error, HTTPStatusError):
        code = 'http_status'
    elif isinstance(error, TimeoutException):
        code = 'timeout'
    elif isinstance(error, HTTPError):
        code = 'transport_error'
    elif isinstance(error, sqlite3.Error):
        code = 'database_unavailable'
    elif isinstance(error, ValueError) and str(error) in (
            'robots_unavailable', 'robots_disallowed', 'source_page_too_large',
            'unrecognized_listing', 'offset_out_of_range'):
        code = str(error)
    result = {'phase': phase, 'error_code': code}
    if isinstance(error, HTTPStatusError):
        result['http_status'] = error.response.status_code
    return result


def collect_archive_batches(adapter, source, key, year, *, max_batches,
                            offset=None, request_delay=10, on_batch=None):
    """Continue bounded batches from the durable cursor, stopping at year end.

    Partial/failed batches and occupied locks stop this invocation without
    retrying. Each call acquires the existing locks independently, allowing
    normal scheduled collectors to run between batches.
    """
    if type(max_batches) is not int or not 1 <= max_batches <= MAX_BATCHES:
        raise ValueError('invalid_archive_batch_limit')
    adapter.listing_url(year)
    result = {'year': year, 'state': 'completed', 'batches': 0,
              'discovered': 0, 'inserted': 0, 'stop_reason': 'batch_limit'}
    for number in range(max_batches):
        batch = collect_archive(adapter, source, key, year,
                                offset if number == 0 else None, request_delay)
        result['batches'] += 1
        result['discovered'] += batch.get('discovered', 0)
        result['inserted'] += batch.get('inserted', 0)
        result['last_batch'] = batch
        if on_batch:
            on_batch(batch)
        if batch['state'] != 'completed':
            result.update(state=batch['state'], stop_reason=batch['state'])
            # Preserve the underlying failure category for the rotation runner.
            # Otherwise a transient source outage becomes an unknown hard failure.
            if batch.get('error_code'):
                result['error_code'] = batch['error_code']
            break
        if batch.get('year_scan_complete'):
            result['stop_reason'] = 'year_scan_complete'
            break
        if number and batch.get('cursor_reset'):
            result.update(state='partial', stop_reason='listing_changed')
            break
        if batch['next_offset'] <= batch['offset']:
            result.update(state='failed', stop_reason='cursor_not_advanced')
            break
    return result


def _read_page(client, url, max_bytes=MAX_BYTES):
    # Bound decoded bytes as they arrive, including chunked responses.
    with client.stream('GET', url) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise ValueError('source_page_too_large')
            chunks.append(chunk)
        return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')


def collect_archive(adapter, source, key, year, offset=None, request_delay=10):
    """Visit at most 12 details; advance only after a fully handled batch.

    An explicit offset sets this year's starting point. A normal subsequent
    call resumes it. Reordered listings reset to zero, preventing skipped
    entries. Any failed detail keeps the cursor unchanged for the next
    scheduled run; successes already ingested are safely de-duplicated.
    """
    adapter.listing_url(year)  # validate before locks, network, or writes
    listing_max_bytes = getattr(adapter, 'LISTING_MAX_BYTES', MAX_BYTES)
    if type(listing_max_bytes) is not int or not 0 < listing_max_bytes <= 12 * 1024 * 1024:
        raise ValueError('invalid_listing_byte_limit')
    if offset is not None and (type(offset) is not int or not 0 <= offset < MAX_CANDIDATES):
        raise ValueError('invalid_archive_offset')
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

        rid, started = secrets.token_hex(12), time.time()
        try:
            with store.connection() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS archive_cursors (
                    source TEXT NOT NULL, year INTEGER NOT NULL, offset INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, updated REAL NOT NULL,
                    PRIMARY KEY(source,year))''')
                saved = db.execute('SELECT offset,fingerprint FROM archive_cursors WHERE source=? AND year=?', (key, year)).fetchone()
                db.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)', (rid, source, started, 'running'))
        except sqlite3.Error:
            # No receipt could be committed. Return a bounded failure instead
            # of a traceback, and do not start network work or move the cursor.
            return {'state':'failed','error_code':'database_unavailable','year':year,
                    'discovered':0,'inserted':0}
        records, inserted, failures, attempted = [], 0, 0, 0
        start = offset if offset is not None else (saved['offset'] if saved else 0)
        next_offset, candidate_count = start, None
        reset, wrapped, fingerprint = False, False, ''
        state, error = 'completed', ''
        details, phase = [], 'robots'
        try:
            with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': USER_AGENT}) as client:
                robots = client.get(adapter.ORIGIN + '/robots.txt')
                if robots.status_code not in (200, 404) or len(robots.content) > MAX_BYTES:
                    raise ValueError('robots_unavailable')
                policy = RobotFileParser()
                policy.parse(robots.text.splitlines() if robots.status_code == 200 else [])
                delay = max(request_delay, policy.crawl_delay(USER_AGENT) or 0)
                listing = adapter.listing_url(year)
                if robots.status_code == 200 and not policy.can_fetch(USER_AGENT, listing):
                    raise ValueError('robots_disallowed')
                phase = 'listing'
                candidates = adapter.parse_listing(_read_page(client, listing, listing_max_bytes), year=year, max_entries=None)
                candidate_count = len(candidates)
                if ((not candidates and getattr(adapter, 'ALLOW_EMPTY_LISTING', False) is not True)
                        or candidate_count > MAX_CANDIDATES):
                    raise ValueError('unrecognized_listing')
                fingerprint = hashlib.sha256(json.dumps([r['source_url'] for r in candidates]).encode()).hexdigest()
                if offset is None and saved and saved['fingerprint'] != fingerprint:
                    start, reset = 0, True
                if not candidate_count:
                    if offset is not None:
                        raise ValueError('offset_out_of_range')
                    start = 0
                elif start >= candidate_count:
                    if offset is not None:
                        raise ValueError('offset_out_of_range')
                    start, reset = 0, True
                next_offset = start
                batch = candidates[start:start + BATCH_SIZE]
                for candidate in batch:
                    attempted += 1
                    try:
                        if robots.status_code == 200 and not policy.can_fetch(USER_AGENT, candidate['source_url']):
                            raise ValueError('robots_disallowed')
                        time.sleep(delay)
                        detail = _read_page(client, candidate['source_url'])
                        record = adapter.apply_detail(candidate, adapter.parse_detail(detail, candidate['source_url']))
                        if record:
                            records.append(record)
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        failures += 1
                        details.append({**_failure_detail(exc, 'detail'), 'candidate': attempted})
            phase = 'ingest'
            for record in records:
                inserted += int(store.ingest(record)[1])
            if failures:
                state, error = ('partial' if records else 'failed'), 'source_unavailable'
            else:
                next_offset = start + len(batch)
                wrapped = next_offset >= candidate_count
                if wrapped:
                    next_offset = 0
                phase = 'cursor'
                with store.connection() as db:
                    db.execute('''INSERT INTO archive_cursors VALUES(?,?,?,?,?)
                        ON CONFLICT(source,year) DO UPDATE SET offset=excluded.offset,
                        fingerprint=excluded.fingerprint,updated=excluded.updated''',
                        (key, year, next_offset, fingerprint, time.time()))
        except sqlite3.Error as exc:
            state, error = 'failed', 'database_unavailable'
            details.append(_failure_detail(exc, phase))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            state, error = 'failed', 'source_unavailable'
            details.append(_failure_detail(exc, phase))
        with store.connection() as db:
            db.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                       (time.time(), state, len(records), inserted, error, rid))
        return {'id': rid, 'state': state, 'year': year, 'offset': start,
                'next_offset': next_offset, 'listing_candidates': candidate_count,
                'attempted': attempted, 'cursor_reset': reset, 'year_scan_complete': wrapped,
                'discovered': len(records), 'inserted': inserted, 'error_code': error,
                'failure_details': details}
