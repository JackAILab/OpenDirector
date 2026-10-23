"""Web Agent lifecycle: budget, ownership, sequential continuity and safe recovery."""
import asyncio
from copy import deepcopy
import pytest
from test_creative_studio import client
from harness.studio import api, store
from harness.tools import creative_campaign as actions
from harness.core import creative_campaign_runner as runner


def ready(client, duration=60):
    created=client.post('/creative/api/projects',json=dict(message='商品广告',duration=duration,model='kling-video-v4_0'))
    assert created.status_code==200,created.text
    p=created.json()
    result=client.post('/creative/api/projects/'+p['id']+'/message',json=dict(revision=p['revision'],mode='plan'))
    assert result.status_code==200,result.text
    return result.json()


def test_web_plan_budget_ownership_and_frozen_inputs(client, monkeypatch):
    p=ready(client);url='/creative/api/projects/'+p['id']
    assert p['duration']==60 and len(p['shots'])==12
    assert p['quote']['new_jobs']==4 and p['quote']['credits']==48
    assert client.post(url+'/execute',json=dict(revision=p['revision'],approved_credits=12)).status_code==400
    assert client.post(url+'/execute',headers={'Authorization':'Bearer two'},json=dict(revision=p['revision'],approved_credits=48)).status_code==404
    calls=[]
    async def hold(app,p,uid,auth):
        calls.append(p['run_id']);await asyncio.sleep(30)
    monkeypatch.setattr(api,'production',hold)
    one=client.post(url+'/execute',json=dict(revision=p['revision'],approved_credits=48)).json()
    two=client.post(url+'/execute',json=dict(revision=p['revision'],approved_credits=48)).json()
    assert one['run_id']==two['run_id'] and len(calls)==1
    assert len(one['campaign']['chapters'])==4 and one['campaign']['approved_credits']==48
    assert client.patch(url+'/agent-duration',json=dict(revision=p['revision'],duration=30)).status_code==409


def test_duration_modes_and_plan_invalidation(client):
    assert client.post('/creative/api/projects',json=dict(message='广告',duration=60,model='kling-video-v3_0')).status_code==422
    assert client.post('/creative/api/projects',json=dict(message='广告',duration=60,creation_mode='video')).status_code==422
    p=ready(client);url='/creative/api/projects/'+p['id']
    changed=client.patch(url+'/agent-duration',json=dict(revision=p['revision'],duration=30))
    assert changed.status_code==200,changed.text
    assert changed.json()['shots']==[] and changed.json()['generation_mode']==actions.MODE
    assert client.patch(url+'/agent-duration',json=dict(revision=p['revision'],duration=15)).status_code==409


@pytest.fixture
def execution(client, monkeypatch):
    p=ready(client);p.update(run_id='a'*24,state='running');actions.freeze(p,48);store.save(p,1)
    submitted=[];polled=[]
    async def submit(self,view,shot):
        submitted.append((deepcopy(view),deepcopy(shot)));return {'id':shot['id']}
    async def status(self,jid): polled.append(jid);return {'status':'completed'}
    async def download(self,jid,path): path.write_bytes(b'verified-test-video')
    monkeypatch.setattr(runner.CreativeVideoTool,'submit',submit)
    monkeypatch.setattr(runner.CreativeVideoTool,'status',status)
    monkeypatch.setattr(runner.CreativeVideoTool,'download',download)
    monkeypatch.setattr(runner,'verify_native_audio',lambda *a:dict(audio=True,semantic='pending'))
    # Storage/FFmpeg are separately tested; keep these contract tests deterministic.
    def prepare(project,model,mode,refs): return dict(model=model,mode=mode,references=deepcopy(refs))
    monkeypatch.setattr(actions,'prepare',prepare)
    def materialize(project,chapter,path):
        chapter.update(asset=str(chapter['index']+1)*32,tail_asset=str(chapter['index']+5)*32)
    monkeypatch.setattr(actions,'materialize_chapter',materialize)
    monkeypatch.setattr(runner,'timeline',lambda project:dict(duration=60,clips=[c['asset'] for c in project['campaign']['chapters']]))
    def render(project,spec,path):path.mkdir();(path/'final.mp4').write_bytes(b'final');return dict(technical='passed',semantic='pending',human='pending',training_eligible=False)
    monkeypatch.setattr(runner,'render_edit',render)
    def final(project,path):project['result_asset']='f'*32;return 'f'*32
    monkeypatch.setattr(actions,'attach_final',final)
    return p,submitted,polled


def run(p): asyncio.run(runner.production_campaign(None,p,1,'Bearer test'))


