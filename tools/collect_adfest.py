"""Refresh curated ADFEST records only from their verified PDF editions."""
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
from harness.models.reference_sources import adfest

USER_AGENT = 'VisualAgent-ReferenceCollector/1.0'
MAX_PDF_BYTES = 4 * 1024 * 1024


def _verified_document(client, kind, url):
    proof = adfest.VERIFIED_PDFS[kind]
    folder = store.ROOT / 'source_cache' / 'adfest'
    target = folder / f"{proof['name']}-{adfest.SOURCE_YEAR}.pdf"
    try:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            content = bytearray()
            for block in response.iter_bytes():
                content.extend(block)
                if len(content) > MAX_PDF_BYTES:
                    raise ValueError('source_page_too_large')
    except httpx.HTTPError:
        # Transport failures may use a verified edition. A changed live PDF
        # must fail below, never be hidden by an older cached document.
        for candidate in (target, folder / f"{proof['name']}-{adfest.LEGACY_IDENTITY_YEAR}.pdf"):
            if candidate.is_file() and candidate.stat().st_size <= MAX_PDF_BYTES:
                adfest.verify_pdf(kind, candidate.read_bytes())
                return True
        raise
    adfest.verify_pdf(kind, content)
    folder.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with target.open('xb') as output:
            output.write(content)
    else:
        adfest.verify_pdf(kind, target.read_bytes())
    return False


def run():
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
        with store.connection() as db:
            db.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                       (rid, 'ADFEST Film / Film Craft / Entertainment official winners', started, 'running'))
        records, cached, inserted, state, error = [], 0, 0, 'completed', ''
        try:
            with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': USER_AGENT}) as client:
                robots = client.get('https://www.adfest.com/robots.txt')
                if robots.status_code not in (200, 404) or len(robots.content) > MAX_PDF_BYTES:
                    raise ValueError('robots_unavailable')
                policy = RobotFileParser()
                policy.parse(robots.text.splitlines() if robots.status_code == 200 else [])
                delay = max(2, policy.crawl_delay(USER_AGENT) or 0)
                for kind, url in (('film', adfest.PDF_URL), ('craft', adfest.CRAFT_PDF_URL),
                                  ('entertainment', adfest.ENTERTAINMENT_PDF_URL)):
                    if not policy.can_fetch(USER_AGENT, url):
                        raise ValueError('robots_disallowed')
                    time.sleep(delay)
                    cached += int(_verified_document(client, kind, url))
            # Validate all editions before modifying any reference record.
            records = adfest.winners() + adfest.craft_winners() + adfest.entertainment_winners()
            inserted = sum(store.ingest(record)[1] for record in records)
        except (httpx.HTTPError, ValueError) as exc:
            state = 'failed'
            error = str(exc) if str(exc) in ('source_document_changed', 'source_page_too_large',
                                             'robots_unavailable', 'robots_disallowed') else 'source_unavailable'
        with store.connection() as db:
            db.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',
                       (time.time(), state, len(records), inserted, error, rid))
        return {'id': rid, 'state': state, 'discovered': len(records), 'inserted': inserted,
                'source_year': adfest.SOURCE_YEAR, 'verified_cached_documents': cached, 'error_code': error}


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['state'] == 'failed' else 0)
