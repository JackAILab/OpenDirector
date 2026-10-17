import asyncio
import time
from harness.studio import api,store
from harness.tools.creative_video import input_manifest
from test_creative_studio import client,ready


def test_background_planning_is_single_submit_and_owner_scoped(client,monkeypatch):
    original=api.direct;calls=[]
    async def slow(p,mode):
        calls.append(p['id']);await asyncio.sleep(.2);return await original(p,mode)
    monkeypatch.setattr(api,'direct',slow)
    p=client.post('/creative/api/projects',json={'message':'新产品广告'}).json();path='/creative/api/projects/'+p['id']
    body={'revision':0,'text':'完善声音','mode':'plan','background':True,'request_id':'a'*32}
    started=client.post(path+'/message',json=body).json()
    assert started['state']=='planning'
    assert client.post(path+'/message',json=body).status_code==200
    assert client.post(path+'/message',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(path+'/message',json={**body,'request_id':'b'*32,'revision':1}).status_code==409
    for _ in range(100):
        result=client.get(path).json()
        if result['state']!='planning':break
        time.sleep(.02)
    assert result['state']=='ready' and len(calls)==1
    assert sum(m['content']=='完善声音' for m in result['messages'])==1


def test_legacy_reference_requires_current_product_confirmation(client):
    p=ready(client);path='/creative/api/projects/'+p['id']
    stored=store.load(p['id'],1);stored['reference']={'id':'a'*32};store.save(stored,1)
    current=client.get(path).json();assert current['reference_needs_review']
    assert client.post(path+'/execute',json={'revision':p['revision'],'approved_credits':100}).status_code==409
    body={'revision':p['revision'],'reference_id':'a'*32}
    assert client.post(path+'/reference/confirm',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    result=client.post(path+'/reference/confirm',json=body).json()
    assert result['reference_needs_review'] is False
    assert result['reference_product']==result['brief']['product']
    assert client.post(path+'/reference/confirm',json=body).status_code==409


def test_manifest_distinguishes_director_from_actual_model_inputs():
    p={'reference':{'id':'r'},'canvas':{'nodes':[{'id':'n','kind':'video','asset':'v'}],
        'edges':[{'source':'n','target':'director'}]},'shots':[{'id':'s','start':0,'duration':15}]}
    m=input_manifest(p)
    assert m['request_count']==1 and m['image']['id']=='r'
    assert m['video']==m['audio']==m['element_ids']==[]
    assert m['director_only'][0]['asset']=='v' and m['beats'][0]['image_id']=='r'


def test_real_gpt_is_not_codebuddy_alias(monkeypatch):
    from harness.models.studio_image import image_models,generate
    monkeypatch.delenv('CREATIVE_GPT_IMAGE_ENABLED',raising=False)
    gpt=next(m for m in image_models() if m['id']=='gpt-image-2')
    assert not gpt['available'] and 'GPT' in gpt['label']
    import pytest
    with pytest.raises(RuntimeError,match='不会改用其他模型'):
        generate('gpt-image-2','test','16:9','/unused')
