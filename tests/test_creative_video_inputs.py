import asyncio
import base64
import hashlib
import io
import json
import pytest
from fastapi import FastAPI,Request
from PIL import Image
from tests.test_creative_studio import client,ready
from harness.studio import store
from harness.tools import creative_video_inputs as inputs
from harness.tools.creative_canvas import asset_directory
from harness.tools.creative_video import CreativeVideoTool,film_prompt,input_manifest,provider_trajectory_observation,provider_trajectory_view,provider_status_projection
from harness.models import kling_studio


def setup(c,count=3):
    p=ready(c);url='/creative/api/projects/'+p['id'];ids=[]
    for i in range(count):
        out=io.BytesIO();Image.new('RGB',(320,180),(i*30,50,80)).save(out,'PNG')
        r=c.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=out.getvalue()).json();p=r['project'];ids.append(r['asset']['id'])
    body=dict(revision=p['revision'],model='kling-video-v3_0_omni',mode='references',references=[dict(asset=a,role='product' if i==0 else 'scene',instruction=f'保留特征{i+1}') for i,a in enumerate(ids)])
    return p,url,body


def confirm(c,url,body):
    r=c.post(url+'/video-inputs/preview',json=body);assert r.status_code==200,r.text
    r=c.put(url+'/video-inputs',json={**body,'input_hash':r.json()['input_hash']});assert r.status_code==200,r.text
    return r.json()


def test_preview_save_version_mode_and_product_reconfirmation(client):
    p,url,body=setup(client);legacy=store.load(p['id'],1);legacy.update(generation_mode='segments',duration=10);store.save(legacy,1);before=client.get(url).json()
    preview=client.post(url+'/video-inputs/preview',json=body).json()
    assert client.get(url).json()==before
    assert preview['requires_plan'] and len(preview['references'])==3
    p=confirm(client,url,body);assert p['shots']==[] and p['model']=='kling-video-v3_0_omni' and 'run_id' not in p
    assert p['generation_mode']=='single_native' and p['duration']==15
    assert len(p['input_manifest']['images'])==3 and p['input_manifest']['image'] is None
    assert client.put(url+'/model',json={'revision':p['revision'],'model':'kling-video-v3_0'}).status_code==409
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    assert '图片1' in p['production_prompt'] and '软参考' in p['production_prompt']
    p2=store.load(p['id'],1);p2['brief']['product']='新的商品';store.save(p2,1)
    assert client.get(url).json()['video_inputs_needs_review']
    assert client.post(url+'/execute',json={'revision':p2['revision'],'approved_credits':12}).status_code==409
    after=confirm(client,url,{**body,'revision':p2['revision']});assert after['shots']==p['shots'] and not after['video_inputs_needs_review']
    assert all('保留特征' not in str(e) for e in after['events'])


