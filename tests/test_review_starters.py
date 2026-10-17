import hashlib
import json
import sqlite3
import types

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from harness.library import learning, review_starters as starters, store
from harness.studio.library_api import install


@pytest.fixture
def candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    identities = []
    for n in range(6):
        item, _ = store.ingest({'source_url': f'https://example.org/{n}', 'title': f'候选{n}',
            'brand': '示例品牌', 'quality_evidence': [{'text': '官方入围依据'}]})
        digest = 'a' * 64 if n == 3 else format(n + 10, 'x') * 64
        with store.connection() as db:
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                       (item, f'assets/{item}/film.mp4', digest, 100, 70 if n == 5 else 30,
                        0 if n == 4 else 1, 1280, 720, 0))
        with learning.connection() as db:
            payload = {'media_role': 'original_ad', 'confidence': 'high',
                       'mechanism': 'private-analysis-detail', 'training_eligible': True}
            db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                       (item, 'f'*64 if n == 2 else digest, 1, 1, 'test-model', json.dumps(payload), 0))
            if n == 1:
                db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                           (item, digest, 2, 1, 'test-model', json.dumps({**payload, 'media_role': 'music_video'}), 1))
        identities.append(item)
    monkeypatch.setattr(starters, 'STARTERS', tuple((i, f'观察点{n}', '商品如何改变故事？')
                                                  for n, i in enumerate(identities)))
    store.review_item(identities[0], 42, 0, 'selected', {'craft': 5}, [], 'private-review-note')
    return identities


def test_only_current_original_ads_are_shown_without_private_data_or_writes(candidates):
    paths = [store.ROOT/'library.sqlite3', store.ROOT/'learning/analyses.sqlite3']
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    result = starters.review_starters()
    assert result['state'] == 'ready'
    # Reject a newer music-video classification, a replaced file, a duplicate,
    # a silent file and an out-of-range duration.
    assert [c['id'] for c in result['items']] == [candidates[0]]
    assert result['items'][0]['source_evidence'] == '官方入围依据'
    assert result['training_eligible'] is False
    assert result['items'][0]['training_eligible'] is False
    encoded = json.dumps(result)
    for private in ('private-review-note', 'private-analysis-detail', 'sha256', 'assets/', 'test-model'):
        assert private not in encoded
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


@pytest.mark.parametrize('latest', ['not-json', '[]', '{"media_role":"original_ad","confidence":"low"}'])
def test_bad_or_low_confidence_latest_version_never_revives_older_analysis(candidates, latest):
    item = candidates[0]
    with learning.connection() as db:
        db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                   (item, 'a'*64, 2, 1, 'test-model', latest, 2))
    # The duplicate may now appear as a different source candidate, but the
    # reclassified/malformed source must never reappear from its old version.
    assert item not in [c['id'] for c in starters.review_starters()['items']]


def test_missing_databases_fail_without_creating_a_new_library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path/'missing')
    assert starters.review_starters()['state'] == 'unavailable'
    assert not store.ROOT.exists()


def test_site_gate_and_account_tokens_apply_to_starter_cards(candidates):
    app = FastAPI()
    def gate(request):
        if request.cookies.get('access') != 'yes':
            raise HTTPException(403)
    def auth(value):
        if value != 'Bearer user':
            raise HTTPException(401)
        return {'id': 42}
    install(types.SimpleNamespace(app=app, require_site_access=gate, require_session=auth))
    with TestClient(app) as client:
        path = '/creative/api/library/review-starters'
        assert client.get(path).status_code == 403
        client.cookies.set('access', 'yes')
        result = client.get(path)
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'private, no-store'
        assert result.json()['items'][0]['id'] == candidates[0]
        assert client.get(path, headers={'Authorization': 'Bearer expired'}).status_code == 401
        assert client.get(path, headers={'Authorization': 'Bearer user'}).json() == result.json()
