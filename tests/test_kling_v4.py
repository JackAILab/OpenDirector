"""No paid calls. New-model routing and ambiguity must fail closed."""
from contextlib import contextmanager
import pytest
from harness.models import kling_omni, kling_studio
from harness.models.video_catalog import model_spec
from tests.test_creative_studio import client


def request():
    return kling_studio.generation_args({'model':kling_omni.MODEL,'task':'t2va','prompt':'a red shoe rotating',
        'target':{'duration_seconds':15,'aspect_ratio':'9:16'},'enable_audio':True,'prefer_multi_shots':True})


def discovery():
    values=kling_omni.provider_arguments(request(),[])['arguments']
    return {'body':{'availableModels':{'omni_ref_video':{'models':[{'model':kling_omni.MODEL,
        'arguments':[{'name':v['name'],'allowedValues':[v['value']]} for v in values],'inputs':[]}]}}}}


def test_v4_exact_route_no_legacy_audio_flags():
    args=request();assert args['task']=='omni_v4'
    payload=kling_omni.provider_arguments(args,['https://example.test/reference'])
    assert payload['model']=='kling-video-v4_0'
    assert payload['inputs'][0]['name']=='image_1'
    assert dict((v['name'],v['value']) for v in payload['arguments'])['prefer_multi_shots']=='true'
    assert model_spec('kling')['id']=='kling-video-v4_0'
    assert model_spec('kling','kling-video-v3_0_omni')['id']=='kling-video-v3_0_omni'


def test_paid_timeout_never_retries_or_falls_back(monkeypatch):
    calls=[]
    @contextmanager
    def connection():
        def call(tool,args):
            calls.append((tool,args['model']))
            raise TimeoutError()
        yield call,None
    monkeypatch.setattr(kling_omni,'connection',connection)
    with pytest.raises(RuntimeError,match='待核对'):
        kling_omni.submit(request(),lambda _:discovery(),'kling')
    assert calls==[('omni_ref_video','kling-video-v4_0')]


def test_removed_model_blocks_before_paid_call(monkeypatch):
    monkeypatch.setattr(kling_omni,'connection',lambda:pytest.fail('must not submit'))
    with pytest.raises(kling_omni.PreflightError):
        kling_omni.submit(request(),lambda _:{'body':{'availableModels':{'omni_ref_video':{'models':[]}}}},'kling')


def test_direct_video_creates_reviewable_plan_without_director_or_payment(client):
    p=client.post('/creative/api/projects',json={'message':'a red shoe rotating','creation_mode':'video'}).json()
    assert p['model']=='kling-video-v4_0' and p['state']=='ready'
    assert p['shots'][0]['prompt']=='a red shoe rotating' and p['quote']['credits']==12
    assert 'advertisement' not in p['production_prompt']
    assert not p['training_eligible'] and not p.get('film')
    assert client.get('/creative/api/projects/'+p['id'],headers={'Authorization':'Bearer two'}).status_code==404
    body={'revision':p['revision'],'model':p['model'],'mode':'text','references':[]}
    preview=client.post('/creative/api/projects/'+p['id']+'/video-inputs/preview',json=body).json()
    changed=client.put('/creative/api/projects/'+p['id']+'/video-inputs',json={**body,'input_hash':preview['input_hash']}).json()
    assert not preview['requires_plan'] and changed['state']=='ready'
    assert changed['shots'][0]['prompt']=='a red shoe rotating'
    assert not changed.get('film')


def test_manual_video_prompt_update_stays_direct(client):
    p=client.post('/creative/api/projects',json={'message':'a red shoe rotating','creation_mode':'video'}).json()
    base='/creative/api/projects/'+p['id']
    changed=client.patch(base+'/manual-prompt',json={'revision':p['revision'],'prompt':'A blue shoe on a rotating platform'}).json()
    assert changed['state']=='ready' and changed['creation_mode']=='video'
    assert changed['shots'][0]['prompt']=='A blue shoe on a rotating platform'
    assert len(changed['messages'])==1 and not changed.get('film')
    assert client.post(base+'/message',json={'revision':changed['revision'],'text':'plan it'}).status_code==409
    assert client.patch(base+'/manual-prompt',json={'revision':p['revision'],'prompt':'stale prompt'}).status_code==409