def test_reject_owner_count_mode_duplicates_stale_and_changed_bytes(client):
    p,url,body=setup(client)
    assert client.post(url+'/video-inputs/preview',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    for edit in [dict(mode='first_last'),dict(model='kling-video-v3_0'),dict(references=body['references']*3),dict(references=[body['references'][0]]*2),dict(references=[dict(asset='f'*32,role='product',instruction='')]),dict(mode='text')]:
        assert client.post(url+'/video-inputs/preview',json={**body,**edit}).status_code==422
    assert client.post(url+'/video-inputs/preview',json={**body,'revision':0}).status_code==409
    frozen=client.post(url+'/video-inputs/preview',json=body).json()
    assert client.put(url+'/video-inputs',json={**body,'input_hash':'0'*64}).status_code==409
    asset=p['canvas_assets'][body['references'][0]['asset']];path=asset_directory(p,asset['id'])/asset['filename']
    Image.new('RGB',(320,180),'red').save(path,'JPEG')
    assert client.put(url+'/video-inputs',json={**body,'input_hash':frozen['input_hash']}).status_code==409
    assert client.get(url).json()['revision']==p['revision']


@pytest.mark.parametrize('model,mode,count,task,tail',[('kling-video-v3_0','first_frame',1,'fl2va',False),('kling-video-v3_0','first_last',2,'fl2va',True),('kling-video-v3_0_omni','references',7,'ref2va',False)])
def test_actual_tool_to_worker_preserves_inputs_and_one_request(client,tmp_path,monkeypatch,model,mode,count,task,tail):
    p,url,body=setup(client,count);body.update(model=model,mode=mode);p=confirm(client,url,body)
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json();p['run_id']='fixed_run'
    seen=[];app=FastAPI();monkeypatch.setattr(kling_studio,'OUTPUT_DIR',tmp_path/'worker')
    @app.post('/v1/videos')
    async def submit(request:Request):
        raw=await request.body();assert len(raw)<1_048_576
        payload=json.loads(raw);args=kling_studio.generation_args(payload);seen.append((payload,args))
        assert request.headers['idempotency-key']=='fixed_run-film'
        return {'id':'fixed_job'}
    result=asyncio.run(CreativeVideoTool(app,'Bearer local').submit_film(p));assert result['id']=='fixed_job' and len(seen)==1
    payload,args=seen[0];assert payload['task']==task and len(payload['conditions'])==count
    assert ('--tailImage' in args)==tail and args.count('--image')==(1 if tail else count)
    assert args[args.index('--model')+1]==model and args[args.index('--poll')+1]=='0'
    digests=[hashlib.sha256(base64.b64decode(c['uri'].split(',')[1])).hexdigest() for c in payload['conditions']]
    assert digests==[r['transport_sha256'] for r in p['video_inputs']['references']]
    assert payload['enable_audio'] and payload['prefer_multi_shots']


def test_worker_refuses_mixed_modes_remote_urls_and_extra_images(client,tmp_path,monkeypatch):
    p,url,body=setup(client);p=confirm(client,url,body);conditions=inputs.conditions(p);monkeypatch.setattr(kling_studio,'OUTPUT_DIR',tmp_path/'worker')
    base=dict(model=p['model'],task='ref2va',prompt='product',conditions=conditions,target={'duration_seconds':15})
    for delta in [dict(model='kling-video-v3_0'),dict(task='fl2va'),dict(conditions=conditions*3),dict(conditions=[{**conditions[0],'index':2}]),dict(conditions=[{**conditions[0],'uri':'https://private.invalid/image'}]),dict(conditions=[{**conditions[0],'frame_index':0}])]:
        with pytest.raises(Exception) as caught:kling_studio.generation_args({**base,**delta})
        assert caught.value.status_code==422


def test_saved_source_mutation_blocks_before_paid_submit_and_legacy_reset(client,monkeypatch):
    p,url,body=setup(client);p=confirm(client,url,body);p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    asset=p['canvas_assets'][body['references'][0]['asset']];path=asset_directory(p,asset['id'])/asset['filename'];Image.new('RGB',(320,180),'yellow').save(path,'JPEG')
    assert client.post(url+'/execute',json={'revision':p['revision'],'approved_credits':12}).status_code==409
    with pytest.raises(ValueError):inputs.conditions(p)
    r=client.post(url+'/reference',params={'revision':p['revision'],'source_asset':asset['id']});assert r.status_code==200
    assert 'video_inputs' not in r.json() and len(r.json()['input_manifest']['images'])==1
    assert r.json()['input_manifest']['mode']=='references'  # O3 legacy image is still a soft reference.


def test_director_receives_actual_images_and_roles(client,monkeypatch):
    from harness.agents import creative_director
    from harness.library import learning,mechanism_report
    p,url,body=setup(client);p=confirm(client,url,body);seen=[]
    async def complete(self,messages):
        seen.append(messages[-1]['content']);return {'reply':'方案','shots':[{'title':'展示','prompt':'product','audio_prompt':'music','caption':'细节','rationale':'展示'}]*3}
    monkeypatch.setattr(creative_director.CreativeDirectorModel,'complete',complete);monkeypatch.setattr(creative_director,'compact',lambda:{})
    monkeypatch.setattr(mechanism_report,'build_mechanism_report',lambda _:{});monkeypatch.setattr(learning,'strategy_candidates',lambda *args:[])
    asyncio.run(creative_director.direct(p,'plan'));assert sum(i['type']=='image_url' for i in seen[0])==3
    context=json.loads(seen[0][0]['text']);assert '图片3' in context['video_input_selection'] and '软语义' in context['reference_policy']


def test_runner_freezes_actual_input_manifest_before_submit_and_preserves_on_resume(client,tmp_path,monkeypatch):
    from harness.core import creative_runner as runner
    p,url,body=setup(client);p=confirm(client,url,body);p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    p['run_id']='frozen-inputs';store.save(p,1);expected=input_manifest(p);calls=[]
    monkeypatch.setattr(runner,'DATA',tmp_path)
    class Video:
        def __init__(self,*args):pass
        async def submit_film(self,project):
            assert store.load(p['id'],1)['film']['inputs']==expected
            calls.append('submit');return {'id':'fixed-input-job'}
        async def status(self,job):
            calls.append('query');raise RuntimeError('temporary query interruption')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    asyncio.run(runner.production(None,p,1,'unused'));p=store.load(p['id'],1)
    assert p['state']=='paused' and p['film']['inputs']==expected
    monkeypatch.setattr('harness.tools.creative_video.input_manifest',lambda _: {'unexpected':'new inputs'})
    asyncio.run(runner.production(None,p,1,'unused'));p=store.load(p['id'],1)
    assert calls==['submit','query','query'] and p['film']['inputs']==expected
    p['artifact']='fixed-fixture/final.mp4'
    store.archive_render(p);assert p['versions'][-1]['input_manifest']==expected


def test_provider_trajectory_observation_discards_raw_coordinates_and_payload():
    status={'status':'completed','signed_url':'https://provider.invalid/secret',
            'trajectory':{'shots':[{'id':'main','duration':5,'points':[[1,2,3],[4.123456789,5,6]],
                                   'closed':True,'easing':'smooth','private_note':'drop me'}]},
            'raw_payload':'must never persist'}
    observed=provider_trajectory_observation(status)
    assert observed and observed['source']=='provider_status'
    row=observed['shots'][0]
    assert row['shot_id']=='main' and row['path_points']==2 and row['path_closed'] is True
    assert 'points' not in row and 'private_note' not in row and 'signed_url' not in str(observed)
    assert 'raw_payload' not in str(observed)
    assert provider_trajectory_view(observed)==observed
    projection=provider_status_projection(status)
    assert projection['status']=='completed' and projection['trajectory_observed'] is True
    assert 'signed_url' not in str(projection) and 'raw_payload' not in str(projection)
    assert provider_trajectory_observation({'status':'completed','trajectory':{'shots':[{'id':'bad','points':[[float('inf'),0,0]]}]}}) is None


def test_product_photo_omni_keeps_image_ratio_and_vertical_video_target(client, tmp_path, monkeypatch):
    """Product reference framing and the final video canvas are separate inputs."""
    monkeypatch.setattr(kling_studio,'OUTPUT_DIR',tmp_path/'worker')
    p=client.post('/creative/api/projects',json={
        'message':'夹克商品参考，竖屏展示', 'model':'kling-video-v3_0_omni', 'aspect':'9:16'
    }).json()
    url='/creative/api/projects/'+p['id']
    image=Image.new('RGB',(585,407),'#28405a');raw=io.BytesIO();image.save(raw,'PNG')
    upload=client.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=raw.getvalue())
    assert upload.status_code==200
    uploaded=upload.json();p=uploaded['project'];aid=uploaded['asset']['id']
    source=client.get(url+'/canvas/assets/'+aid+'/source');assert source.status_code==200
    decoded=Image.open(io.BytesIO(source.content));assert decoded.size==image.size and decoded.tobytes()==image.tobytes()
    selection=dict(revision=p['revision'],model=p['model'],mode='references',references=[dict(asset=aid,role='product',instruction='保留可见结构')])
    # Identical source cannot be silently treated as a matching vertical first frame.
    incompatible=client.post(url+'/video-inputs/preview',json={**selection,'model':'kling-video-v3_0','mode':'first_frame'})
    assert incompatible.status_code==422
    p=confirm(client,url,selection)
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json();p['run_id']='separate-image-and-frame'
    received=[];app=FastAPI()
    @app.post('/v1/videos')
    async def receive(request:Request):
        payload=await request.json();args=kling_studio.generation_args(payload);received.append((payload,args))
        return {'id':'fixture-only'}
    asyncio.run(CreativeVideoTool(app,'Bearer fixture').submit_film(p))
    assert len(received)==1
    payload,args=received[0];assert payload['task']=='ref2va'
    assert payload['target']['aspect_ratio']=='9:16' and payload['target']['duration_seconds']==15
    assert payload['model']=='kling-video-v3_0_omni' and payload['enable_audio']
    condition=payload['conditions'][0];assert condition['role']=='reference' and condition['index']==1 and 'frame_index' not in condition
    transported=base64.b64decode(condition['uri'].split(',')[1]);picture=Image.open(io.BytesIO(transported))
    assert picture.size==(585,407)
    assert hashlib.sha256(transported).hexdigest()==p['video_inputs']['references'][0]['transport_sha256']
    assert args.count('--image')==1 and '--tailImage' not in args
    assert args[args.index('--aspect_ratio')+1]=='9:16'
    assert p['training_eligible'] is False


