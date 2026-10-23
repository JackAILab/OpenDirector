import pytest
from tests.test_creative_studio import client
from harness.studio import store
from harness.models.generation_progress import observing, report


def test_add_node_during_generation_keeps_parent_task_and_owner(client):
    parent=client.post('/creative/api/projects',json={'message':'cat image','creation_mode':'image'}).json()
    p=store.load(parent['id'],1);p['image_task']={'id':'fixture','state':'running'};store.save(p,1)
    store.RUNNING[parent['id']]=object()
    result=client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'cat video','creation_mode':'video','model':'kling-video-v2_6','duration':5})
    assert result.status_code==200,result.text
    child=result.json()['project'];assert child['model']=='kling-video-v2_6'
    assert store.load(parent['id'],1)['image_task']['state']=='running'
    assert parent['id'] in store.RUNNING and child['id'] not in store.RUNNING
    nodes=client.get('/creative/api/projects/'+parent['id']+'/manual-nodes').json()['nodes']
    assert nodes[0]['project']['id']==child['id']
    assert client.get('/creative/api/projects/'+parent['id']+'/manual-nodes',headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'agent mode','creation_mode':'agent'}).status_code==422


def test_runner_retains_nodes_created_after_snapshot(client):
    from harness.core.creative_runner import _save
    p=client.post('/creative/api/projects',json={'message':'cat video','creation_mode':'video'}).json()
    stale=store.load(p['id'],1)
    result=client.post('/creative/api/projects/'+p['id']+'/manual-nodes',json={'message':'another image','creation_mode':'image'}).json()
    _save(stale,1)
    assert store.load(p['id'],1)['manual_nodes'][0]['project']==result['project']['id']


def test_progress_is_bounded_and_observer_failure_is_not_generation_failure():
    observations=[]
    with observing(observations.append):
        report('generating',35);report('generating',float('nan'));report('raw provider secret',10)
    assert observations==[{'phase':'generating','percent':35},{'phase':'generating'}]
    with observing(lambda _:1/0):report('generating',80)


def test_image_provider_poll_publishes_real_progress_without_payload(monkeypatch,tmp_path):
    from contextlib import contextmanager,nullcontext
    from io import BytesIO
    from PIL import Image
    from harness.models import kling_studio_image as adapter
    tool,body=adapter.arguments('kling-image-o1','a cat','1:1',[])
    states=iter([{'state':'RUNNING','progress':37,'private':'never-observe'}, {'state':'COMPLETED','url':'https://fixture.invalid/result.png'}])
    def cli(args):
        if args[0]=='who_am_i':return {'body':{'availableModels':{tool:{'models':[{'model':body['model'],'arguments':body['arguments'],'inputs':[]}]}}}}
        return next(states)
    submitted=[]
    @contextmanager
    def connection():
        def call(name,args):submitted.append(name);return {'generation_id':'fixture-generation'}
        yield call,None
    image=BytesIO();Image.new('RGB',(8,8)).save(image,'PNG');raw=image.getvalue()
    monkeypatch.setattr(adapter,'connection',connection)
    monkeypatch.setattr(adapter,'session_lock',nullcontext)
    monkeypatch.setattr(adapter,'cli',cli)
    monkeypatch.setattr(adapter.time,'sleep',lambda _:None)
    monkeypatch.setattr(adapter.urllib.request,'urlopen',lambda *a,**kw:BytesIO(raw))
    observations=[]
    with observing(observations.append):
        assert adapter.generate(body['model'],'a cat','1:1',tmp_path/'attempt',[])==raw
    assert {'phase':'generating','percent':37} in observations
    assert observations[-1]=={'phase':'downloading'}
    assert submitted==['text_to_image']
    assert 'private' not in str(observations) and 'https' not in str(observations)


