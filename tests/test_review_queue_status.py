"""Snapshot age must survive HTTP refreshes; counts follow the current film."""
import json
from datetime import datetime, timezone

import pytest

from harness.library import learning, store
from harness.studio import library_api


def test_snapshot_exposes_only_counts_and_original_observation_time(tmp_path, monkeypatch):
    monkeypatch.setenv('AD_LIBRARY_LEARNING_ARTIFACT_ROOT',str(tmp_path))
    monkeypatch.setattr(library_api,'_is_production_library',lambda:True)
    monkeypatch.setattr(library_api,'_QUEUE_CACHE',None)
    observed=datetime(2026,10,14,15,48,27,tzinfo=timezone.utc)
    monkeypatch.setattr(library_api.time,'time',lambda:observed.timestamp()+600)
    payload={'state':'ready','total_pending':100,'analysis_pending':80,
             'semantic_review_pending':20,'generated_at':observed.isoformat(),
             'items':[{'note':'private-case-detail'}],'training_eligible':True}
    (tmp_path/'ad-analysis-review-queue-fixture.json').write_text(json.dumps(payload))
    result=library_api._review_queue_summary()
    assert result=={'state':'ready','total_pending':100,'analysis_pending':80,
                    'semantic_review_pending':20,'observed_at':observed.timestamp(),
                    'training_eligible':False}
    # A later dashboard request cannot make the same measurements look new.
    monkeypatch.setattr(library_api.time,'time',lambda:observed.timestamp()+3600)
    assert library_api._review_queue_summary()==result
    assert 'private-case-detail' not in json.dumps(result)


@pytest.mark.parametrize('value',[None,False,0,'bad','2026-10-14T15:48:27',
                                 '2099-01-01T00:00:00+00:00','0001-01-01T00:00:00+00:00'])
def test_unknown_naive_and_impossible_timestamps_are_not_reported_as_now(value):
    assert library_api._queue_observed_at(value) is None


def test_database_fallback_uses_current_digest_before_comparing_versions(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setattr(library_api,'_is_production_library',lambda:False)
    monkeypatch.setattr(library_api.time,'time',lambda:1234)
    item,_=store.ingest({'source_url':'https://example.org/film','title':'Current film'})
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (item,'assets/film.mp4','b'*64,100,30,1,1280,720,0))
    for _ in range(2):
        learning.save_analysis(item,'a'*64,1,'fixture',{'audio_semantics_reviewed':False,
            'full_motion_reviewed':False,'note':'private-old-film'},[1,15])
    learning.save_analysis(item,'b'*64,1,'fixture',{'audio_semantics_reviewed':False,
        'full_motion_reviewed':False,'note':'private-current-film'},[1,15])
    result=library_api._review_queue_summary()
    assert result['analysis_pending']==0
    assert result['semantic_review_pending']==1
    assert result['observed_at']==1234
    assert 'private-' not in json.dumps(result)


def test_unavailable_queue_does_not_invent_an_observation_time(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path/'missing')
    monkeypatch.setattr(library_api,'_is_production_library',lambda:False)
    result=library_api._review_queue_summary()
    assert result['state']=='unavailable'
    assert result['observed_at'] is None
    assert not store.ROOT.exists()


def test_status_http_includes_snapshot_time_on_fresh_and_cached_reads(tmp_path,monkeypatch):
    import types
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.ingest({'source_url':'https://example.org/status','title':'Reference'})
    monkeypatch.setattr(library_api,'_is_production_library',lambda:True)
    monkeypatch.setattr(library_api,'_STATUS_CACHE',{})
    queue={'state':'ready','total_pending':0,'analysis_pending':0,
           'semantic_review_pending':0,'observed_at':1234,'training_eligible':False}
    monkeypatch.setattr(library_api,'_review_queue_summary',lambda:dict(queue))
    app=FastAPI()
    library_api.install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,
                                             require_session=lambda h:{'id':1}))
    with TestClient(app) as client:
        endpoint='/creative/api/library/status'
        assert client.get(endpoint).json()['review_queue']['observed_at']==1234
        assert client.get(endpoint).json()['review_queue']['observed_at']==1234
        queue['observed_at']=5678
        assert client.get(endpoint).json()['review_queue']['observed_at']==5678
