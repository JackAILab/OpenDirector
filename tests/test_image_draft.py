"""Durable reference drafts must not generate or bypass project ownership."""
from test_creative_studio import client
from test_image_reframe import source
from harness.studio import store


def setup_draft(client):
    p,url,aid=source(client)
    saved=store.load(p['id'],1);saved['creation_mode']='image';store.save(saved,1)
    return p,url,{'revision':p['revision'],'model':'hunyuan-image-v2.0-general-edit','prompt':'保留主体与光线','references':[{'asset':aid,'role':'scene','instruction':'保留光线'}]}


def test_saved_draft_round_trip_no_generation(client):
    p,url,body=setup_draft(client)
    r=client.put(url+'/images/draft',json=body)
    assert r.status_code==200,r.text
    saved=client.get(url).json()
    assert saved['image_draft']=={k:v for k,v in body.items() if k!='revision'}
    assert saved['revision']==p['revision']+1
    assert saved.get('image_task')==p.get('image_task')
    assert client.app.state.test_account_limits['used']==0
    assert client.put(url+'/images/draft',json=body).status_code==409
    assert client.put(url+'/images/draft',json={**body,'revision':saved['revision']}).json()['revision']==saved['revision']
    assert client.put(url+'/images/draft',json=body,headers={'Authorization':'Bearer two'}).status_code==404


def test_invalid_references_and_busy_rejected(client):
    p,url,body=setup_draft(client)
    for refs in ([{**body['references'][0],'asset':'f'*32}],body['references']*2):
        assert client.put(url+'/images/draft',json={**body,'references':refs}).status_code==422
    assert client.put(url+'/images/draft',json={**body,'model':'unknown'}).status_code==422
    saved=store.load(p['id'],1);saved['image_task']={'state':'running'};store.save(saved,1)
    assert client.put(url+'/images/draft',json=body).status_code==409
    assert 'image_draft' not in client.get(url).json()
    assert client.app.state.test_account_limits['used']==0