def test_director_reuses_linked_run_without_changing_manual_job(client):
    parent=client.post('/creative/api/projects',json={'message':'cat video','creation_mode':'video'}).json()
    p=store.load(parent['id'],1);p['film']={'job_id':'already-paid','state':'generating'};store.save(p,1)
    endpoint='/creative/api/projects/'+parent['id']+'/director'
    child=client.post(endpoint).json()
    assert child['creation_mode']=='agent'
    assert client.post(endpoint).json()['id']==child['id']
    latest=store.load(parent['id'],1)
    assert latest['film']['job_id']=='already-paid'
    assert len(latest['manual_nodes'])==1
    assert client.post(endpoint,headers={'Authorization':'Bearer two'}).status_code==404
    node=client.post('/creative/api/projects/'+child['id']+'/manual-nodes',json={'message':'another image','creation_mode':'image'})
    assert node.status_code==200


@pytest.mark.parametrize('video_inputs', [None, {}])
def test_generated_result_is_idempotent_and_preserves_canvas(client, monkeypatch, tmp_path, video_inputs):
    from harness.tools import creative_video_result
    p=client.post('/creative/api/projects',json={'message':'cat video','creation_mode':'video'}).json()
    p['run_id']='fixture-run'
    p['video_inputs']=video_inputs
    latest=store.load(p['id'],1)
    latest['canvas']={'nodes':[{'id':'note','kind':'text','text':'keep me','x':10,'y':10}], 'edges':[]}
    store.save(latest,1)
    calls=[]
    def asset(*a,**kw):
        assert kw['max_bytes']==256*1024*1024
        calls.append(True)
        return {'id':('a' if len(calls)==1 else 'b')*32,'kind':'video','filename':'source.mp4','sha256':__import__('hashlib').sha256(a[1]).hexdigest()}
    monkeypatch.setattr(creative_video_result,'save_asset',asset)
    video=tmp_path/'result.mp4';video.write_bytes(b'fixture')
    creative_video_result.attach_result(p,1,video);store.save(p,1)
    creative_video_result.attach_result(p,1,video)
    assert len(calls)==1
    assert len(p['canvas']['nodes'])==2
    assert p['canvas']['nodes'][0]['text']=='keep me'
    assert p['canvas_assets']['a'*32]['provenance']['training_eligible'] is False

    # A different edit of the same generation is a new immutable canvas asset.
    changed=tmp_path/'new-edit.mp4';changed.write_bytes(b'new edited content')
    creative_video_result.attach_result(p,1,changed)
    assert len(calls)==2
    assert len(p['canvas']['nodes'])==3
    assert p['result_asset']=='b'*32
    assert p['result_artifact']=='new-edit.mp4'
    assert 'a'*32 in p['canvas_assets']


def test_director_imports_only_connected_context_and_retains_local_nodes(client):
    from harness.tools.creative_workspace_context import sync_context
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    p=store.load(parent['id'],1)
    def note(n, text):return {'id':n,'kind':'text','label':n,'text':text,'x':40,'y':30,'role':'reference'}
    p['canvas']={'nodes':[note('connected','use this'),note('private','not selected')],
                 'edges':[{'source':'connected','target':'director'}]}
    store.save(p,1)
    child=client.post('/creative/api/projects/'+p['id']+'/director').json()
    assert [n['text'] for n in child['canvas']['nodes']]==['use this']
    p=store.load(p['id'],1);c=store.load(child['id'],1)
    c['canvas']['nodes'].append(note('local','keep local'))
    p['canvas']['edges']=[]
    sync_context(p,c)
    assert [n['id'] for n in c['canvas']['nodes']]==['local']
    assert c['workspace_context_nodes']==[]
    import pytest
    with pytest.raises(ValueError):sync_context({**p,'director_project':'another'},c)