def test_four_chapters_are_sequential_bound_and_assembled(execution):
    p,submitted,polled=execution;run(p);saved=store.load(p['id'],1)
    assert saved['state']=='completed' and saved['qa']['semantic']=='pending' and not saved['training_eligible']
    assert [x[1]['id'] for x in submitted]==['chapter_1','chapter_2','chapter_3','chapter_4']
    assert all(x[0]['duration']==15 and [s['start'] for s in x[0]['shots']]==[0,5,10] for x in submitted)
    assert submitted[0][0]['video_inputs']['mode']=='text'
    assert submitted[1][0]['video_inputs']['references'][-1]['asset']=='5'*32
    assert 'Do not conclude' in submitted[0][1]['prompt'] and 'Complete the approved ending' in submitted[-1][1]['prompt']
    assert saved['edit']['duration']==60 and saved['result_asset']=='f'*32
    run(saved);assert len(submitted)==4  # Restart after delivery never submits another chapter.


def test_pause_then_resume_queries_accepted_job(execution, monkeypatch):
    p,submitted,polled=execution
    original=runner.CreativeVideoTool.submit
    async def pause(self,view,shot):
        result=await original(self,view,shot)
        saved=store.load(p['id'],1);saved['stop_requested']=True;store.save(saved,1)
        return result
    monkeypatch.setattr(runner.CreativeVideoTool,'submit',pause);run(p)
    saved=store.load(p['id'],1);assert saved['state']=='paused' and len(submitted)==1
    assert saved['campaign']['chapters'][0]['job_id']=='chapter_1' and not polled
    saved['stop_requested']=False;store.save(saved,1)
    monkeypatch.setattr(runner.CreativeVideoTool,'submit',original);run(saved)
    assert len(submitted)==4 and polled[0]=='chapter_1' and store.load(p['id'],1)['state']=='completed'


def test_unknown_submission_is_not_replayed(execution,monkeypatch):
    p,submitted,polled=execution;calls=[]
    async def lost(*args):calls.append(1);raise OSError('private transport')
    monkeypatch.setattr(runner.CreativeVideoTool,'submit',lost);run(p);run(store.load(p['id'],1))
    saved=store.load(p['id'],1)
    assert calls==[1] and saved['state']=='paused' and saved['campaign']['chapters'][0]['state']=='submitting'
    assert 'private transport' not in saved['error']


def test_provider_failure_stops_all_later_chapters(execution,monkeypatch):
    p,submitted,polled=execution
    async def failed(*args):return {'status':'failed'}
    monkeypatch.setattr(runner.CreativeVideoTool,'status',failed);run(p)
    saved=store.load(p['id'],1);assert saved['state']=='failed' and len(submitted)==1
    run(saved);assert len(submitted)==1


def test_plan_change_is_rejected_before_any_submit(execution):
    p,submitted,_=execution;p['shots'][0]['prompt']='changed';store.save(p,1);run(p)
    assert not submitted and store.load(p['id'],1)['state']=='paused'


def test_real_media_graph_timeline_and_export(client, monkeypatch, tmp_path):
    """Synthetic provider fixture, real frame extraction/HyperFrames/audio/graph checks."""
    import os
    import subprocess
    import io
    from PIL import Image
    from harness.tools.creative_canvas import save_asset, validate_graph
    from harness.tools.creative_video_inputs import prepare
    from harness.tools.canvas_lineage import lineage, derivation_edges
    from harness.tools import creative_render
    if not os.environ.get('CAMPAIGN_MEDIA_TEST'):
        pytest.skip('Opt-in real media integration requires configured render runtime')
    source=tmp_path/'provider-fixture.mp4'
    subprocess.run([os.environ['CREATIVE_FFMPEG'],'-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=24',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','15','-c:v','libx264','-preset','ultrafast',
        '-pix_fmt','yuv420p','-c:a','aac','-threads','1',str(source)],check=True,timeout=30)
    p=ready(client);p.update(run_id='b'*24,state='running')
    image=io.BytesIO();Image.new('RGB',(320,180),'black').save(image,'PNG')
    product=save_asset(p,image.getvalue(),'image');p['canvas_assets']={product['id']:product}
    p['canvas']={'nodes':[dict(id='product',kind='image',asset=product['id'],role='product',label='商品',text='',x=40,y=40)],'edges':[]}
    p['video_inputs']=prepare(p,p['model'],'references',[dict(asset=product['id'],role='product',instruction='保留黑色瓶身')])
    actions.freeze(p,48);store.save(p,1)
    submits=[]
    async def submit(self,view,shot):
        # Exercise actual input encoding and validate frozen hashes before accepting.
        from harness.tools.creative_video_inputs import conditions
        assert len(conditions(view))==(1 if not submits else 2)
        submits.append(shot['id']);return {'id':shot['id']}
    async def status(self,jid): return {'status':'completed'}
    async def download(self,jid,path): path.write_bytes(source.read_bytes())
    monkeypatch.setattr(runner.CreativeVideoTool,'submit',submit)
    monkeypatch.setattr(runner.CreativeVideoTool,'status',status)
    monkeypatch.setattr(runner.CreativeVideoTool,'download',download)
    monkeypatch.setattr(creative_render,'FFPROBE',os.environ['CREATIVE_FFPROBE'])
    run(p);saved=store.load(p['id'],1)
    assert saved['state']=='completed',saved.get('error')
    assert len(submits)==4 and len(saved['canvas']['nodes'])==9
    assert len(derivation_edges(saved['canvas'],lineage(saved)))==14
    validate_graph(saved['canvas'],saved['canvas_assets'])
    assert saved['edit']['duration']==60 and len(saved['edit']['clips'])==4
    assert all(c['gain']==1 and not c['muted'] for c in saved['edit']['clips'])
    assert saved['qa']['technical']=='passed' and saved['qa']['semantic']=='pending'
    output=store.DATA/saved['artifact'];meta=creative_render.probe(output)
    assert abs(float(meta['format']['duration'])-60)<.2
    assert any(s['codec_type']=='audio' for s in meta['streams'])
    graph=deepcopy(saved['canvas']);run(saved)
    assert store.load(p['id'],1)['canvas']==graph and len(submits)==4
    parent=client.post('/creative/api/projects',json=dict(message='母画布',creation_mode='video')).json()
    parent['director_project']=saved['id'];saved['manual_parent']=parent['id']
    assert actions.publish_to_workspace(parent,saved)
    assert not actions.publish_to_workspace(parent,saved)
    assert len(derivation_edges(parent['canvas'],lineage(parent)))==14


