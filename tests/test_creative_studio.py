"""Contract gates for paid approvals, ownership, revisions and durable state."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import types
import time
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from harness.studio import api, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    store.LOCKS.clear();store.RUNNING.clear()
    app=FastAPI()
    app.state.test_account_limits={'quota':100,'used':0}
    def auth(value):
        if value not in ('Bearer one','Bearer two'): raise HTTPException(401)
        return {'id':1 if value=='Bearer one' else 2,**app.state.test_account_limits}
    async def director(p,mode):
        return {'reply':'已规划','brief':{'product':'测试产品'},'assumptions':[], 'decisions':[], 'questions':[],
                'shots':[{'id':f'shot_{i+1}','title':f'镜头{i+1}','prompt':'glass bottle','audio_prompt':'Original soft music and gentle wind','caption':'字幕',
                          'rationale':'展示主体','start':i*5,'duration':5,'state':'planned'} for i in range(p['duration']//5)]}
    monkeypatch.setattr(api,'direct',director)
    def admin(value):
        if value!='Bearer admin': raise HTTPException(403)
        return {'id':3}
    api.install(types.SimpleNamespace(app=app,require_session=auth,require_admin=admin))
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer one'
        yield c


def ready(c):
    p=c.post('/creative/api/projects',json={'message':'测试香水','duration':15,'model':'kling-video-v3_0'}).json()
    return c.post('/creative/api/projects/'+p['id']+'/message',json={'revision':0,'mode':'plan'}).json()


def test_auth_and_owner_isolation(client):
    p=ready(client)
    assert client.get('/creative/api/projects/'+p['id'],headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get('/creative/api/projects',headers={'Authorization':'Bearer two'}).json()==[]
    assert client.get('/creative/api/projects',headers={'Authorization':'invalid'}).status_code==401
    assert client.get('/creative/api/projects/'+p['id']+'/media/final').status_code==404


def test_signed_provider_callback_is_bounded_and_idempotent(client, monkeypatch):
    secret='callback-test-secret';monkeypatch.setenv('CREATIVE_PROVIDER_CALLBACK_SECRET',secret)
    p=ready(client);current=store.load(p['id'],1);current['film']={'job_id':'provider-film-1','state':'generating'};store.save(current,1)
    body={'project_id':p['id'],'job_id':'provider-film-1','status':'completed',
          'trajectory':{'shots':[{'id':'main','duration':5,'points':[[0,0,0],[1,2,3]],'closed':True}],
                        'private':'discard'}}
    raw=json.dumps(body,separators=(',',':')).encode();timestamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),(timestamp+'.').encode()+raw,hashlib.sha256).hexdigest()
    headers={'X-Provider-Timestamp':timestamp,'X-Provider-Signature':'sha256='+signature}
    received=client.post('/creative/internal/provider-callback',content=raw,headers=headers)
    assert received.status_code==200,received.text;result=received.json();assert result['accepted'] and not result['idempotent'] and result['trajectory_observed'] and result['training_eligible'] is False
    saved=store.load(p['id'],1);callback=saved['film']['provider_callback'];assert callback['status']=='completed';assert callback['projection']['status']=='completed';assert saved['film']['provider_resolution']=='callback_observed_awaiting_poll';assert '[[0, 0, 0]' not in str(callback) and 'discard' not in str(callback);assert callback['training_eligible'] is False
    view=client.get('/creative/api/projects/'+p['id']).json();audit=view['provider_callback_audit'];assert len(audit)==1;assert audit[0]['target']=='film';assert audit[0]['status']=='completed';assert audit[0]['projection']['trajectory_observed'] is True
    queue=view['production_recovery_queue'];assert queue[0]['action']=='refresh_provider';assert queue[0]['can_resume'] is False;assert 'job' not in str(queue).lower()
    from harness.core import creative_runner
    stale=store.load(p['id'],1);stale['film'].pop('provider_callback',None);creative_runner._save(stale,1);assert store.load(p['id'],1)['film']['provider_callback']['status']=='completed'
    event_count=len(client.get('/creative/api/projects/'+p['id']).json()['events'])
    duplicate=client.post('/creative/internal/provider-callback',content=raw,headers=headers);assert duplicate.status_code==200 and duplicate.json()['idempotent'] is True
    duplicate_view=client.get('/creative/api/projects/'+p['id']).json();assert len(duplicate_view['events'])==event_count;assert len(duplicate_view['provider_callback_audit'])==1
    tampered=client.post('/creative/internal/provider-callback',content=raw+b' ',headers=headers);assert tampered.status_code==401
    unknown={**body,'job_id':'missing-job'};unknown_raw=json.dumps(unknown,separators=(',',':')).encode();unknown_sig=hmac.new(secret.encode(),(timestamp+'.').encode()+unknown_raw,hashlib.sha256).hexdigest();assert client.post('/creative/internal/provider-callback',content=unknown_raw,headers={**headers,'X-Provider-Signature':unknown_sig}).status_code==404


def test_callback_audit_serializes_same_digest_across_workers(client):
    p=ready(client);current=store.load(p['id'],1);current['film']={'job_id':'provider-film-race','state':'generating'};store.save(current,1)
    def apply():
        return store.apply_provider_callback(p['id'],1,'provider-film-race','e'*64,'running',{'status':'running'},None,time.time())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:apply(),range(2)))
    assert sorted(result[2] for result in results)==[False,True]
    assert len(store.provider_callback_audit(p['id']))==1


def test_stale_plan_and_budget_cannot_execute(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    assert client.post(url+'/execute',json={'revision':0,'approved_credits':9}).status_code==409
    assert client.post(url+'/execute',json={'revision':1,'approved_credits':1}).status_code==400
    assert client.get(url).json()['state']=='ready'


def test_edit_reorders_single_clock_and_validates(client):
    p=ready(client);url='/creative/api/projects/'+p['id']+'/timeline'
    shots=p['shots'][::-1];shots[0]['start']=999;shots[0]['caption']='新的字幕'
    r=client.patch(url,json={'revision':1,'shots':shots});assert r.status_code==200
    assert [s['start'] for s in r.json()['shots']]==[0,5,10]
    assert r.json()['shots'][0]['id']=='shot_3'
    assert client.patch(url,json={'revision':1,'shots':shots}).status_code==409
    shots[0]['prompt']=''
    assert client.patch(url,json={'revision':2,'shots':shots}).status_code==400


def test_trajectory_excludes_brief_and_provider_payload(client):
    p=ready(client)
    assert p['training_eligible'] is False
    assert p['events']
    for e in p['events']: assert set(e)=={'seq','time','stage','code','shot'}


def test_canvas_layout_observation_explains_auto_and_manual_states(client):
    from harness.tools.canvas_lineage import layout_observation
    project = {'canvas': {'nodes': [
        {'id': 'source', 'kind': 'image', 'label': '商品参考', 'x': 40, 'y': 30},
        {'id': 'generated', 'kind': 'image', 'label': '生成结果', 'x': 350, 'y': 30},
    ], 'edges': []}, 'canvas_auto_layout': {'node_id': 'generated', 'x': 350, 'y': 30}}
    observed = layout_observation(project)
    assert observed['schema'] == 'canvas-layout-observation-v1'
    assert observed['mode'] == 'auto'
    assert observed['node_count'] == 2 and observed['collision_count'] == 0
    assert observed['training_eligible'] is False
    project['canvas']['nodes'][1]['x'] = 80
    moved = layout_observation(project)
    assert moved['mode'] == 'manual_adjusted'
    assert moved['collision_count'] == 1


def test_model_failure_persists_context_without_generation(client,monkeypatch):
    p=ready(client)
    async def fail(*args): raise ValueError('raw unsafe provider data')
    monkeypatch.setattr(api,'direct',fail)
    url='/creative/api/projects/'+p['id']
    r=client.post(url+'/message',json={'text':'补充的重要要求','revision':p['revision']})
    assert r.status_code==502 and 'raw unsafe' not in r.text
    saved=client.get(url).json()
    assert saved['messages'][-1]['content']=='补充的重要要求'
    assert not saved.get('run_id')
    assert saved['state']=='planning_failed'
    assert saved['planning_failure_code']=='plan_validation'
    assert 'raw unsafe' not in json.dumps(saved)
    assert client.post(url+'/execute',json={'revision':saved['revision'],'approved_credits':9}).status_code==409
    assert client.patch(url+'/timeline',json={'revision':saved['revision'],'shots':saved['shots']}).status_code==409


def test_execute_deduplicates_inflight_and_recovers(client,monkeypatch):
    calls=[]
    async def production(app,p,owner,auth):
        calls.append(p['run_id'])
        await asyncio.sleep(10)
    monkeypatch.setattr(api,'production',production)
    p=ready(client);url='/creative/api/projects/'+p['id']
    one=client.post(url+'/execute',json={'revision':1,'approved_credits':9}).json()
    two=client.post(url+'/execute',json={'revision':1,'approved_credits':9}).json()
    assert one['run_id']==two['run_id']
    assert len(calls)==1
    assert client.post(url+'/message',json={'revision':1,'text':'改方案'}).status_code==409
    assert client.post(url+'/stop').json()['stop_requested']


def test_stop_during_submission_does_not_start_next_shot(client,monkeypatch,tmp_path):
    from harness.core import creative_runner as runner
    p=ready(client);p.pop('generation_mode');p['run_id']='test_run';p['state']='running';store.save(p,1)
    monkeypatch.setattr(runner,'DATA',tmp_path)
    submitted=[]
    class Video:
        def __init__(self,*args): pass
        async def submit(self,project,shot):
            submitted.append(shot['id'])
            saved=store.load(project['id'],1);saved['stop_requested']=True;store.save(saved,1)
            return {'id':'job_1'}
        async def status(self,job): return {'status':'completed'}
        async def download(self,job,path): path.write_bytes(b'fixture')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    monkeypatch.setattr(runner,'probe',lambda path:{'format':{'duration':'5'}})
    asyncio.run(runner.production(None,p,1,'Bearer one'))
    saved=store.load(p['id'],1)
    assert submitted==['shot_1']
    assert saved['state']=='paused'
    assert saved['shots'][0]['state']=='completed'
    assert saved['shots'][1]['state']=='planned'


def test_interrupted_planning_cannot_execute_old_plan(client):
    p=ready(client);p['state']='planning';p['revision']+=1;store.save(p,1)
    url='/creative/api/projects/'+p['id']
    assert client.post(url+'/execute',json={'revision':p['revision'],'approved_credits':9}).status_code==409
    result=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'})
    assert result.status_code==200
    assert result.json()['state']=='ready'


def completed(c):
    p=ready(c);p['state']='completed';p['run_id']='existing_run';p['artifact']='artifacts/existing_run/old/final.mp4';p['qa']={'technical':'passed','training_eligible':False}
    for s in p['shots']:s.update(state='completed',job_id='job_'+s['id'])
    store.save(p,1)
    return p


def test_completed_caption_edit_reuses_sources_and_archives(client):
    p=completed(client);shots=p['shots'][::-1];shots[0]['caption']='新字幕'
    r=client.patch('/creative/api/projects/'+p['id']+'/timeline',json={'revision':p['revision'],'shots':shots})
    assert r.status_code==200
    saved=r.json();assert saved['state']=='ready' and 'artifact' not in saved and 'qa' not in saved
    assert saved['run_id']=='existing_run'
    assert all(s['state']=='completed' and s.get('job_id') for s in saved['shots'])
    assert [s['start'] for s in saved['shots']]==[0,5,10]
    assert saved['versions'][0]['artifact']==p['artifact']
    assert saved['versions'][0]['shots'][0]['id']=='shot_1'
    assert saved['versions'][0]['shots'][1]['caption']=='字幕'


def test_completed_prompt_change_requires_new_plan(client):
    p=completed(client);shots=p['shots'];shots[0]['prompt']='another product'
    r=client.patch('/creative/api/projects/'+p['id']+'/timeline',json={'revision':p['revision'],'shots':shots})
    assert r.status_code==409
    assert client.get('/creative/api/projects/'+p['id']).json()['state']=='completed'


def test_reassembly_skips_all_paid_actions(client,monkeypatch,tmp_path):
    from harness.core import creative_runner as runner
    p=completed(client);p.pop('generation_mode')
    monkeypatch.setattr(runner,'DATA',tmp_path)
    directory=tmp_path/'artifacts'/p['run_id'];directory.mkdir(parents=True)
    for s in p['shots']:(directory/(s['id']+'.mp4')).write_bytes(b'fixture')
    class NoVideoCalls:
        def __init__(self,*args): pass
        async def submit(self,*args):raise AssertionError('paid submission forbidden')
        async def status(self,*args):raise AssertionError('completed sources need no polling')
    def render(project,destination):
        assert all((destination/(s['id']+'.mp4')).read_bytes()==b'fixture' for s in project['shots'])
        (destination/'final.mp4').write_bytes(b'new rendered output')
        return {'technical':'passed','training_eligible':False}
    monkeypatch.setattr(runner,'CreativeVideoTool',NoVideoCalls);monkeypatch.setattr(runner,'render',render)
    asyncio.run(runner.production(None,p,1,'Bearer one'))
    saved=store.load(p['id'],1)
    assert saved['state']=='completed'
    assert saved['artifact']!=p.get('old_artifact','artifacts/existing_run/old/final.mp4')


def test_history_media_is_owner_scoped(client,monkeypatch,tmp_path):
    p=completed(client);store.archive_render(p);store.save(p,1)
    monkeypatch.setattr(api,'DATA',tmp_path)
    target=tmp_path/p['artifact'];target.parent.mkdir(parents=True);target.write_bytes(b'fake test bytes')
    url='/creative/api/projects/'+p['id']+'/media/version_v'+str(p['revision'])
    assert client.get(url).status_code==200
    assert client.get(url,headers={'Authorization':'Bearer two'}).status_code==404


def test_review_requires_current_completed_version_and_owner(client):
    p=ready(client);url='/creative/api/projects/'+p['id']+'/review'
    body={'revision':p['revision'],'decision':'approved'}
    assert client.post(url,json=body).status_code==409
    p=completed(client);url='/creative/api/projects/'+p['id']+'/review'
    assert client.post(url,json={**body,'revision':0}).status_code==409
    assert client.post(url,json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url,json={**body,'decision':'changes_requested','note':'  '}).status_code==400


def test_review_is_version_bound_and_never_auto_enables_training(client):
    p=completed(client)
    target=store.DATA/p['artifact'];target.parent.mkdir(parents=True);target.write_bytes(b'review-test-artifact')
    url='/creative/api/projects/'+p['id']
    r=client.post(url+'/review',json={'revision':p['revision'],'decision':'approved','note':'synthetic test approval'})
    assert r.status_code==200
    reviewed=r.json();assert reviewed['qa']['human']=='approved'
    assert next(x for x in client.get('/creative/api/projects').json() if x['id']==p['id'])['review_status']=='approved'
    assert reviewed['training_eligible'] is False and reviewed['qa']['training_eligible'] is False
    assert reviewed['reviews'][0]['artifact']==p['artifact']
    shots=reviewed['shots'];shots[0]['caption']='修改后的字幕'
    edited=client.patch(url+'/timeline',json={'revision':p['revision'],'shots':shots}).json()
    assert 'qa' not in edited
    assert edited['versions'][0]['qa']['human']=='approved'
    assert edited['versions'][0]['reviews'][0]['note']=='synthetic test approval'
    assert client.post(url+'/review',json={'revision':edited['revision'],'decision':'approved'}).status_code==409


def test_review_records_append_and_notes_stay_out_of_events(client):
    p=completed(client)
    target=store.DATA/p['artifact'];target.parent.mkdir(parents=True);target.write_bytes(b'review-test-artifact')
    url='/creative/api/projects/'+p['id']+'/review'
    first=client.post(url,json={'revision':p['revision'],'decision':'changes_requested','note':'private review notes'}).json()
    second=client.post(url,json={'revision':p['revision'],'decision':'approved'}).json()
    assert len(second['reviews'])==2
    assert second['reviews'][0]==first['reviews'][0]
    assert second['qa']['human']=='approved'
    assert all('note' not in e for e in second['events'])


def test_catalog_quotes_model_specific_budget_and_rejects_mismatch(client):
    models=client.get('/creative/api/models').json()['models']
    assert {m['id'] for m in models}>={'kling-video-v2_5','kling-video-v3_0_omni','MiniMax-H3'}
    assert {m['id'] for m in models if m['available']}=={'kling-video-v3_0','kling-video-v3_0_omni','kling-video-v4_0'}
    assert all(m['service_status']=='unchecked' for m in models if m.get('provider'))
    assert all(m['service_status']=='unavailable' for m in models if not m.get('provider'))
    for m in models:
        if not m['available']:
            assert m['limitation']
            assert client.post('/creative/api/projects',json={'message':'测试广告','provider':m.get('provider','kling'),'model':m['id']}).status_code==422
    for provider,model,total in [('kling','kling-video-v3_0',9),('kling','kling-video-v3_0_omni',12)]:
        p=client.post('/creative/api/projects',json={'message':'香水广告','duration':15,'provider':provider,'model':model}).json()
        p=client.post('/creative/api/projects/'+p['id']+'/message',json={'revision':0,'mode':'plan'}).json()
        assert p['quote']['credits']==total
        assert p['model']==model
        assert client.post('/creative/api/projects/'+p['id']+'/execute',json={'revision':p['revision'],'approved_credits':total-1}).status_code==400
    assert client.post('/creative/api/projects',json={'message':'香水广告','provider':'kling','model':'MiniMax-H3'}).status_code==422


def test_video_tool_forwards_explicit_model_without_fallback():
    from harness.tools.creative_video import CreativeVideoTool
    calls=[]
    tool=CreativeVideoTool(None,'private-auth')
    async def request(method,path,**kw):
        calls.append(kw)
        return types.SimpleNamespace(json=lambda:{'id':'job'})
    tool.request=request
    asyncio.run(tool.submit({'provider':'kling','model':'kling-video-v2_5','run_id':'r','aspect':'9:16'},{'id':'s','duration':5,'prompt':'bottle'}))
    assert calls[0]['json']['model']=='kling-video-v2_5'
    assert calls[0]['json']['target']['duration_seconds']==5
    assert calls[0]['headers']['Idempotency-Key']=='r-s'


def test_insufficient_total_balance_stops_before_any_paid_shot(client):
    p=ready(client)
    client.app.state.test_account_limits={'quota':5,'used':0}
    result=client.post('/creative/api/projects/'+p['id']+'/execute',json={'revision':p['revision'],'approved_credits':9})
    assert result.status_code==402
    saved=client.get('/creative/api/projects/'+p['id']).json()
    assert saved['state']=='ready' and not saved.get('run_id')


def test_progress_snapshot_drops_provider_details_and_invalid_numbers():
    from harness.tools.creative_video import progress_snapshot
    assert progress_snapshot({'progress':38.1,'stage':'denoising','steps_completed':20,'steps_total':50,'url':'private','token':'private'})=={'percent':38,'stage':'denoising','steps_completed':20,'steps_total':50}
    assert progress_snapshot({'progress':float('nan'),'stage':'private arbitrary text','steps_completed':99,'steps_total':1})=={}


def test_progress_snapshot_normalizes_known_provider_percent_fields_only():
    from harness.tools.creative_video import progress_snapshot
    assert progress_snapshot({'progress_percent':'42.4','stage':'generating'})=={'percent':42,'stage':'generating'}
    assert progress_snapshot({'result':{'progressPercent':67},'signed_url':'private'})=={'percent':67}
    assert progress_snapshot({'output':{'progress':'81'},'raw_payload':'private'})=={'percent':81}
    assert progress_snapshot({'progress':True})=={}
    assert progress_snapshot({'result':{'progress_percent':'101'}})=={}


def test_uncertain_provider_receipt_pauses_without_next_shot(client,monkeypatch,tmp_path):
    from harness.core import creative_runner as runner
    p=ready(client);p.pop('generation_mode');p['run_id']='uncertain_run';p['state']='running'
    p['shots'][0].update(job_id='existing_job',state='generating');store.save(p,1)
    monkeypatch.setattr(runner,'DATA',tmp_path)
    class Video:
        def __init__(self,*args): pass
        async def status(self,job): return {'status':'uncertain'}
        async def submit(self,*args): raise AssertionError('Must not submit another shot')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    asyncio.run(runner.production(None,p,1,'Bearer one'))
    saved=store.load(p['id'],1)
    assert saved['state']=='paused' and '核对' in saved['error']
    assert saved['shots'][0]['provider_resolution']=='provider_terminal_uncertain'
    assert saved['shots'][0]['job_id']=='existing_job'


def test_reference_ownership_revision_and_plan_invalidation(client):
    import io
    from PIL import Image
    p=ready(client);url='/creative/api/projects/'+p['id']
    image=io.BytesIO();Image.new('RGB',(320,180),'white').save(image,'PNG')
    r=client.post(url+'/reference?revision='+str(p['revision']),content=image.getvalue(),headers={'Content-Type':'image/png'})
    assert r.status_code==200,r.text
    updated=r.json();assert updated['state']=='intake' and updated['shots']==[]
    assert updated['revision']==p['revision']+1 and updated['reference']['width']==320
    assert client.get(url+'/reference',headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(url+'/reference').headers['content-type']=='image/jpeg'
    assert client.post(url+'/execute',json={'revision':updated['revision'],'approved_credits':100}).status_code==409
    assert client.delete(url+'/reference?revision='+str(p['revision'])).status_code==409
    removed=client.delete(url+'/reference?revision='+str(updated['revision'])).json()
    assert removed['reference'] is None
    assert client.get(url+'/reference').status_code==404
    for event in removed['events']:assert set(event)=={'seq','time','stage','code','shot'}


def test_reference_rejects_invalid_image_without_changing_plan(client):
    import io
    from PIL import Image
    p=ready(client);url='/creative/api/projects/'+p['id'];endpoint=url+'/reference?revision='+str(p['revision'])
    assert client.post(endpoint,content=b'not an image').status_code==422
    image=io.BytesIO();Image.new('RGB',(180,320),'white').save(image,'PNG')
    assert client.post(endpoint,content=image.getvalue()).status_code==422
    current=client.get(url).json();assert current['revision']==p['revision'] and current['state']=='ready'
    assert client.post(endpoint,content=b'x'*(6*1024*1024+1)).status_code==413


def test_reference_video_transport_is_inline_and_bounded(client):
    import io,json
    from PIL import Image
    from harness.tools.creative_video import CreativeVideoTool
    p=ready(client);image=io.BytesIO();Image.new('RGB',(320,180),'white').save(image,'PNG')
    p=client.post('/creative/api/projects/'+p['id']+'/reference?revision='+str(p['revision']),content=image.getvalue()).json()
    p=client.post('/creative/api/projects/'+p['id']+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    p['run_id']='test-run';p['provider']='minimax-h3';p['model']='MiniMax-H3';captured=[]
    class Tool(CreativeVideoTool):
        async def request(self,*args,**kwargs):
            captured.append(kwargs['json']);return types.SimpleNamespace(json=lambda:{'id':'accepted'})
    asyncio.run(Tool(None,'unused').submit(p,p['shots'][0]))
    request=captured[0];assert request['task']=='fl2va' and request['target']['aspect_ratio']=='auto'
    assert request['conditions'][0]['uri'].startswith('data:image/jpeg;base64,')
    assert len(json.dumps(request))<1048576


def test_missing_film_cannot_receive_owner_approval(client):
    p=completed(client)
    assert client.post('/creative/api/projects/'+p['id']+'/review',json={'revision':p['revision'],'decision':'approved'}).status_code==409
    assert not client.get('/creative/api/projects/'+p['id']).json().get('reviews')


def _save_default_scene_for_timeline(client, project):
    from harness.tools.creative_scene import default_scene
    response = client.put(
        f"/creative/api/projects/{project['id']}/scene3d",
        json={'revision': project['revision'], 'spec': default_scene()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_scene_timeline_draft_requires_source_and_is_read_only(client, monkeypatch):
    from harness.studio import edit_api
    monkeypatch.setattr(edit_api, 'source_catalog', lambda _project: {})
    project = client.post('/creative/api/projects', json={'message': '无素材场景', 'duration': 15}).json()
    planned = client.post(
        f"/creative/api/projects/{project['id']}/message",
        json={'revision': 0, 'mode': 'plan'},
    ).json()
    scene = _save_default_scene_for_timeline(client, planned)
    draft_response = client.post(
        f"/creative/api/projects/{project['id']}/edit/scene-timeline-draft",
        json={'revision': scene['revision'], 'scene_hash': scene['hash']},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()['draft']
    assert draft['state'] == 'unavailable'
    assert 'no_video_source' in draft['conflicts']
    assert draft['requires_explicit_confirmation'] is True
    assert draft['training_eligible'] is False
    assert client.get(f"/creative/api/projects/{project['id']}/edit").json()['revision'] == scene['revision']


def test_scene_timeline_apply_and_undo_are_revision_bound(client, monkeypatch):
    from harness.studio import edit_api
    monkeypatch.setattr(edit_api, 'source_catalog', lambda _project: {
        'primary': {'id': 'primary', 'title': '测试原片', 'sha256': 'a' * 64,
                    'duration': 15.0, 'kind': 'video', 'has_audio': True,
                    'width': 1280, 'height': 720},
    })
    project = client.post('/creative/api/projects', json={'message': '有素材场景', 'duration': 15}).json()
    planned = client.post(
        f"/creative/api/projects/{project['id']}/message",
        json={'revision': 0, 'mode': 'plan'},
    ).json()
    scene = _save_default_scene_for_timeline(client, planned)
    base = client.post(
        f"/creative/api/projects/{project['id']}/edit/scene-timeline-draft",
        json={'revision': scene['revision'], 'scene_hash': scene['hash']},
    ).json()['draft']
    assert base['state'] == 'ready'
    assert len(base['rows']) == 1
    applied = client.post(
        f"/creative/api/projects/{project['id']}/edit/scene-timeline-apply",
        json={'revision': scene['revision'], 'scene_hash': scene['hash'],
              'base_document_sha256': base['base_document_sha256'],
              'draft_sha256': base['draft_sha256'], 'confirm': 'apply'},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result['revision'] == scene['revision'] + 1
    assert result['application']['reversible'] is True
    assert result['application']['training_eligible'] is False
    assert 'before_spec' not in result['application']
    assert result['spec']['clips'][0]['end'] == 10.0

    undone = client.post(
        f"/creative/api/projects/{project['id']}/edit/scene-timeline-undo",
        json={'revision': result['revision'],
              'application_id': result['application']['id']},
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()['application']['state'] == 'undone'
    assert undone.json()['revision'] == result['revision'] + 1

    stale = client.post(
        f"/creative/api/projects/{project['id']}/edit/scene-timeline-undo",
        json={'revision': result['revision'],
              'application_id': result['application']['id']},
    )
    assert stale.status_code == 409


def test_budget_preflight_is_owned_read_only_and_tracks_remaining(client):
    p=client.post('/creative/api/projects',json={'message':'皮夹克广告','model':'kling-video-v3_0_omni','duration':15}).json()
    p=client.post('/creative/api/projects/'+p['id']+'/message',json={'revision':0,'mode':'plan'}).json()
    url='/creative/api/projects/'+p['id']
    before=store.load(p['id'],1)
    client.app.state.test_account_limits={'quota':10,'used':4}
    assert client.get(url+'/budget').json()=={'revision':p['revision'],'required_credits':12,'remaining_credits':6,'sufficient':False}
    assert store.load(p['id'],1)==before
    assert client.get(url+'/budget',headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(url+'/budget',headers={'Authorization':'invalid'}).status_code==401
    client.app.state.test_account_limits={'quota':16,'used':4}
    assert client.get(url+'/budget').json()['sufficient'] is True
    client.app.state.test_account_limits={'quota':-1,'used':40}
    assert client.get(url+'/budget').json()['remaining_credits'] is None
    # An existing provider job costs zero to resume, even with no balance left.
    current=store.load(p['id'],1);current['film']={'job_id':'existing','state':'generating'};store.save(current,1)
    client.app.state.test_account_limits={'quota':10,'used':10}
    result=client.get(url+'/budget').json()
    assert result['required_credits']==0 and result['sufficient'] is True


@pytest.mark.parametrize('kind', ['image', 'planning', 'film', 'render'])
def test_poll_snapshot_does_not_become_interrupted_during_projection(client, monkeypatch, kind):
    """Complete a real asyncio worker while a GET response is being enriched."""
    import threading
    created = client.post('/creative/api/projects', json={'message': '进度快照验收'}).json()
    pid = created['id']
    current = store.load(pid, 1)
    current['revision'] += 1
    current['state'] = {'image': 'intake', 'planning': 'planning',
                        'film': 'running', 'render': 'rendering'}[kind]
    if kind == 'image':
        current['image_task'] = {'id': 'fixed-image-task', 'state': 'running'}
    store.save(current, 1)
    initial_revision = current['revision']

    async def start_worker():
        finish = asyncio.Event()
        async def worker():
            await finish.wait()
            latest = store.load(pid, 1)
            latest['revision'] += 1
            latest['state'] = 'ready' if kind == 'planning' else 'completed'
            if kind == 'image':
                latest['image_task']['state'] = 'completed'
            store.save(latest, 1)
            store.RUNNING.pop(pid, None)
        task = asyncio.create_task(worker())
        store.RUNNING[pid] = task
        return finish, task

    finish, task = client.portal.call(start_worker)
    entered, release = threading.Event(), threading.Event()
    original_present = api.present
    def delayed_projection(snapshot, **kwargs):
        if snapshot['id'] == pid and snapshot['revision'] == initial_revision:
            entered.set()
            assert release.wait(5), 'test did not release the in-flight response'
        return original_present(snapshot, **kwargs)
    monkeypatch.setattr(api, 'present', delayed_projection)

    async def complete_worker():
        finish.set()
        await task

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.get, '/creative/api/projects/' + pid)
        try:
            assert entered.wait(5), 'GET did not enter projection'
            client.portal.call(complete_worker)
            assert pid not in store.RUNNING
            # The first projection cannot block the event loop or newer reads.
            terminal = client.get('/creative/api/projects/' + pid)
            assert terminal.status_code == 200
            latest = terminal.json()
            assert latest['revision'] == initial_revision + 1
            assert latest['state'] == ('ready' if kind == 'planning' else 'completed')
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 200
    old = response.json()
    assert old['revision'] == initial_revision
    assert old['state'] == current['state']
    assert old['interrupted'] is False
    assert old['production_recovery_queue'] == []
    if kind == 'image':
        assert old['image_task']['state'] == 'running'
        assert latest['image_task']['state'] == 'completed'
        assert 'error' not in old['image_task']
    assert store.load(pid, 1)['revision'] == latest['revision']
    assert old['training_eligible'] is False


@pytest.mark.parametrize('kind', ['image', 'planning', 'film', 'render'])
def test_poll_still_reports_persisted_task_without_runtime_worker(client, kind):
    created = client.post('/creative/api/projects', json={'message': '真实中断验收'}).json()
    current = store.load(created['id'], 1)
    current['state'] = {'image': 'intake', 'planning': 'planning',
                        'film': 'running', 'render': 'rendering'}[kind]
    if kind == 'image':
        current['image_task'] = {'id': 'orphan-image-task', 'state': 'running'}
    store.save(current, 1)
    assert current['id'] not in store.RUNNING
    response = client.get('/creative/api/projects/' + current['id'])
    assert response.status_code == 200
    view = response.json()
    if kind == 'image':
        assert view['image_task']['state'] == 'needs_review'
    elif kind == 'planning':
        assert view['state'] == 'planning_failed'
    else:
        assert view['interrupted'] is True
        assert view['production_recovery_queue'][0]['action'] == 'refresh_existing'
    # Presentation does not rewrite durable state or create a replacement job.
    assert store.load(current['id'], 1)['state'] == current['state']
    assert current['id'] not in store.RUNNING


def test_progress_keeps_real_provider_check_time_without_private_fields():
    from harness.tools.creative_video import progress_snapshot
    import time
    stamp=int(time.time())
    assert progress_snapshot({'checked_at':stamp,'stage':'generating','token':'private'})=={'stage':'generating','checked_at':stamp}
    for invalid in (True, -1, 0, '123', float('nan'), float('inf'), stamp+3600):
        assert progress_snapshot({'checked_at':invalid})=={}