def test_manual_draft_atomic_review_and_confirmation(client):
    p=client.post('/creative/api/projects',json={'message':'原始画面提示词','creation_mode':'video','model':'kling-video-v4_0','duration':25}).json()
    url='/creative/api/projects/'+p['id']
    body=dict(revision=p['revision'],model='kling-video-v3_0',mode='text',references=[],manual=dict(prompt='新的画面提示词',duration=5))
    reviewed=client.post(url+'/video-inputs/preview',json=body)
    assert reviewed.status_code==200,reviewed.text
    assert client.get(url).json()['duration']==25
    tampered={**body,'manual':dict(prompt='核对后更换提示词',duration=5),'input_hash':reviewed.json()['input_hash']}
    assert client.put(url+'/video-inputs',json=tampered).status_code==409
    saved=client.put(url+'/video-inputs',json={**body,'input_hash':reviewed.json()['input_hash']}).json()
    assert saved['duration']==5 and saved['direct_prompt']=='新的画面提示词'
    assert saved['shots'][0]['duration']==5 and saved['model']=='kling-video-v3_0'
    inputs.validate(store.load(p['id'],1))
    pending=store.load(p['id'],1);pending.update(state='paused',film={'state':'generating','job_id':'fixture-job'});store.save(pending,1)
    assert client.post(url+'/video-inputs/preview',json={**body,'revision':saved['revision']}).status_code==409
