#!/usr/bin/env python3
"""Collect bounded LIA winner metadata from permanent public entry pages."""
import argparse, fcntl, json, os, secrets, sys, time
from contextlib import ExitStack
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import lia

YEARS = (2025, 2024, 2023, 2022)
# Keep the source taxonomy explicit and bounded. These categories cover the
# main moving-image/audio ad forms plus adjacent branded formats that are
# useful as templates; non-media design/print categories stay out of this
# collector and can be added through a dedicated source later.
MEDIUMS = (
    (6, 'TV & Cinema'), (36, 'Online Film'), (7, 'Audio & Radio'),
    (24, 'Music Video'), (45, 'Branded Content'), (25, 'Branded Entertainment'),
    (2, 'Digital'), (3, 'Integration'), (29, 'Use of Social Media & Influencers'),
    (27, 'Ambient & Activation'),
    (22, 'Music & Sound'), (23, 'Production & Post-Production'),
    (46, 'Creative Strategy'),
)
MAX_PAGES = 4


def failure_detail(error, year, phase, medium_id=None, page=None):
    """Report bounded diagnostics without exception messages or request URLs."""
    code = 'invalid_source'
    if isinstance(error, httpx.HTTPStatusError):
        code = 'http_status'
    elif isinstance(error, httpx.TimeoutException):
        code = 'timeout'
    elif isinstance(error, httpx.HTTPError):
        code = 'transport_error'
    elif isinstance(error, ValueError) and str(error) in ('robots_unavailable', 'robots_disallowed'):
        code = str(error)
    result = {'year': year, 'phase': phase, 'error_code': code}
    if medium_id is not None:
        result.update(medium_id=medium_id, page=page)
    if isinstance(error, httpx.HTTPStatusError):
        result['http_status'] = error.response.status_code
    return result


def run(years=None, medium_ids=None, page_start=1):
    # Targeted backfills use the same vetted archive/category allowlist and
    # shared collector lock as scheduled scans. Invalid selections fail
    # before any network request or database write.
    selected_years = tuple(YEARS if years is None else years)
    selected_ids = tuple(mid for mid, _ in MEDIUMS) if medium_ids is None else tuple(medium_ids)
    if (not selected_years or len(set(selected_years)) != len(selected_years)
            or any(type(year) is not int or year not in YEARS for year in selected_years)
            or not selected_ids or len(set(selected_ids)) != len(selected_ids)
            or any(type(mid) is not int or mid not in dict(MEDIUMS) for mid in selected_ids)
            or type(page_start) is not int or not 1 <= page_start <= 500):
        raise ValueError('invalid_lia_selection')
    selected_mediums = [(mid, dict(MEDIUMS)[mid]) for mid in selected_ids]
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        backup = None if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1' else locks.enter_context((store.ROOT/'.backup.lock').open('a'))
        collector = locks.enter_context((store.ROOT/'.collector.lock').open('a'))
        try:
            if backup: fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(collector, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'discovered': 0, 'inserted': 0}
        identity, started, inserted, records = secrets.token_hex(12), time.time(), 0, []
        with store.connection() as c:
            c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)', (identity, 'LIA official winners', started, 'running'))
        failures = []
        try:
            seen = set()
            with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': 'VisualAgent-ReferenceCollector/1.0'}) as client:
                for year in selected_years:
                    origin = f'https://{year}.liaentries.com'
                    try:
                        robots = RobotFileParser()
                        rp = client.get(origin + '/robots.txt')
                        if rp.status_code not in (200, 404):
                            raise ValueError('robots_unavailable')
                        if rp.status_code == 200:
                            robots.parse(rp.text.splitlines())
                        # Some archived years explicitly disallow crawling. Skip
                        # that year and preserve the other public archives.
                        if rp.status_code == 200 and not robots.can_fetch('VisualAgent-ReferenceCollector', origin + '/winners/'):
                            continue
                    except (httpx.HTTPError, ValueError) as exc:
                        failures.append(failure_detail(exc, year, 'robots'))
                        continue
                    for medium_id, _label in selected_mediums:
                        try:
                            page_fingerprints = set()
                            for page_no in range(page_start, page_start + MAX_PAGES):
                                url = origin + f'/winners/?clear_search_session=true&id_medium={medium_id}&range=w&view=icons&page={page_no}'
                                if rp.status_code == 200 and not robots.can_fetch('VisualAgent-ReferenceCollector', url):
                                    raise ValueError('robots_disallowed')
                                page = client.get(url); page.raise_for_status()
                                batch = lia.parse_winners(page.text, medium_id, year=year, origin=origin)
                                if not batch:
                                    break
                                fingerprint = tuple(sorted(r['source_url'] for r in batch))
                                if fingerprint in page_fingerprints:
                                    break
                                page_fingerprints.add(fingerprint)
                                for record in batch:
                                    if record['source_url'] not in seen:
                                        records.append(record); seen.add(record['source_url'])
                                time.sleep(0.2)
                        except (httpx.HTTPError, ValueError, KeyError) as exc:
                            # A single archived medium may be temporarily unavailable.
                            # Keep the records already collected and let the next
                            # scheduled run revisit the source.
                            failures.append(failure_detail(exc, year, 'listing', medium_id, page_no))
            for record in records:
                _, new = store.ingest(record); inserted += int(new)
            if failures and not records:
                state = 'failed'
            else:
                state = 'partial' if failures else 'completed'
            error = 'source_unavailable' if failures else ''
        except (httpx.HTTPError, ValueError, KeyError):
            state, error = 'failed', 'source_unavailable'
        with store.connection() as c:
            c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?', (time.time(), state, len(records), inserted, error, identity))
        return {'id': identity, 'state': state, 'discovered': len(records), 'inserted': inserted, 'error_code': error,
                'failures': failures}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=YEARS, action='append', help='Archive year to backfill; repeat for multiple years')
    parser.add_argument('--medium', type=int, choices=[mid for mid, _ in MEDIUMS], action='append', help='Vetted LIA medium ID; repeat for multiple categories')
    parser.add_argument('--page-start', type=int, default=1, help='Start page for a bounded backfill (1-500); default 1')
    args = parser.parse_args()
    result = run(years=args.year, medium_ids=args.medium, page_start=args.page_start)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
