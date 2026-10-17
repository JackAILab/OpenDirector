import hashlib
import json
import sqlite3
from harness.learning import governance
from harness.studio import store
from test_creative_studio import client,ready


def completed(client):
    p=ready(client);p['state']='completed';p['artifact']='artifacts/final.mp4'
    path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'final')
    store.save(p,1);return p,path


def test_series_and_learning_permissions_are_owner_scoped(client):
    p=ready(client);path='/creative/api/projects/'+p['id']+'/learning'
    default=client.get(path).json()
    assert not default['training'] and not default['public_dataset'] and not default['training_eligible']
    s=client.post('/creative/api/learning/series',json={'label':'杯子系列'}).json()
    assert client.get('/creative/api/learning/series',headers={'Authorization':'Bearer two'}).json()==[]
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    foreign=client.post('/creative/api/learning/series',json={'label':'其他用户'},headers={'Authorization':'Bearer two'}).json()
    assert client.put(path+'/family',json={'revision':p['revision'],'series_id':foreign['id']}).status_code==404
    assigned=client.put(path+'/family',json={'revision':p['revision'],'series_id':s['id']}).json()
    assert assigned['family_id']==s['id']
    assert client.put(path+'/family',json={'revision':0,'series_id':None}).status_code==409
    assert client.get('/creative/api/projects/'+p['id']).json()['revision']==p['revision']


def test_mechanism_report_endpoint_is_session_scoped_and_sanitized(client):
    report=client.get('/creative/api/learning/mechanisms').json()
    assert report['schema']=='visualagent.ad-mechanism-report.v1'
    assert report['training_eligible'] is False
    assert 'source_item' not in json.dumps(report)
    assert client.get('/creative/api/learning/mechanisms',headers={'Authorization':'Bearer two'}).status_code==200


def test_consent_is_separate_revocable_and_bound_to_actual_artifact(client):
    p,path=completed(client);url='/creative/api/projects/'+p['id']+'/learning'
    approved=client.post('/creative/api/projects/'+p['id']+'/review',json={'revision':p['revision'],'decision':'approved'}).json()
    assert not approved['training_eligible'] and not client.get(url).json()['training']
    current=client.get(url).json();body={k:current[k] for k in ('revision','artifact_sha256','policy','policy_sha256')}
    body.update(training=True,public_dataset=False)
    r=client.post(url+'/consent',json=body)
    assert r.status_code==200 and r.json()['training'] and not r.json()['public_dataset']
    assert not r.json()['training_eligible']
    from harness.learning.episodes import record_artifact,inspect_episode
    record_artifact(p,1,path)
    observed=inspect_episode(p['id'],1)['revisions'][-1]
    assert observed['data_controls'][0]['training'] is True
    assert observed['training_eligible'] is False and 'independent_semantic_review' in observed['release_blockers']
    assert client.post(url+'/consent',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url+'/consent',json={**body,'revision':0}).status_code==409
    assert client.post(url+'/consent',json={**body,'policy':'different'}).status_code==409
    assert client.post(url+'/consent',json={**body,'policy_sha256':'a'*64}).status_code==409
    assert client.post(url+'/consent',json={**body,'training':'yes'}).status_code==422
    assert client.post(url+'/consent',json={**body,'training':False,'public_dataset':True}).status_code==409
    revoked=client.post(url+'/consent',json={**body,'training':False,'public_dataset':False}).json()
    assert not revoked['training']
    with sqlite3.connect(store.DATA/'learning/episodes.sqlite3') as c:
        assert c.execute("SELECT COUNT(*) FROM learning_controls WHERE kind='consent'").fetchone()[0]==2
    client.post(url+'/consent',json=body)
    path.write_bytes(b'changed-after-consent')
    assert not client.get(url).json()['training']
    assert client.post(url+'/consent',json=body).status_code==409
    assert all('changed-after' not in str(e) for e in client.get('/creative/api/projects/'+p['id']).json()['events'])


def test_consent_does_not_transfer_to_new_revision_or_unfinished_work(client):
    p,path=completed(client);url='/creative/api/projects/'+p['id']+'/learning'
    current=client.get(url).json();body={k:current[k] for k in ('revision','artifact_sha256','policy','policy_sha256')};body.update(training=True,public_dataset=True)
    assert client.post(url+'/consent',json=body).status_code==200
    p['revision']+=1;store.save(p,1)
    assert not client.get(url).json()['training']
    p['state']='ready';store.save(p,1)
    assert client.post(url+'/consent',json={**body,'revision':p['revision']}).status_code==409


def test_artifact_reference_cannot_escape_private_project_storage(client,tmp_path):
    p=ready(client);p['state']='completed';p['artifact']='/etc/hosts';store.save(p,1)
    assert client.get('/creative/api/projects/'+p['id']+'/learning').status_code==409
