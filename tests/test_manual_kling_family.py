"""Manual workspaces must keep their model/duration and never ask the director."""
from contextlib import contextmanager
import pytest
from tests.test_creative_studio import client
from harness.models import kling_manual, kling_studio
from harness.models.video_catalog import MANUAL_DURATIONS
from harness.studio import store


@pytest.mark.parametrize('model,durations',MANUAL_DURATIONS.items())
def test_manual_model_duration_and_agent_boundary(client,model,durations):
    p=client.post('/creative/api/projects',json={'message':'cat playing near a tiger','creation_mode':'video','model':model,'duration':durations[-1]})
    assert p.status_code==200,p.text
    p=p.json();assert p['model']==model and p['duration']==durations[-1]
    assert len(p['shots'])==1 and p['shots'][0]['duration']==durations[-1]
    assert client.post('/creative/api/projects/'+p['id']+'/message',json={'revision':0,'text':'more'}).status_code==409
    if model in ('kling-video-v2_5','kling-video-v2_6','kling-video-o1'):
        assert client.post('/creative/api/projects',json={'message':'cat playing','creation_mode':'video','model':model,'duration':15}).status_code==422
    if model in ('kling-video-v2_5','kling-video-v2_6','kling-video-o1','kling-video-v3_0_turbo'):
        assert client.post('/creative/api/projects',json={'message':'cat playing','creation_mode':'agent','model':model}).status_code==422


def test_repeat_manual_send_keeps_history_but_clears_original_task(client):
    p=client.post('/creative/api/projects',json={'message':'same prompt','creation_mode':'video'}).json()
    current=store.load(p['id'],1);current.update(state='completed',artifact='old/final.mp4',run_id='oldrun',film={'job_id':'oldjob','state':'completed'},qa={'technical':'passed'});store.save(current,1)
    changed=client.patch('/creative/api/projects/'+p['id']+'/manual-prompt',json={'revision':p['revision'],'prompt':'same prompt','model':'kling-video-v2_6','duration':10})
    assert changed.status_code==200,changed.text
    changed=changed.json();assert changed['state']=='ready' and changed['duration']==10
    assert not changed.get('film') and not changed.get('run_id') and not changed.get('artifact')
    assert changed['versions'][0]['artifact']=='old/final.mp4'


def args(model):
    return kling_studio.generation_args({'task':'t2va','prompt':'cat playing','model':model,'target':{'duration_seconds':5},'enable_audio':model=='kling-video-v2_6'})


def spec(request):
    return {'model':request['model'],'inputs':[],'arguments':[{'name':name,'allowedValues':values} for name,values in [('prompt',None),('duration',['5','10']),('resolution',['720p','1080p']),('imageCount',['1']),('aspect_ratio',['16:9']),*([('enable_audio',['true','false'])] if request['model']=='kling-video-v2_6' else [])]]}


@pytest.mark.parametrize('model',['kling-video-v2_6','kling-video-o1','kling-video-v3_0_turbo'])
def test_legacy_model_routes_without_unsupported_flags(model,monkeypatch):
    request=args(model);assert request['task']=='manual_family'
    body=kling_manual.payload(request,spec(request),[])
    values={v['name']:v['value'] for v in body['arguments']}
    assert 'prefer_multi_shots' not in values
    assert ('enable_audio' in values)==(model=='kling-video-v2_6')
    calls=[]
    @contextmanager
    def connect():
        def call(tool,payload):calls.append((tool,payload['model']));raise TimeoutError()
        yield call,None
    monkeypatch.setattr(kling_manual,'connection',connect)
    discovery={'body':{'availableModels':{'text_to_video':{'models':[spec(request)]}}}}
    with pytest.raises(RuntimeError,match='待核对'):kling_manual.submit(request,lambda _:discovery,'kling')
    assert calls==[('text_to_video',model)]


def test_missing_capability_prevents_payment(monkeypatch):
    monkeypatch.setattr(kling_manual,'connection',lambda:pytest.fail('No paid call permitted'))
    with pytest.raises(kling_manual.PreflightError):
        kling_manual.submit(args('kling-video-o1'),lambda _:{'body':{'availableModels':{'text_to_video':{'models':[]}}}},'kling')


@pytest.mark.parametrize('film',[{'job_id':'pendingjob','state':'submitted'},{'state':'submitting'}])
def test_uncertain_existing_task_cannot_be_overwritten(client,film):
    p=client.post('/creative/api/projects',json={'message':'same prompt','creation_mode':'video'}).json()
    current=store.load(p['id'],1);current.update(state='interrupted',film=film);store.save(current,1)
    changed=client.patch('/creative/api/projects/'+p['id']+'/manual-prompt',json={'revision':p['revision'],'prompt':'new prompt'})
    assert changed.status_code==409
    assert store.load(p['id'],1)['film']==film


def test_manual_output_accepts_silent_model_but_rejects_truncated_video(monkeypatch):
    from harness.tools import creative_render
    meta={'streams':[{'codec_type':'video','width':1280,'height':720}], 'format':{'duration':'10'}}
    monkeypatch.setattr(creative_render,'probe',lambda _:meta)
    qa=creative_render.verify_manual_video('fixture.mp4',10)
    assert qa['technical']=='passed' and qa['audio'] is False
    assert qa['semantic']==qa['human']=='pending' and qa['training_eligible'] is False
    meta['format']['duration']='3'
    with pytest.raises(RuntimeError):creative_render.verify_manual_video('fixture.mp4',10)


def test_manual_runner_returns_unchanged_provider_media(client,monkeypatch,tmp_path):
    import asyncio
    from harness.core import creative_runner
    from harness.learning import episodes
    p=client.post('/creative/api/projects',json={'message':'cat playing','creation_mode':'video','model':'kling-video-v2_5','duration':5}).json()
    p=store.load(p['id'],1);p.update(run_id='manual-fixture',state='running');store.save(p,1)
    calls=[]
    class Tool:
        async def submit_film(self,project):calls.append(project['model']);return {'id':'fixture-job'}
        async def status(self,job):return {'status':'completed'}
        async def download(self,job,path):path.write_bytes(b'provider-media-unchanged')
    monkeypatch.setattr(creative_runner,'DATA',tmp_path)
    monkeypatch.setattr(creative_runner,'CreativeVideoTool',lambda *args:Tool())
    monkeypatch.setattr(creative_runner,'verify_manual_video',lambda *args:{'technical':'passed','audio':False,'semantic':'pending','human':'pending','training_eligible':False})
    monkeypatch.setattr(creative_runner,'render',lambda *args:pytest.fail('Manual output must not render an Agent advertisement'))
    monkeypatch.setattr(episodes,'record_artifact',lambda *args:None)
    asyncio.run(creative_runner.production_film(None,p,1,'Bearer one'))
    saved=store.load(p['id'],1)
    assert saved['state']=='completed' and saved['training_eligible'] is False
    assert (tmp_path/saved['artifact']).read_bytes()==b'provider-media-unchanged'
    assert calls==['kling-video-v2_5']
