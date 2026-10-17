import copy
import hashlib
import json

import httpx
import pytest

from harness.library import store
from harness.models.reference_sources import adfest
from tools import collect_adfest as collector


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    documents = {kind: b'\r\n%PDF-1.7 synthetic verified edition ' + kind.encode()
                 for kind in adfest.VERIFIED_PDFS}
    proofs = copy.deepcopy(adfest.VERIFIED_PDFS)
    for kind, content in documents.items():
        proofs[kind]['sha256'] = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(adfest, 'VERIFIED_PDFS', proofs)
    original_client = httpx.Client
    urls = {adfest.PDF_URL: 'film', adfest.CRAFT_PDF_URL: 'craft',
            adfest.ENTERTAINMENT_PDF_URL: 'entertainment'}
    def install(mode='live'):
        requests = []
        def respond(request):
            requests.append(str(request.url))
            if request.url.path == '/robots.txt':
                return httpx.Response(200, text='User-agent: *\nDisallow:\n')
            kind = urls[str(request.url)]
            if mode == 'offline':
                return httpx.Response(503)
            body = b'%PDF-1.7 different annual edition' if mode == 'changed' and kind == 'entertainment' else documents[kind]
            return httpx.Response(200, content=body, headers={'content-type': 'application/pdf'})
        monkeypatch.setattr(collector.httpx, 'Client', lambda **kwargs:
                            original_client(transport=httpx.MockTransport(respond), **kwargs))
        return requests
    def cache(corrupt=False):
        folder = tmp_path / 'source_cache' / 'adfest'
        folder.mkdir(parents=True, exist_ok=True)
        for kind, proof in proofs.items():
            data = b'corrupt cached document' if corrupt and kind == 'craft' else documents[kind]
            (folder / f"{proof['name']}-2025.pdf").write_bytes(data)
    return install, cache


def test_year_repair_preserves_record_identity_personal_review_and_media(source):
    install, _ = source
    corrected = adfest.winners()[0]
    legacy = copy.deepcopy(corrected)
    legacy['published'] = '2025'
    for field in ('source_name', 'summary'):
        legacy[field] = legacy[field].replace('ADFEST 2026', 'ADFEST 2025')
    legacy.pop('creative_structure')
    identity, _ = store.ingest(legacy)
    store.review_item(identity, 91, 0, 'selected', {'craft': 4}, ['my tag'], 'my review')
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, f'assets/{identity}/film.mp4', 'a'*64, 100, 20, 1, 1280, 720, 0))
        before = {table: [tuple(r) for r in db.execute('SELECT * FROM ' + table)]
                  for table in ('reviews', 'assets')}
    requests = install()
    result = collector.run()
    assert result['state'] == 'completed'
    assert result['source_year'] == 2026
    assert result['discovered'] == 53 and result['inserted'] == 52
    assert len(requests) == 4
    with store.connection() as db:
        row = db.execute('SELECT * FROM items WHERE id=?', (identity,)).fetchone()
        assert row['source_url'] == store.canonical_url(legacy['source_url'])
        assert row['title'] == legacy['title']
        data = json.loads(row['data'])
        assert data['published'] == '2026'
        assert data['creative_structure']['legacy_identity_year'] == 2025
        assert data['training_eligible'] is False
        assert data['quality_evidence'][0]['kind'] == 'award_finalist'
        assert before == {table: [tuple(r) for r in db.execute('SELECT * FROM ' + table)]
                          for table in before}
        assert db.execute("SELECT COUNT(*) FROM items WHERE title='FRIES BEAT 2025'").fetchone()[0] == 1


def test_new_live_edition_cannot_be_hidden_by_old_verified_cache(source):
    install, cache = source
    cache()
    install('changed')
    result = collector.run()
    assert result['state'] == 'failed' and result['error_code'] == 'source_document_changed'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0


@pytest.mark.parametrize('corrupt', [False, True])
def test_transport_failure_uses_only_verified_cached_bytes(source, corrupt):
    install, cache = source
    cache(corrupt=corrupt)
    install('offline')
    result = collector.run()
    if corrupt:
        assert result['state'] == 'failed' and result['error_code'] == 'source_document_changed'
    else:
        assert result['state'] == 'completed' and result['verified_cached_documents'] == 3
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == (0 if corrupt else 53)


def test_oversize_document_stops_before_ingestion(source, monkeypatch):
    install, _ = source
    install()
    monkeypatch.setattr(collector, 'MAX_PDF_BYTES', 32)
    result = collector.run()
    assert result['state'] == 'failed' and result['error_code'] == 'source_page_too_large'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0
