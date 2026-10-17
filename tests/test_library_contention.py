"""Exercise actual SQLite locks, annotation rollback and the HTTP boundary."""
import sqlite3
import time
import types

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from harness.library import store
from harness.studio.library_api import install


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    identity, _ = store.ingest({'source_url': 'https://example.org/ad', 'title': '案例'})
    app = FastAPI()
    def gate(request):
        if request.cookies.get('access') != 'yes':
            raise HTTPException(403)
    install(types.SimpleNamespace(app=app, require_site_access=gate,
        require_session=lambda token: {'id': 1}))
    with TestClient(app) as client:
        client.cookies.set('access', 'yes')
        yield client, identity


def test_busy_list_is_bounded_private_and_recovers(library):
    client, identity = library
    with sqlite3.connect(store.ROOT/'library.sqlite3') as locked:
        locked.execute('BEGIN EXCLUSIVE')
        start = time.monotonic()
        result = client.get('/creative/api/library?local_only=true')
        assert time.monotonic() - start < 6
        assert result.status_code == 503
        assert result.headers['retry-after'] == '3'
        assert result.headers['cache-control'] == 'private, no-store'
        assert '重新加载' in result.json()['detail']
        assert str(store.ROOT) not in result.text
        client.cookies.clear()
        assert client.get('/creative/api/library').status_code == 403
    client.cookies.set('access', 'yes')
    assert client.get('/creative/api/library').json()['total'] == 1


def test_commit_contention_rolls_back_and_manual_save_succeeds_once(library):
    client, identity = library
    url = '/creative/api/library/'+identity+'/review'
    payload = {'version': 0, 'state': 'selected', 'scores': {'sound': 5},
               'tags': ['声音'], 'note': '完整听看后的个人判断'}
    headers = {'Authorization': 'Bearer viewer'}
    # A reader lets the writer insert, but blocks its COMMIT. The response
    # must not claim success and the uncommitted preference must disappear.
    with sqlite3.connect(store.ROOT/'library.sqlite3') as reader:
        reader.execute('BEGIN')
        reader.execute('SELECT id FROM items').fetchall()
        response = client.post(url, json=payload, headers=headers)
        assert response.status_code == 503
        assert '未保存' in response.json()['detail']
        reader.rollback()
    assert store.review_history(identity, 1) == []
    success = client.post(url, json=payload, headers=headers)
    assert success.status_code == 200
    item = success.json()
    assert item['review']['version'] == 1
    assert item['review']['note'] == payload['note']
    assert item['training_eligible'] is False
    assert len(store.review_history(identity, 1)) == 1
    assert store.get_item(identity, 2)['review']['state'] == 'pending'
    assert client.post(url, json=payload, headers=headers).status_code == 409


def test_playable_count_keeps_filters_and_immediate_new_asset(library):
    client, identity = library
    url = '/creative/api/library?local_only=true'
    assert client.get(url).json()['total'] == 0
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, 'assets/film.mp4', 'a'*64, 10, 35, 1, 1280, 720, 0))
    assert client.get(url).json()['total'] == 1
    for extra in ('&duration_band=short', '&industry=其他', '&ad_type=其他',
                  '&q=不存在', '&state=selected', '&ad_group=sound'):
        assert client.get(url+extra).json()['total'] == 0
    assert client.get(url+'&duration_band=standard').json()['total'] == 1


@pytest.mark.parametrize('locked_database', ['library.sqlite3', 'learning/analyses.sqlite3'])
def test_analysis_read_lock_is_bounded_and_recovers(library, locked_database):
    from harness.library import learning
    client, identity = library
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, 'assets/film.mp4', 'a'*64, 10, 30, 1, 1280, 720, 0))
    learning.save_analysis(identity,'a'*64,1,'fixture',{'principle':'可见变化','training_eligible':False},[1,15])
    url='/creative/api/library/'+identity+'/analysis'
    with sqlite3.connect(store.ROOT/locked_database) as locked:
        locked.execute('BEGIN EXCLUSIVE')
        start=time.monotonic()
        result=client.get(url)
        assert time.monotonic()-start < 6
        assert result.status_code == 503
        assert result.headers['retry-after'] == '3'
        assert result.headers['cache-control'] == 'private, no-store'
        assert str(store.ROOT) not in result.text
        client.cookies.clear()
        assert client.get(url).status_code == 403
    client.cookies.set('access','yes')
    result=client.get(url)
    assert result.status_code == 200
    assert result.json()['analysis']['analysis_version'] == 1
    assert result.headers['cache-control'] == 'private, no-store'


def test_analysis_read_tracks_current_version_without_loading_reviews(library, monkeypatch):
    from harness.library import learning
    client, identity = library
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, 'assets/film.mp4', 'a'*64, 10, 30, 1, 1280, 720, 0))
    learning.save_analysis(identity,'a'*64,1,'fixture',{'principle':'旧观察'},[1,15])
    learning.save_analysis(identity,'a'*64,1,'fixture',{'principle':'修正观察'},[1,15])
    def forbidden(*args, **kwargs):
        raise AssertionError('Interactive analysis must not load full sources, reviews or initialize schema')
    monkeypatch.setattr(store,'get_item',forbidden)
    monkeypatch.setattr(learning,'connection',forbidden)
    url='/creative/api/library/'+identity+'/analysis'
    assert client.get(url).json()['analysis']['principle'] == '修正观察'
    with store.connection() as db:
        db.execute('UPDATE assets SET sha256=? WHERE item=?',('b'*64,identity))
    assert client.get(url).json() == {'state':'pending','analysis':None,'training_eligible':False}
    assert client.get('/creative/api/library/missing/analysis').status_code == 404


def test_missing_analysis_database_is_pending_without_creating_files(library):
    client, identity = library
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, 'assets/film.mp4', 'a'*64, 10, 30, 1, 1280, 720, 0))
    assert not (store.ROOT/'learning').exists()
    assert client.get('/creative/api/library/'+identity+'/analysis').json()['state'] == 'pending'
    assert not (store.ROOT/'learning').exists()
