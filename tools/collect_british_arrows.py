#!/usr/bin/env python3
"""Collect bounded British Arrows commercial and craft winner metadata."""
import argparse
from contextlib import ExitStack
import fcntl, json, os, secrets, sys, time
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import british_arrows

SOURCE = 'British Arrows official film winners'
MAX_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 12
REQUEST_DELAY = 1


def _year(year):
    if year is None:
        return british_arrows.YEARS[int(time.time() // (3 * 3600)) % len(british_arrows.YEARS)]
    if type(year) is not int or year not in british_arrows.YEARS:
        raise ValueError('invalid_british_arrows_year')
    return year


def _cursor_path(year, explicit):
    return store.ROOT / (f'british_arrows_cursor_{year}.json' if explicit else 'british_arrows_cursor.json')


def run(year=None, page=None, offset=None):
    explicit = year is not None or page is not None or offset is not None
    year = _year(year)
    if page is not None and (type(page) is not int or not 1 <= page <= british_arrows.MAX_PAGES):
        raise ValueError('invalid_british_arrows_page')
    if offset is not None and (type(offset) is not int or offset < 0):
        raise ValueError('invalid_british_arrows_offset')
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((store.ROOT/'.backup.lock').open('a'))
        collector = locks.enter_context((store.ROOT/'.collector.lock').open('a'))
        try:
            if backup: fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0}
        cursor_path = _cursor_path(year, explicit)
        cursor = {'year': year, 'page': page or 1, 'offset': 0}
        saved = None
        if cursor_path.exists():
            try:
                saved = json.loads(cursor_path.read_text())
                if saved.get('year') in british_arrows.YEARS:
                    if not explicit or saved.get('year') == cursor['year']:
                        cursor.update({k: int(saved[k]) for k in ('year', 'page', 'offset') if k in saved})
            except (OSError, ValueError, TypeError):
                pass
        if page is not None:
            cursor['page'] = page
            if not saved or saved.get('year') != year or saved.get('page') != page:
                cursor['offset'] = 0
        if offset is not None:
            cursor['offset'] = offset
        rid, started, inserted = secrets.token_hex(12), time.time(), 0
        with store.connection() as c:
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)', (rid, SOURCE, started, 'running'))
        records, failures = [], 0
        try:
            with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'}) as client:
                robots = client.get(british_arrows.ORIGIN + '/robots.txt')
                if robots.status_code not in (200, 404):
                    raise ValueError('robots_unavailable')
                policy = RobotFileParser()
                policy.parse(robots.text.splitlines() if robots.status_code == 200 else [])
                listing = british_arrows.listing_url(cursor['year'], cursor['page'])
                if robots.status_code == 200 and not policy.can_fetch('VisualAgent-ReferenceCollector', listing):
                    raise ValueError('robots_disallowed')
                response = client.get(listing)
                response.raise_for_status()
                if len(response.content) > MAX_BYTES:
                    raise ValueError('source_page_too_large')
                candidates, last_page = british_arrows.parse_listing(response.text, cursor['year'], cursor['page'])
                batch = candidates[cursor['offset']:cursor['offset'] + MAX_ENTRIES]
                for index, candidate in enumerate(batch):
                    try:
                        if index:
                            time.sleep(REQUEST_DELAY)
                        detail = client.get(candidate['source_url'])
                        detail.raise_for_status()
                        if len(detail.content) > MAX_BYTES:
                            raise ValueError('detail_too_large')
                        record = british_arrows.apply_detail(candidate, detail.text)
                        if record:
                            records.append(record)
                    except (httpx.HTTPError, ValueError, KeyError):
                        failures += 1
                next_cursor = dict(cursor)
                if cursor['offset'] + len(batch) < len(candidates):
                    next_cursor['offset'] = cursor['offset'] + len(batch)
                elif cursor['page'] < last_page:
                    next_cursor.update(page=cursor['page'] + 1, offset=0)
                else:
                    idx = british_arrows.YEARS.index(cursor['year'])
                    next_cursor.update(year=british_arrows.YEARS[(idx + 1) % len(british_arrows.YEARS)], page=1, offset=0)
            for record in records:
                inserted += int(store.ingest(record)[1])
            cursor_path.write_text(json.dumps(next_cursor, ensure_ascii=False))
            state = 'partial' if failures and records else ('failed' if failures else 'completed')
            error = 'source_unavailable' if failures else ''
        except (httpx.HTTPError, ValueError, KeyError):
            state, error, next_cursor = 'failed', 'source_unavailable', cursor
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                      (time.time(), state, len(records), inserted, error, rid))
        return {'id': rid, 'state': state, 'year': cursor['year'], 'page': cursor['page'],
                'discovered': len(records), 'inserted': inserted, 'error_code': error}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=british_arrows.YEARS)
    parser.add_argument('--page', type=int)
    parser.add_argument('--offset', type=int)
    args = parser.parse_args()
    result = run(args.year, args.page, args.offset)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