def test_workspace_reference_files_are_local_and_reused(client):
    from harness.tools.creative_workspace_context import sync_context
    from harness.tools.creative_canvas import save_asset,asset_directory,director_inputs
    from io import BytesIO
    from PIL import Image
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    p=store.load(parent['id'],1)
    raw=BytesIO();Image.new('RGB',(16,16),'red').save(raw,format='PNG')
    asset=save_asset(p,raw.getvalue(),'image');p['canvas_assets']={asset['id']:asset}
    p['canvas']={'nodes':[{'id':'picture','kind':'image','asset':asset['id'],'label':'reference','text':'keep character','x':40,'y':30,'role':'reference'}],
                 'edges':[{'source':'picture','target':'director'}]};store.save(p,1)
    response=client.post('/creative/api/projects/'+p['id']+'/director');assert response.status_code==200,response.text
    c=store.load(response.json()['id'],1);p=store.load(p['id'],1)
    assert (asset_directory(c,asset['id'])/'frame-0.jpg').is_file()
    notes,images=director_inputs(c);assert notes[0]['instruction']=='keep character';assert len(images)==2
    sync_context(p,c);assert len(c['canvas']['nodes'])==1
    assert client.get('/creative/api/projects/'+c['id'],headers={'Authorization':'Bearer two'}).status_code==404


def test_director_message_refreshes_workspace_snapshot(client, monkeypatch):
    from harness.studio import api
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/director').json()
    p=store.load(parent['id'],1)
    p['canvas']={'nodes':[{'id':'latest','kind':'text','label':'updated reference','text':'new scene instructions','x':40,'y':30}],
                 'edges':[{'source':'latest','target':'director'}]}
    store.save(p,1)
    seen=[]
    async def director(project,mode):
        seen.extend(project['canvas']['nodes'])
        return {'reply':'context received','brief':{},'questions':[],'assumptions':[],'decisions':[],'shots':[]}
    monkeypatch.setattr(api,'direct',director)
    response=client.post('/creative/api/projects/'+child['id']+'/message',json={'revision':child['revision'],'text':'use workspace reference','mode':'interview'})
    assert response.status_code==200,response.text
    assert [n['text'] for n in seen]==['new scene instructions']
    assert store.load(parent['id'],1)['revision']==p['revision']


def test_director_context_preview_is_current_read_only_and_owned(client):
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/director').json()
    p=store.load(parent['id'],1);p['canvas']={'nodes':[{'id':'visible','kind':'text','label':'sunset','text':'private description','x':40,'y':30}], 'edges':[{'source':'visible','target':'director'}]};store.save(p,1)
    before=store.load(child['id'],1)
    url='/creative/api/projects/'+child['id']+'/director-context'
    result=client.get(url);assert result.status_code==200
    assert result.json()=={'project':p['id'],'live_inputs':None,'references':[{'id':'visible','kind':'text','label':'sunset'}]}
    assert store.load(child['id'],1)==before
    assert client.get(url,headers={'Authorization':'Bearer two'}).status_code==404
    p['canvas']['edges']=[];store.save(p,1)
    assert client.get(url).json()['references']==[]


def test_workspace_delivery_retry_is_owned_versioned_and_does_not_generate(client):
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/director').json()
    with store.connection() as c:
        c.execute("INSERT INTO workspace_deliveries(owner,project,parent,asset,state,code,next_attempt,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (1,child['id'],parent['id'],'a'*32,'needs_review','workspace_inputs_or_capacity',9999999999,1))
    before=store.load(child['id'],1);url='/creative/api/projects/'+child['id']+'/workspace-delivery/retry'
    assert client.post(url,json={'revision':child['revision']},headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url,json={'revision':child['revision']+1}).status_code==409
    result=client.post(url,json={'revision':child['revision']})
    assert result.status_code==200,result.text
    assert result.json()['workspace_deliveries']==[{'asset':'a'*32,'state':'pending','code':''}]
    assert store.load(child['id'],1)==before and not store.RUNNING


def test_director_input_summary_never_borrows_nearby_video_inputs(client):
    parent=client.post('/creative/api/projects',json={'message':'workspace','creation_mode':'video'}).json()
    director=client.post('/creative/api/projects/'+parent['id']+'/director').json()
    video=client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'unrelated video','creation_mode':'video'}).json()['project']
    unrelated=store.load(video['id'],1)
    unrelated['video_inputs']={'mode':'references','references':[{'asset':'a'*32,'role':'product','instruction':'different product'}]}
    store.save(unrelated,1)
    url='/creative/api/projects/'+director['id']+'/director-context'
    assert client.get(url).json()['live_inputs'] is None
    own=store.load(director['id'],1);own['video_inputs']={'mode':'text','references':[]};store.save(own,1)
    assert client.get(url).json()['live_inputs']==own['video_inputs']
    assert client.get(url,headers={'Authorization':'Bearer two'}).status_code==404
    child=client.post('/creative/api/projects/'+director['id']+'/manual-nodes',json={'message':'another video','creation_mode':'video'}).json()['project']
    saved=store.load(child['id'],1);saved['video_inputs']=unrelated['video_inputs'];store.save(saved,1)
    own=store.load(director['id'],1);own.pop('video_inputs');store.save(own,1)
    view=client.get('/creative/api/projects/'+director['id']).json()
    assert 'director_inputs' not in view and view['input_manifest']['mode']=='text'


