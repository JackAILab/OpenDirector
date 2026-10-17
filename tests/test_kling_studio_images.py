from contextlib import contextmanager
import json
import pytest
from harness.models import kling_studio_image as adapter
from tests.test_creative_studio import client

@pytest.mark.parametrize('model',[m[0] for m in adapter.MODELS])
def test_text_and_reference_modes_keep_exact_model(model):
    tool,body=adapter.arguments(model,'a cat','16:9',[])
    assert tool=='text_to_image' and body['model']==model and body['inputs']==[]
    count=2 if model.endswith('v2_1') else 1
    tool,body=adapter.arguments(model,'edit cat','1:1',['memory-url']*count)
    assert tool=='image_to_image' and body['model']==model
    assert body['inputs'][0]['name']==('subject_image_0' if count==2 else 'image_1')
    assert {a['name']:a['value'] for a in body['arguments']}['imageCount']=='1'
    if count==2:assert 'img_resolution' not in {a['name'] for a in body['arguments']}


def test_image_21_one_reference_rejected():
    with pytest.raises(ValueError):adapter.arguments('kling-image-v2_1','edit','1:1',['ref'])


def test_uncertain_paid_submit_is_not_retried(monkeypatch,tmp_path):
    tool,body=adapter.arguments('kling-image-o1','a cat','1:1',[])
    monkeypatch.setattr(adapter,'cli',lambda _: {'body':{'availableModels':{tool:{'models':[{'model':body['model'],'arguments':body['arguments'],'inputs':[]}]}}}})
    calls=[]
    @contextmanager
    def connection():
        def call(name,args):
            calls.append((name,args['model']));raise TimeoutError()
        yield call,None
    monkeypatch.setattr(adapter,'connection',connection)
    with pytest.raises(RuntimeError,match='不会自动重试'):
        adapter.generate(body['model'],'a cat','1:1',tmp_path/'attempt',[])
    assert calls==[('text_to_image','kling-image-o1')]
    record=json.loads((tmp_path/'attempt/attempt.json').read_text())
    assert record['state']=='uncertain' and not record['training_eligible']
    assert 'prompt' not in record


def test_manual_image_never_enters_director(client):
    p=client.post('/creative/api/projects',json={'message':'a cat playing with a tiger','creation_mode':'image','image_model':'kling-image-o1'}).json()
    assert p['creation_mode']=='image' and p['image_model']=='kling-image-o1'
    assert p['direct_prompt']=='a cat playing with a tiger' and p['shots']==[]
    response=client.post('/creative/api/projects/'+p['id']+'/message',json={'revision':p['revision'],'text':'start','mode':'interview'})
    assert response.status_code==409
    loaded=client.get('/creative/api/projects/'+p['id']).json()
    assert loaded['revision']==p['revision'] and len(loaded['messages'])==1
    body={'revision':p['revision'],'model':'kling-image-o1','prompt':p['direct_prompt'],'references':[],'connect_to_director':False}
    result=client.post('/creative/api/projects/'+p['id']+'/images/preview',json=body)
    assert result.status_code==200,result.text
    assert client.post('/creative/api/projects/'+p['id']+'/images/preview',json={**body,'connect_to_director':True}).status_code==422