def test_explicit_reference_binding_survives_planning_and_duration(client):
    import io
    from PIL import Image
    from harness.tools.creative_canvas import save_asset
    p=ready(client);p=store.load(p['id'],1);p['brief']={}
    image=io.BytesIO();Image.new('RGB',(320,180),'black').save(image,'PNG')
    asset=save_asset(p,image.getvalue(),'image');p['canvas_assets']={asset['id']:asset}
    p['canvas']={'nodes':[dict(id='product',asset=asset['id'],kind='image',role='product',text='保留瓶型',label='商品',x=0,y=0)],'edges':[dict(source='product',target='director')]}
    store.save(p,1);url='/creative/api/projects/'+p['id']
    result=client.post(url+'/message',json=dict(revision=p['revision'],mode='plan')).json()
    assert result['video_inputs']['references'][0]['asset']==asset['id']
    assert result['duration']==60 and result['video_inputs_product']==result['brief']['product']
    assert result['video_inputs_needs_review'] is False
    body=dict(revision=result['revision'],model=result['model'],mode='references',references=[dict(asset=asset['id'],role='product',instruction='保留瓶型和黑色材质')])
    preview=client.post(url+'/video-inputs/preview',json=body).json()
    saved=client.put(url+'/video-inputs',json=dict(body,input_hash=preview['input_hash']))
    assert saved.status_code==200,saved.text
    assert saved.json()['duration']==60 and saved.json()['generation_mode']==actions.MODE


def test_automatic_mode_budget_covers_all_chapters(client,monkeypatch):
    import time
    captured=[]
    async def hold(app,p,uid,auth):captured.append(p);await asyncio.sleep(30)
    monkeypatch.setattr(api,'production',hold)
    p=client.post('/creative/api/projects',json=dict(message='60秒商品广告',duration=60,approval_mode='auto')).json()
    url='/creative/api/projects/'+p['id']
    body=dict(revision=0,mode='plan',background=True,request_id='a'*32,auto_approve_credits=12)
    assert client.post(url+'/message',json=body).status_code==400
    body['auto_approve_credits']=48
    assert client.post(url+'/message',json=body).status_code==200
    for _ in range(100):
        if captured:break
        time.sleep(.02)
    assert len(captured)==1 and len(captured[0]['campaign']['chapters'])==4
    assert captured[0]['campaign']['approved_credits']==48


def test_capacity_and_unresolved_submission_block_new_paid_work(client):
    p=ready(client);p=store.load(p['id'],1)
    p['canvas']={'nodes':[dict(id=str(i)) for i in range(9)],'edges':[]}
    with pytest.raises(ValueError):actions.freeze(p,48)
    p.pop('canvas');actions.freeze(p,48)
    p['campaign']['chapters'][0]['state']='submitting';p['state']='paused';store.save(p,1)
    result=client.post('/creative/api/projects/'+p['id']+'/message',json=dict(revision=p['revision'],mode='plan'))
    assert result.status_code==409
