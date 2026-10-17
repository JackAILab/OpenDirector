import asyncio
import copy
import json
import time
import pytest
from tests.test_creative_studio import client,ready
from tests.test_scene_shots import png
from harness.studio import store
from harness.core import creative_scene_runner as runner
from harness.tools.creative_scene import default_scene,scene_hash
from harness.tools.creative_scene_observe import SceneSuggestionRequest,observe_scene
from harness.evaluators.creative_scene import evaluate_scene_proposal


def request(spec,revision=2):
    return dict(revision=revision,request_id='1'*32,scene_hash=scene_hash(spec),intent='主光移到左侧，新增细节镜头',
                selected_object='bottle',selected_shot='main',frames=[dict(kind='camera',shot_id='main',at=0,png=png())])


def proposal(spec):
    next=copy.deepcopy(spec);next['objects'][4]['position'][0]=-3
    shot=copy.deepcopy(next['shots'][0]);shot.update(id='detail',name='细节',duration=3);shot['camera'].update(fov=25,points=[[0,2,5],[0,2,3]],closed=False)
    next['shots'].append(shot);next['duration']+=3
    return dict(spec=next,summary='左侧主光并加入细节推进',reasons=[dict(text='主体位于中心，补上近景角度供核对。',views=['view_1'])])


def prepare(client):
    p=ready(client);base='/creative/api/projects/'+p['id']+'/scene3d'
    saved=client.put(base,json=dict(revision=p['revision'],spec=default_scene())).json()
    return p,base,saved,request(saved['spec'],saved['revision'])


def wait(client,path):
    for _ in range(200):
        job=client.get(path).json()
        if job['state']!='running':return job
        time.sleep(.01)
    pytest.fail('scene suggestion did not finish')


def test_observation_bounds_selection_and_metadata():
    spec=default_scene();body=request(spec);views=observe_scene(spec,SceneSuggestionRequest(**body))
    assert views[0]['image'].startswith('data:image/jpeg;base64,') and not views[0]['verified_render']
    bads=[dict(selected_object='foreign'),dict(selected_shot='foreign'),dict(intent=' '),
          dict(frames=[dict(kind='camera',shot_id='main',at=11,png=png())]),
          dict(frames=[dict(kind='camera',shot_id='main',at=0,png=png(size=(180,320)))]),
          dict(frames=[dict(kind='camera',shot_id='main',at=0,png='invalid')])]
    for delta in bads:
        with pytest.raises(ValueError):observe_scene(spec,SceneSuggestionRequest(**dict(body,**delta)))


def test_evaluator_computes_real_changes_and_protects_assets():
    spec=default_scene();views=observe_scene(spec,SceneSuggestionRequest(**request(spec)))
    good=evaluate_scene_proposal(proposal(spec),spec,{},views)
    assert any(c['label']=='主光 · 位置' and c['after']==[-3,5,3] for c in good['changes'])
    assert 'image' not in good['observations'][0] and not good['qa']['training_eligible']
    bad=proposal(spec);bad['reasons'][0]['views']=['unknown']
    with pytest.raises(ValueError):evaluate_scene_proposal(bad,spec,{},views)
    for mutate in ('unknown_asset','remove','material'):
        original=copy.deepcopy(spec);original['objects'][2].update(kind='glb',asset='a'*32)
        bad=proposal(original)
        if mutate=='unknown_asset':bad['spec']['objects'][2]['asset']='b'*32
        elif mutate=='remove':bad['spec']['objects'].pop(2)
        else:bad['spec']['objects'][2]['roughness']=.9
        with pytest.raises(ValueError):evaluate_scene_proposal(bad,original,{'a'*32:{}},views)


def test_suggestion_single_attempt_private_and_never_applied(client,monkeypatch):
    p,base,saved,body=prepare(client);calls=[]
    async def propose(spec,observations,intent,selection):
        calls.append((observations,selection));await asyncio.sleep(.1);return proposal(spec)
    monkeypatch.setattr(runner,'propose_scene',propose)
    before=store.load(p['id'],1);r=client.post(base+'/suggestions',json=body);assert r.status_code==200,r.text
    assert client.put(base,json=dict(revision=saved['revision'],spec=saved['spec'])).status_code==409
    assert client.post(base+'/suggestions',json=body).json()['id']==body['request_id']
    path=base+'/suggestions/'+body['request_id'];job=wait(client,path);assert job['state']=='completed' and len(calls)==1
    after=store.load(p['id'],1)
    assert after['scene3d']==before['scene3d'] and after['shots']==before['shots'] and after['revision']==before['revision']
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(base+'/suggestions',json=dict(body,intent='changed')).status_code==409
    assert client.post(base+'/suggestions',json=body).status_code==200 and len(calls)==1
    assert client.get(base).json()['suggestion']['result']==job['result']
    serialized=json.dumps(after);assert 'data:image' not in serialized and body['frames'][0]['png'] not in serialized
    events=json.dumps(store.present(after)['events']);assert body['intent'] not in events and 'position' not in events
    assert client.put(base,json=dict(revision=saved['revision'],spec=job['result']['spec'])).status_code==200
    assert client.get(path).json()['stale'] is True


def test_invalid_requests_never_call_model(client,monkeypatch):
    p,base,saved,body=prepare(client);calls=[]
    async def propose(*args):calls.append(1);raise RuntimeError()
    monkeypatch.setattr(runner,'propose_scene',propose)
    for delta,status in [(dict(revision=0),409),(dict(scene_hash='0'*64),409),(dict(selected_object='foreign'),422),(dict(intent=' '),422)]:
        assert client.post(base+'/suggestions',json=dict(body,**delta)).status_code==status
    assert client.post(base+'/suggestions',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    current=store.load(p['id'],1);current['image_task']={'state':'running'};store.save(current,1)
    assert client.post(base+'/suggestions',json=body).status_code==409
    assert calls==[]


def test_failure_and_interruption_do_not_retry_or_expose_provider_data(client,monkeypatch):
    p,base,saved,body=prepare(client);calls=[]
    async def fail(*args):calls.append(1);raise RuntimeError('secret-provider-payload')
    monkeypatch.setattr(runner,'propose_scene',fail)
    client.post(base+'/suggestions',json=body);job=wait(client,base+'/suggestions/'+body['request_id'])
    assert job['state']=='failed' and 'secret-provider' not in json.dumps(job)
    assert client.post(base+'/suggestions',json=body).json()['state']=='failed' and len(calls)==1
    current=store.load(p['id'],1);current['scene_suggestions'][body['request_id']]['state']='running';store.save(current,1)
    assert client.get(base).json()['suggestion']['state']=='interrupted' and len(calls)==1
    assert store.load(p['id'],1)['scene3d']==saved['spec']


def test_actual_agent_sends_scene_selection_and_observed_images_once(monkeypatch):
    from harness.agents.creative_scene_director import propose_scene,CreativeDirectorModel
    calls=[]
    async def complete(self,messages):calls.append(messages);return {'fixed':True}
    monkeypatch.setattr(CreativeDirectorModel,'complete',complete)
    spec=default_scene();views=observe_scene(spec,SceneSuggestionRequest(**request(spec)))
    output=asyncio.run(propose_scene(spec,views,'左侧主光',dict(object='bottle',shot='main')))
    assert output=={'fixed':True} and len(calls)==1
    info=json.loads(calls[0][1]['content'][0]['text']);assert info['scene']==spec and info['selection']['object']=='bottle'
    assert calls[0][1]['content'][-1]['image_url']['url'].startswith('data:image/jpeg;base64,')
