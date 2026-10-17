import json
import types
import pytest
from fastapi import HTTPException
from harness.studio import store
from harness.studio.learning_review_api import install
from harness.learning import review
from test_creative_studio import client,ready


@pytest.fixture
def reviewers(client):
    client.app.router.routes[:]=[r for r in client.app.router.routes if not getattr(r,'path','').startswith('/creative/api/admin/learning') and getattr(r,'path','')!='/creative/review']
    def admin(value):
        if value not in ('Bearer admin','Bearer one'):raise HTTPException(403)
        return {'id':3 if value=='Bearer admin' else 1}
    install(types.SimpleNamespace(app=client.app,require_admin=admin))
    return client


def film(client,consent=True):
    p=ready(client);p.update(state='completed',artifact='artifacts/'+p['id']+'/final.mp4')
    path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'test-film')
    store.save(p,1)
    controls=client.get('/creative/api/projects/'+p['id']+'/learning').json()
    if consent:
        body={k:controls[k] for k in ('revision','artifact_sha256','policy','policy_sha256')}
        assert client.post('/creative/api/projects/'+p['id']+'/learning/consent',json={**body,'training':True,'public_dataset':False}).status_code==200
    return p,path,controls


def assessment(p,controls):
    return {'revision':p['revision'],'artifact_sha256':controls['artifact_sha256'],'decision':'passed',
        'ratings':{k:{'score':4,'evidence':'测试中核对了对应画面或声音证据'} for k in review.RUBRIC},
        'checks':{'full_video_watched':True,'audio_listened':True,'product_facts_checked':True}}


def test_only_independent_admin_can_review_opted_in_current_film(reviewers):
    c=reviewers;p,path,controls=film(c);url='/creative/api/admin/learning/projects/'+p['id'];admin={'Authorization':'Bearer admin'}
    assert c.get(url).status_code==403
    assert c.get(url,headers={'Authorization':'Bearer two'}).status_code==403
    d=c.get(url,headers=admin).json();assert d['artifact_sha256']==controls['artifact_sha256'] and d['assessment'] is None
    queue=c.get('/creative/api/admin/learning/queue',headers=admin).json()
    assert queue['items'][0]['project']==p['id'] and queue['items'][0]['digest_status']=='needs_verification'
    body=assessment(p,controls);r=c.post(url+'/assessment',json=body,headers=admin)
    assert r.status_code==200 and r.json()['decision']=='passed' and not r.json()['training_eligible']
    latest=c.get(url,headers=admin).json()['assessment'];assert latest['independent']
    current=c.get('/creative/api/projects/'+p['id']).json();assert not current['training_eligible']
    assert all('测试中' not in str(e) for e in current['events'])
    p2,_,_=film(c,consent=False)
    assert c.get('/creative/api/admin/learning/projects/'+p2['id'],headers=admin).status_code==403
    assert len(c.get('/creative/api/admin/learning/queue',headers=admin).json()['items'])==1


def test_assessment_rejects_stale_version_missing_evidence_and_unheard_audio(reviewers):
    c=reviewers;p,path,controls=film(c);url='/creative/api/admin/learning/projects/'+p['id']+'/assessment';admin={'Authorization':'Bearer admin'};body=assessment(p,controls)
    for changed in ({'revision':0},{'artifact_sha256':'a'*64},{'ratings':{}},
                    {'checks':{**body['checks'],'audio_listened':False}},
                    {'ratings':{**body['ratings'],'audio_quality':{'score':2,'evidence':'声音有明显质量问题'}}}):
        assert c.post(url,json={**body,**changed},headers=admin).status_code==409
    bad={**body,'ratings':{**body['ratings'],'audio_quality':{'score':True,'evidence':'不能把布尔值当评分'}}}
    assert c.post(url,json=bad,headers=admin).status_code==422
    path.write_bytes(b'changed')
    assert c.post(url,json=body,headers=admin).status_code==409


def test_review_history_and_revocation_are_not_silently_reused(reviewers):
    c=reviewers;p,path,controls=film(c);url='/creative/api/admin/learning/projects/'+p['id'];admin={'Authorization':'Bearer admin'};body=assessment(p,controls)
    first=c.post(url+'/assessment',json=body,headers=admin).json()
    changed=c.post(url+'/assessment',json={**body,'decision':'needs_changes'},headers=admin).json()
    assert first['receipt_id']!=changed['receipt_id']
    assert c.get(url,headers=admin).json()['assessment']['decision']=='needs_changes'
    controls_body={k:controls[k] for k in ('revision','artifact_sha256','policy','policy_sha256')}
    c.post('/creative/api/projects/'+p['id']+'/learning/consent',json={**controls_body,'training':False,'public_dataset':False})
    assert c.get(url,headers=admin).status_code==403
    assert c.post(url+'/assessment',json=body,headers=admin).status_code==409


def test_admin_media_stays_bound_to_version_and_consent(reviewers):
    c=reviewers;p,path,controls=film(c);url='/creative/api/admin/learning/projects/'+p['id']+'/media';admin={'Authorization':'Bearer admin'}
    assert c.get(url,params={'revision':p['revision'],'digest':controls['artifact_sha256']},headers=admin).status_code==200
    assert c.get(url,params={'revision':0,'digest':controls['artifact_sha256']},headers=admin).status_code==409
    assert c.get(url,params={'revision':p['revision'],'digest':'a'*64},headers=admin).status_code==409
    assert c.get(url,params={'revision':p['revision'],'digest':controls['artifact_sha256']},headers={'Authorization':'Bearer two'}).status_code==403


def test_quality_receipt_tampering_and_owner_approval_binding_fail_closed(reviewers):
    import sqlite3,hashlib
    c=reviewers;p,path,controls=film(c);admin={'Authorization':'Bearer admin'};url='/creative/api/admin/learning/projects/'+p['id']
    own=c.post('/creative/api/projects/'+p['id']+'/review',json={'revision':p['revision'],'decision':'approved'}).json()
    assert own['reviews'][-1]['artifact_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert c.post(url+'/assessment',json=assessment(p,controls),headers=admin).status_code==200
    s=c.get('/creative/api/projects/'+p['id']+'/learning').json()
    assert s['independent_quality']['decision']=='passed' and not s['training_eligible']
    assert s['independent_quality']['mean_score']==4 and s['independent_quality']['min_score']==4
    with sqlite3.connect(store.DATA/'learning/episodes.sqlite3') as db:
        row=db.execute('SELECT seq,data FROM quality_reviews').fetchone();data=json.loads(row[1]);data['decision']='rejected'
        db.execute('UPDATE quality_reviews SET data=? WHERE seq=?',(json.dumps(data),row[0]))
    assert c.get(url,headers=admin).status_code==409
    assert c.get('/creative/api/projects/'+p['id']+'/learning').json()['independent_quality']['decision']=='integrity_failed'