def test_manual_node_position_is_owned_bounded_and_independent_of_generation(client):
    parent=client.post('/creative/api/projects',json={'message':'layout test','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'child layout','creation_mode':'video'}).json()['project']
    p=store.load(parent['id'],1);p['state']='running';p['film']={'job_id':'existing','state':'running'};store.save(p,1)
    stale=store.load(parent['id'],1)
    path='/creative/api/projects/'+parent['id']+'/manual-nodes/'+child['id']+'/position'
    result=client.patch(path,json={'x':-200.5,'y':800})
    assert result.status_code==200,result.text
    saved=store.load(parent['id'],1)
    assert saved['manual_nodes'][0]['x']==-200.5
    assert saved['film']==p['film'] and saved['revision']==p['revision']
    from harness.core.creative_runner import _save
    _save(stale,1)
    assert store.load(parent['id'],1)['manual_nodes'][0]['y']==800
    assert client.patch(path,json={'x':10001,'y':0}).status_code==422
    assert client.patch(path,json={'x':0,'y':0},headers={'Authorization':'Bearer two'}).status_code==404
    unrelated=client.post('/creative/api/projects',json={'message':'unrelated project'}).json()
    assert client.patch(path.replace(child['id'],unrelated['id']),json={'x':0,'y':0}).status_code==404


def test_root_manual_position_survives_runner_and_preserves_inputs(client):
    parent=client.post('/creative/api/projects',json={'message':'root position','creation_mode':'video'}).json()
    stale=store.load(parent['id'],1)
    path='/creative/api/projects/'+parent['id']+'/manual-nodes/'+parent['id']+'/position'
    result=client.patch(path,json={'x':270,'y':180})
    assert result.status_code==200,result.text
    from harness.core.creative_runner import _save
    _save(stale,1)
    saved=store.load(parent['id'],1)
    assert saved['manual_position']=={'x':270,'y':180}
    assert saved['revision']==parent['revision']
    assert saved['direct_prompt']==parent['direct_prompt']
    assert client.patch(path,json={'x':0,'y':0},headers={'Authorization':'Bearer two'}).status_code==404
    agent=client.post('/creative/api/projects',json={'message':'agent position'}).json()
    assert client.patch(path.replace(parent['id'],agent['id']),json={'x':0,'y':0}).status_code==404


@pytest.mark.parametrize("director", [False, True])
def test_import_child_result_is_immutable_idempotent_and_owned(client, director):
    from io import BytesIO
    from PIL import Image
    from harness.tools.creative_canvas import save_asset, asset_directory
    parent=client.post('/creative/api/projects',json={'message':'parent canvas','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'child image','creation_mode':'image'}).json()['project']
    if director:
        child=client.post('/creative/api/projects/'+parent['id']+'/director').json()
        parent=client.get('/creative/api/projects/'+parent['id']).json()
    c=store.load(child['id'],1);raw=BytesIO();Image.new('RGB',(64,64),'blue').save(raw,'PNG')
    asset=save_asset(c,raw.getvalue(),'image');c['canvas_assets']={asset['id']:asset};c['image_task']={'state':'completed','asset':asset['id']};store.save(c,1)
    path='/creative/api/projects/'+parent['id']+'/manual-nodes/'+child['id']+'/result'
    result=client.post(path);assert result.status_code==200,result.text
    p=result.json()['project'];n=result.json()['node']
    assert p['canvas']['edges']==[] and n['asset']==asset['id']
    assert p['state']==parent['state'] and p['direct_prompt']==parent['direct_prompt']
    assert p['revision']==parent['revision']+1
    assert asset_directory(p,asset['id']).joinpath('source.jpg').read_bytes()==asset_directory(c,asset['id']).joinpath('source.jpg').read_bytes()
    assert store.load(c['id'],1)==c
    again=client.post(path).json();assert again['node']['id']==n['id'] and again['project']['revision']==p['revision']
    assert len(again['project']['canvas']['nodes'])==1
    assert client.post(path,headers={'Authorization':'Bearer two'}).status_code==404
    unrelated=client.post('/creative/api/projects',json={'message':'unrelated image','creation_mode':'image'}).json()
    assert client.post(path.replace(child['id'],unrelated['id'])).status_code==422
    p=store.load(parent['id'],1);p['state']='running';store.save(p,1)
    assert client.post(path).status_code==409


def test_video_result_import_rejects_stale_artifact_and_pending_image(client):
    parent=client.post('/creative/api/projects',json={'message':'parent canvas','creation_mode':'video'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/manual-nodes',json={'message':'child video','creation_mode':'video'}).json()['project']
    path='/creative/api/projects/'+parent['id']+'/manual-nodes/'+child['id']+'/result'
    assert client.post(path).status_code==422
    c=store.load(child['id'],1);c.update(state='completed',artifact='new.mp4',result_artifact='old.mp4',result_asset='a'*32,canvas_assets={'a'*32:{'kind':'video'}});store.save(c,1)
    assert client.post(path).status_code==422


@pytest.mark.parametrize('kind',['image','video'])
def test_child_reference_import_owned_idempotent_and_locked(client,kind):
    import io
    from PIL import Image
    from harness.tools.creative_canvas import asset_directory
    parent=client.post('/creative/api/projects',json={'message':'parent image','creation_mode':'image'}).json()
    base='/creative/api/projects/'+parent['id']
    raw=io.BytesIO();Image.new('RGB',(320,180),(80,100,120)).save(raw,'PNG')
    upload=client.post(base+'/canvas/assets',params={'revision':parent['revision'],'kind':'image'},content=raw.getvalue()).json()
    aid=upload['asset']['id'];p=upload['project']
    saved=client.put(base+'/canvas',json={'revision':p['revision'],'nodes':[{'id':'image1','kind':'image','asset':aid,'label':'主体参考','text':'','role':'reference','x':40,'y':40}],'edges':[]});assert saved.status_code==200
    child=client.post(base+'/manual-nodes',json={'message':'child generator','creation_mode':kind}).json()['project']
    route=base+'/manual-nodes/'+child['id']+'/reference';body={'revision':child['revision'],'asset':aid}
    assert client.post(route,json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(route,json={**body,'asset':'f'*32}).status_code==422
    result=client.post(route,json=body);assert result.status_code==200,result.text
    imported=result.json();assert aid in imported['canvas_assets'] and not imported.get('video_inputs')
    assert imported['direct_prompt']==child['direct_prompt']
    path=asset_directory(store.load(child['id'],1),aid)/upload['asset']['filename'];assert path.read_bytes()==raw.getvalue()
    again=client.post(route,json={**body,'revision':imported['revision']}).json();assert again['revision']==imported['revision']
    pending=store.load(child['id'],1);pending.update(state='paused',film={'state':'generating','job_id':'fixture'});store.save(pending,1)
    assert client.post(route,json={**body,'revision':imported['revision']}).status_code==409
