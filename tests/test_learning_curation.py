import json,sqlite3
from fastapi import HTTPException
import types
from harness.learning import curation,governance
from harness.studio import store
from harness.studio.learning_curation_api import install
from test_creative_studio import client,ready


def film(client):
    p=ready(client);p.update(state='completed',artifact='artifacts/curation/'+p['id']+'.mp4');path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'curation-film');store.save(p,1)
    s=client.get('/creative/api/projects/'+p['id']+'/learning').json();body={k:s[k] for k in ('revision','artifact_sha256','policy','policy_sha256')};client.post('/creative/api/projects/'+p['id']+'/learning/consent',json={**body,'training':True,'public_dataset':False});return p,path,client.get('/creative/api/projects/'+p['id']+'/learning').json()


def cbody(p,status,gate=True):return {'revision':p['revision'],'artifact_sha256':status['artifact_sha256'],'privacy_review':gate,'rights_review':gate,'sanitized_context_review':gate,'note':'逐项核对了授权范围、来源凭证和脱敏字段。'}

def test_curation_requires_independent_admin_and_all_gates(client):
    c=client;p,path,status=film(c)
    def admin(value):
        if value!='Bearer admin':raise HTTPException(403)
        return {'id':3}
    # The fixture already installs the admin route; the local helper is intentionally unused.
    url='/creative/api/admin/learning/projects/'+p['id']+'/curation';h={'Authorization':'Bearer admin'}
    assert c.post(url,json=cbody(p,status,True),headers=h).status_code==200
    got=c.get(url,headers=h).json();assert all(got['curation']['decisions'].values())
    assert c.post(url,json={**cbody(p,status,True),'privacy_review':'yes'},headers=h).status_code==422
    assert c.post(url,json={**cbody(p,status,False),'note':'太短'},headers=h).status_code==422
    assert c.post(url,json={**cbody(p,status,True),'revision':0},headers=h).status_code==409
    assert c.get(url,headers={'Authorization':'Bearer one'}).status_code==403
    with sqlite3.connect(store.DATA/'learning/episodes.sqlite3') as db:
      row=db.execute('select seq,data from curation_reviews').fetchone();data=json.loads(row[1]);data['decisions']['rights_review']=False;db.execute('update curation_reviews set data=? where seq=?',(json.dumps(data),row[0]))
    assert c.get(url,headers=h).status_code==409


def test_curation_digest_and_inventory_gate(client,tmp_path):
    p,path,status=film(client);url='/creative/api/projects/'+p['id']+'/learning';h={'Authorization':'Bearer one'}
    from harness.learning.inventory import prepare
    before=prepare(b'y'*32,tmp_path/'registry.sqlite','seed');assert before['summary']['evidence_tiers'].get('release_gate_complete',0)==0
    # The user cannot submit curator credentials through the owner endpoint.
    assert client.post(url+'/consent',json={**{k:status[k] for k in ('revision','artifact_sha256','policy','policy_sha256')},'training':True,'public_dataset':False}).status_code==200
    path.write_bytes(b'changed');assert client.get(url).json()['training'] is False
