import hashlib
import io
import json
import sqlite3
import time
import types
import pytest
from PIL import Image
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from harness.studio import api,store,image_api
from harness.tools import creative_image
from harness.models import studio_image
from harness.tools.creative_canvas import asset_directory
from harness.tools.creative_image_inputs import checked_paths


@pytest.fixture
def image_client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'projects');store.LOCKS.clear();store.RUNNING.clear()
    def db():return sqlite3.connect(tmp_path/'users.sqlite3')
    with db() as c:
        c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)')
        c.execute('INSERT INTO users VALUES(1,1,0,10)')
    def auth(value):
        if value not in ('Bearer one','Bearer two'):raise HTTPException(401)
        return {'id':1 if value=='Bearer one' else 2}
    specs=[dict(m,available=True) for m in studio_image.IMAGE_MODELS]
    monkeypatch.setattr(image_api,'image_models',lambda:specs)
    seen=[]
    def generate(model,prompt,aspect,out,reference):
        paths=reference if isinstance(reference,list) else [reference] if reference else []
        seen.append(dict(model=model,prompt=prompt,paths=paths,bytes=[p.read_bytes() for p in paths]))
        raw=io.BytesIO();Image.new('RGB',(240,180),'green').save(raw,'PNG');return raw.getvalue()
    monkeypatch.setattr(creative_image,'generate',generate)
    async def direct(p,mode):
        return dict(reply='方案已保存',brief={'product':'外套'},questions=[],assumptions=[],decisions=[],shots=[dict(id='s'+str(i),title='展示',prompt='jacket',audio_prompt='Original music',caption='可见细节',start=i*5,duration=5,state='planned') for i in range(3)])
    monkeypatch.setattr(api,'direct',direct)
    app=FastAPI();api.install(types.SimpleNamespace(app=app,require_session=auth,db=db))
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer one';yield c,seen,db


def setup(c):
    p=c.post('/creative/api/projects',json={'message':'三图组合验收','aspect':'16:9'}).json();url='/creative/api/projects/'+p['id'];ids=[]
    for color in ('red','blue','green'):
        raw=io.BytesIO();Image.new('RGB',(256,192),color).save(raw,'PNG')
        r=c.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=raw.getvalue()).json();p=r['project'];ids.append(r['asset']['id'])
    nodes=[dict(id='n'+str(i),asset=a,kind='image',role=role,label=role,text='',x=i*310,y=30) for i,(a,role) in enumerate(zip(ids,['product','person','scene']))]
    p=c.put(url+'/canvas',json={'revision':p['revision'],'nodes':nodes,'edges':[]}).json()
    p=c.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    body=dict(revision=p['revision'],model='hunyuan-image-v2.0-general-edit',prompt='穿着这件外套进入场景',references=[dict(asset=a,role=role,instruction='保留可见细节') for a,role in zip(ids,['product','person','scene'])],connect_to_director=False)
    return p,url,body


def finish(c,url):
    for _ in range(100):
        p=c.get(url).json()
        if p['image_task']['state']!='running':return p
        time.sleep(.02)
    pytest.fail('Image job remained running')


def test_review_and_single_submit_preserve_plan_and_record_all_inputs(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    reviewed=c.post(url+'/images/preview',json=body);assert reviewed.status_code==200,reviewed.text
    reviewed=reviewed.json();assert len(reviewed['references'])==3 and '图片 3：场景空间' in reviewed['prompt']
    assert reviewed['adjustments']=={'angle':'保留原角度','light':'保留原光照'}
    assert c.get(url).json()['revision']==p['revision'] and not seen
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0
    paid={**body,'request_id':'a'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}
    assert c.post(url+'/images',json=paid).status_code==200
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='completed' and len(seen)==1
    assert after['state']==p['state']=='ready' and after['shots']==p['shots']
    new=after['image_task']['asset'];origin=after['canvas_assets'][new]['provenance']
    assert origin['kind']=='image_composite' and origin['sources']==[v['asset'] for v in body['references']]
    assert origin['inputs']==reviewed['references'] and origin['input_hash']==reviewed['input_hash'] and not origin['training_eligible']
    assert origin['adjustments']==reviewed['adjustments']=={'angle':'保留原角度','light':'保留原光照'}
    assert after['canvas_lineage'][new]['inputs']==reviewed['references']
    assert after['canvas_lineage'][new]['adjustments']==reviewed['adjustments']
    assert after['canvas']['edges']==p['canvas']['edges']
    assert after['canvas']['nodes'][-1]['x']>max(n['x'] for n in p['canvas']['nodes'])
    assert after['canvas']['nodes'][-1]['role']=='reference'
    assert [hashlib.sha256(raw).hexdigest() for raw in seen[0]['bytes']]==[v['sha256'] for v in reviewed['references']]
    assert seen[0]['prompt']==reviewed['prompt']
    assert c.post(url+'/images',json={**paid,'prompt':'不同要求'}).status_code==409
    assert c.post(url+'/images',json={**paid,'references':list(reversed(body['references']))}).status_code==409
    assert c.post(url+'/images',json=paid).status_code==200
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1
    assert all('可见细节' not in str(e) and 'sha256' not in str(e) for e in after['events'])
    connected={**body,'revision':after['revision'],'connect_to_director':True}
    reviewed=c.post(url+'/images/preview',json=connected).json()
    assert c.post(url+'/images',json={**connected,'request_id':'b'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}).status_code==200
    connected=finish(c,url);assert connected['state']=='intake' and connected['shots']==[]
    assert len(connected['canvas']['edges'])==1 and len(seen)==2


def test_angle_and_light_adjustments_are_bounded_and_persisted(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    adjusted={**body,'references':[],'source_asset':body['references'][0]['asset'],'model':'hunyuan-image-v2.0-general-edit',
              'adjustments':{'angle':'侧面 45 度','light':'冷色轮廓光'}}
    reviewed=c.post(url+'/images/preview',json=adjusted);assert reviewed.status_code==200,reviewed.text
    reviewed=reviewed.json();assert reviewed['adjustments']==adjusted['adjustments']
    paid={**adjusted,'request_id':'c'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);aid=after['image_task']['asset']
    assert after['canvas_assets'][aid]['provenance']['adjustments']==adjusted['adjustments']
    assert after['canvas_lineage'][aid]['adjustments']==adjusted['adjustments']
    for key in ('angle','light'):
        invalid={**adjusted,'adjustments':{**adjusted['adjustments'],key:'未定义'}}
        assert c.post(url+'/images/preview',json=invalid).status_code==422


def test_image_transform_draft_preview_save_and_undo_are_version_bound(image_client):
    c,seen,db=image_client;p,url,body=setup(c);asset=body['references'][0]['asset']
    draft={'revision':p['revision'],'asset':asset,'angle':'侧面 45 度','light':'冷色轮廓光'}
    preview=c.post(url+'/image-transforms/preview',json=draft);assert preview.status_code==200,preview.text
    preview=preview.json();assert preview['preview_only'] and preview['reversible'] and not preview['training_eligible']
    assert preview['adjustments']=={'angle':'侧面 45 度','light':'冷色轮廓光'}
    assert c.get(url).json()['revision']==p['revision'] and not seen
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0
    saved=c.post(url+'/image-transforms/drafts',json={**draft,'preview_hash':preview['preview_hash'],'confirm':'save'});assert saved.status_code==200,saved.text
    saved=saved.json();record=saved['draft'];assert record['state']=='applied' and record['reversible'] and saved['revision']==p['revision']+1
    assert saved['project']['image_transform_drafts'][record['id']]['training_eligible'] is False
    assert c.post(url+'/image-transforms/drafts',json={**draft,'preview_hash':'0'*64,'confirm':'save'}).status_code==409
    undone=c.post(url+f"/image-transforms/drafts/{record['id']}/undo",json={'revision':saved['revision']});assert undone.status_code==200,undone.text
    undone=undone.json();assert undone['draft']['state']=='undone' and not undone['draft']['reversible'];assert undone['revision']==saved['revision']+1
    assert c.post(url+f"/image-transforms/drafts/{record['id']}/undo",json={'revision':undone['revision']}).status_code==404
    assert c.post(url+'/image-transforms/preview',json=draft).status_code==409


def test_image_transform_draft_binds_generation_and_reports_result(image_client):
    c,seen,db=image_client;p,url,body=setup(c);asset=body['references'][0]['asset']
    draft={'revision':p['revision'],'asset':asset,'angle':'俯视特写','light':'暖色侧光'}
    preview=c.post(url+'/image-transforms/preview',json=draft).json()
    saved=c.post(url+'/image-transforms/drafts',json={**draft,'preview_hash':preview['preview_hash'],'confirm':'save'}).json()
    record=saved['draft']
    generation={
        'revision':saved['revision'],'model':'hunyuan-image-v2.0-general-edit',
        'prompt':'生成一张变换结果','references':[],'source_asset':asset,
        'connect_to_director':False,'adjustments':{'angle':draft['angle'],'light':draft['light']},
        'transform_draft_id':record['id'],
    }
    reviewed=c.post(url+'/images/preview',json=generation);assert reviewed.status_code==200,reviewed.text
    reviewed=reviewed.json();assert reviewed['transform_draft_id']==record['id']
    paid={**generation,'request_id':'d'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);result=after['image_task']['asset'];origin=after['canvas_assets'][result]['provenance']
    assert origin['transform_draft_id']==record['id']
    linked=after['image_transform_drafts'][record['id']]
    assert linked['result_asset']==result and linked['result_revision']==after['revision'] and linked['result_state']=='available'
    assert linked['result_observation']['status']=='changed_observed'
    assert linked['result_observation']['human_review_required'] is True
    assert after['canvas_lineage'][result]['adjustments']=={'angle':draft['angle'],'light':draft['light']}
    assert after['canvas_lineage'][result]['transform_draft_id']==record['id']
    assert after['canvas_lineage'][result]['transform_alignment']['status']=='changed_observed'
    assert len(seen)==1


def test_reference_selection_limits_owner_model_and_review_hash(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    assert c.post(url+'/images/preview',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    for changed in [dict(references=[dict(asset='f'*32,role='product')]),dict(references=body['references']*2),dict(references=[body['references'][0]]*2),dict(model='hunyuan-image-v3.0'),dict(source_asset=body['references'][0]['asset']),dict(prompt='  '),dict(references=[dict(asset=body['references'][0]['asset'],role='admin')])]:
        assert c.post(url+'/images/preview',json={**body,**changed}).status_code==422
    paid={**body,'request_id':'a'*32,'approved_credits':1}
    assert c.post(url+'/images',json=paid).status_code==409
    assert c.post(url+'/images',json={**paid,'input_hash':'0'*64}).status_code==409
    assert c.get(url).json()['revision']==p['revision'] and not seen
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0


def test_changed_bytes_are_rejected_before_submission(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    approved=c.post(url+'/images/preview',json=body).json()
    a=p['canvas_assets'][body['references'][0]['asset']];path=asset_directory(p,a['id'])/a['filename'];path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='发生变化'):checked_paths(p,approved['references'])
    assert c.post(url+'/images',json={**body,'request_id':'a'*32,'approved_credits':1,'input_hash':approved['input_hash']}).status_code==409
    assert not seen
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0


def test_failure_is_not_retried_and_connect_requires_explicit_choice(image_client,monkeypatch):
    c,seen,db=image_client;p,url,body=setup(c);body['connect_to_director']=True
    approved=c.post(url+'/images/preview',json=body).json();paid={**body,'request_id':'a'*32,'approved_credits':1,'input_hash':approved['input_hash']}
    attempts=[]
    def fail(*args):attempts.append(1);raise RuntimeError('private provider response')
    monkeypatch.setattr(creative_image,'generate',fail)
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='needs_review' and after['shots']==p['shots']
    assert 'private provider response' not in json.dumps(after)
    assert c.post(url+'/images',json=paid).status_code==200 and attempts==[1]


def test_adapter_passes_ordered_files_without_fallback(tmp_path,monkeypatch):
    calls=[];refs=[]
    for i in range(3):
        file=tmp_path/(str(i)+'.jpg');file.write_bytes(b'input');refs.append(file)
    def run(args,**kwargs):
        calls.append(args);out=tmp_path/'output'/'result.png';out.write_bytes(b'result')
        return types.SimpleNamespace(returncode=0,stdout=json.dumps({'outputs':[{'path':str(out)}]}))
    monkeypatch.setattr(studio_image.subprocess,'run',run)
    assert studio_image.generate('hunyuan-image-v2.0-general-edit','要求','16:9',tmp_path/'output',refs)==b'result'
    assert [calls[0][i+1] for i,v in enumerate(calls[0]) if v=='--reference-image']==list(map(str,refs))
    with pytest.raises(ValueError):studio_image.generate('hunyuan-image-v2.0-general-edit','要求','16:9',tmp_path/'another',refs+[refs[0]])
    assert len(calls)==1 and not (tmp_path/'another').exists()


def test_region_review_once_and_lossless_outside_pixels(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    source=body['references'][0]['asset']
    body={**body,'references':[],'source_asset':source,'region':dict(x=.25,y=.25,width=.5,height=.5,feather=4)}
    review=c.post(url+'/images/preview',json=body);assert review.status_code==200,review.text
    reviewed=review.json();assert reviewed['region']==dict(box=[64,48,192,144],dimensions=[256,192],feather=4)
    assert '局部修改' in reviewed['prompt'] and not seen
    assert c.get(url).json()['revision']==p['revision']
    paid={**body,'request_id':'e'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}
    assert c.post(url+'/images',json={**paid,'region':{**body['region'],'x':.2}}).status_code==409
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='completed' and len(seen)==1
    aid=after['image_task']['asset'];asset=after['canvas_assets'][aid];assert asset['filename']=='source.png'
    original=c.get(url+'/canvas/assets/'+source+'/source');result=c.get(url+'/canvas/assets/'+aid+'/source')
    assert result.headers['content-type']=='image/png'
    a=Image.open(io.BytesIO(original.content)).convert('RGB');b=Image.open(io.BytesIO(result.content)).convert('RGB')
    assert a.size==b.size==(256,192)
    for box in [(0,0,256,48),(0,144,256,192),(0,48,64,144),(192,48,256,144)]:assert a.crop(box).tobytes()==b.crop(box).tobytes()
    assert a.getpixel((128,96))!=b.getpixel((128,96))
    assert a.getpixel((64,48))==b.getpixel((64,48))  # inward feather leaves the outer edge untouched
    assert after['canvas_lineage'][aid]['region_edit']['outside_preserved']
    assert after['canvas_lineage'][aid]['region_edit']['human_review_required']
    assert not asset['provenance']['training_eligible']
    assert after['shots']==p['shots'] and after['canvas']['edges']==p['canvas']['edges']
    assert c.post(url+'/images',json=paid).status_code==200 and len(seen)==1
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1


@pytest.mark.parametrize('region',[
    dict(x=-.1,y=0,width=.5,height=.5),dict(x=.8,y=0,width=.5,height=.5),
    dict(x=0,y=0,width=.001,height=.5),dict(x=0,y=0,width=.5,height=.5,feather=99),
    dict(x=0,y=0,width=.5,height=.5,arbitrary='ignored'),
])
def test_region_invalid_bounds_never_submit(image_client,region):
    c,seen,db=image_client;p,url,body=setup(c)
    body={**body,'references':[],'source_asset':body['references'][0]['asset'],'region':region}
    assert c.post(url+'/images/preview',json=body).status_code==422
    assert c.post(url+'/images',json={**body,'request_id':'e'*32,'approved_credits':1}).status_code==422
    assert not seen and c.get(url).json()['revision']==p['revision']


def test_region_requires_owned_single_image_and_frozen_review(image_client):
    c,seen,db=image_client;p,url,body=setup(c);region=dict(x=0,y=0,width=.5,height=.5)
    assert c.post(url+'/images/preview',json={**body,'region':region}).status_code==422
    local={**body,'references':[],'source_asset':body['references'][0]['asset'],'region':region}
    assert c.post(url+'/images/preview',json={**local,'source_asset':'f'*32}).status_code==422
    assert c.post(url+'/images/preview',json={**local,'model':'hunyuan-image-v3.0'}).status_code==422
    assert c.post(url+'/images/preview',json={**local,'adjustments':{'angle':'侧面 45 度','light':'保留原光照'}}).status_code==422
    assert c.post(url+'/images/preview',json=local,headers={'Authorization':'Bearer two'}).status_code==404
    assert c.post(url+'/images',json={**local,'request_id':'e'*32,'approved_credits':1}).status_code==409
    assert not seen


def test_brush_mask_guide_and_erased_hole_preserve_original_pixels(image_client):
    c,seen,db=image_client;p,url,body=setup(c);source=body['references'][0]['asset']
    strokes=[dict(points=[[.5,.5]],size=.3,erase=False),dict(points=[[.5,.5]],size=.1,erase=True)]
    body={**body,'references':[],'source_asset':source,'region':dict(x=0,y=0,width=1,height=1,feather=2,shape='brush',strokes=strokes)}
    review=c.post(url+'/images/preview',json=body);assert review.status_code==200,review.text
    reviewed=review.json();assert reviewed['region']['strokes']==strokes
    assert '第2张是黑白选区引导' in reviewed['prompt'] and not seen
    paid={**body,'request_id':'f'*32,'approved_credits':1,'input_hash':reviewed['input_hash']}
    changed={**paid,'region':{**body['region'],'strokes':strokes[:1]}}
    assert c.post(url+'/images',json=changed).status_code==409
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='completed' and len(seen)==1
    assert len(seen[0]['paths'])==2
    guide=Image.open(io.BytesIO(seen[0]['bytes'][1])).convert('L')
    assert hashlib.sha256(guide.tobytes()).hexdigest()==reviewed['region']['mask_sha256']
    aid=after['image_task']['asset']
    original=Image.open(io.BytesIO(c.get(url+'/canvas/assets/'+source+'/source').content)).convert('RGB')
    output=Image.open(io.BytesIO(c.get(url+'/canvas/assets/'+aid+'/source').content)).convert('RGB')
    for old,new,mask in zip(original.getdata(),output.getdata(),guide.getdata()):
        if mask==0:assert old==new
    assert output.getpixel((128,96))==original.getpixel((128,96))  # hole inside the bounding box
    assert output.getpixel((150,96))!=original.getpixel((150,96))
    assert after['canvas_lineage'][aid]['region_edit']['shape']=='brush'
    assert after['canvas_lineage'][aid]['region_edit']['outside_preserved']
    assert c.post(url+'/images',json=paid).status_code==200 and len(seen)==1
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1


@pytest.mark.parametrize('strokes',[
    [],[dict(points=[[.5,.5]],size=.2,erase=True)],
    [dict(points=[[1.1,.5]],size=.2,erase=False)],
    [dict(points=[[.5,.5]],size=.5,erase=False)],
    [dict(points=[[.5,.5]]*257,size=.2,erase=False)],
    [dict(points=[[.5,.5]],size=.2,erase=False)]*33,
    [dict(points=[[.5,.5]]*256,size=.2,erase=False)]*17,
])
def test_brush_bounds_empty_and_complexity_rejected_without_generation(image_client,strokes):
    c,seen,db=image_client;p,url,body=setup(c)
    body={**body,'references':[],'source_asset':body['references'][0]['asset'],
          'region':dict(x=0,y=0,width=1,height=1,shape='brush',strokes=strokes)}
    assert c.post(url+'/images/preview',json=body).status_code==422
    assert not seen and c.get(url).json()['revision']==p['revision']
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0


def test_brush_failed_candidate_is_not_retried_or_saved(image_client,monkeypatch):
    c,seen,db=image_client;p,url,body=setup(c);source=body['references'][0]['asset']
    body={**body,'references':[],'source_asset':source,'region':dict(x=0,y=0,width=1,height=1,shape='brush',strokes=[dict(points=[[.5,.5]],size=.3,erase=False)])}
    review=c.post(url+'/images/preview',json=body).json();calls=[]
    def invalid(*args):calls.append(1);return b'not an image'
    monkeypatch.setattr(creative_image,'generate',invalid)
    paid={**body,'request_id':'f'*32,'approved_credits':1,'input_hash':review['input_hash']}
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='needs_review'
    assert after['canvas_assets']==p['canvas_assets'] and after['canvas']==p['canvas']
    assert c.post(url+'/images',json=paid).status_code==200 and calls==[1]


def test_full_resolution_sources_and_results_have_separate_small_previews(image_client,monkeypatch):
    c,seen,db=image_client;p,url,body=setup(c)
    original=Image.new('RGB',(1440,1080),'#315369')
    original.putpixel((1001,701),(19,222,111))
    raw=io.BytesIO();original.save(raw,'PNG')
    upload=c.post(url+'/canvas/assets',params={'kind':'image','revision':p['revision']},content=raw.getvalue())
    assert upload.status_code==200,upload.text
    asset=upload.json()['asset'];p=upload.json()['project'];aid=asset['id']
    source=c.get(url+'/canvas/assets/'+aid+'/source');assert source.headers['content-type']=='image/png'
    with Image.open(io.BytesIO(source.content)) as full:assert full.size==(1440,1080) and full.tobytes()==original.tobytes()
    with Image.open(io.BytesIO(c.get(url+'/canvas/assets/'+aid+'/preview').content)) as preview:assert preview.size==(960,720)
    calls=[]
    def generated(*args):calls.append(1);return raw.getvalue()
    monkeypatch.setattr(creative_image,'generate',generated)
    body={**body,'revision':p['revision'],'references':[{'asset':aid,'role':'product','instruction':''}]}
    review=c.post(url+'/images/preview',json=body);assert review.status_code==200
    assert c.post(url+'/images',json={**body,'request_id':'c'*32,'approved_credits':1,'input_hash':review.json()['input_hash']}).status_code==200
    result=finish(c,url);assert result['image_task']['state']=='completed';result_id=result['image_task']['asset']
    assert result_id!=aid and calls==[1]
    with Image.open(io.BytesIO(c.get(url+'/canvas/assets/'+result_id+'/source').content)) as full:assert full.size==(1440,1080) and full.tobytes()==original.tobytes()
    with Image.open(io.BytesIO(c.get(url+'/canvas/assets/'+result_id+'/preview').content)) as preview:assert preview.size==(960,720)


@pytest.mark.parametrize('controls', [
    dict(kind='angle', preset='自定义', yaw=185, pitch=-35, zoom=50),
    dict(kind='light', preset='暖色侧光', direction=90, elevation=30, intensity=65, temperature=3200),
])
def test_numeric_controls_are_frozen_and_bound_to_result(image_client, controls):
    c,seen,db=image_client;p,url,body=setup(c)
    body.update(source_asset=body['references'][0]['asset'], references=[], control_parameters=controls)
    reviewed=c.post(url+'/images/preview',json=body)
    assert reviewed.status_code==200, reviewed.text
    frozen=reviewed.json();assert frozen['control_parameters']==controls
    paid={**body,'request_id':'e'*32,'approved_credits':1,'input_hash':frozen['input_hash']}
    field='yaw' if controls['kind']=='angle' else 'direction'
    changed={**controls,field:controls[field]+1}
    assert c.post(url+'/images/preview',json={**body,'control_parameters':changed}).json()['input_hash']!=frozen['input_hash']
    assert c.post(url+'/images',json={**paid,'control_parameters':changed}).status_code==409
    assert c.post(url+'/images',json={k:v for k,v in paid.items() if k!='input_hash'}).status_code==409
    assert not seen
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0
    assert c.post(url+'/images',json=paid).status_code==200
    after=finish(c,url);assert after['image_task']['state']=='completed'
    aid=after['image_task']['asset'];origin=after['canvas_assets'][aid]['provenance']
    assert origin['control_parameters']==after['canvas_lineage'][aid]['control_parameters']==controls
    assert origin['input_hash']==frozen['input_hash'] and origin['training_eligible'] is False
    assert body['source_asset'] in after['canvas_assets'] and len(seen)==1
    assert c.post(url+'/images',json=paid).status_code==200
    assert c.post(url+'/images',json={**paid,'control_parameters':changed}).status_code==409
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1


@pytest.mark.parametrize('change', [
    {'kind':[]}, {'preset':'unknown'}, {'yaw':361}, {'pitch':-91}, {'zoom':101},
    {'yaw':True}, {'yaw':'90'}, {'yaw':3.5}, {'direction':90},
])
def test_invalid_numeric_controls_do_not_submit(image_client, change):
    c,seen,db=image_client;p,url,body=setup(c)
    controls=dict(kind='angle',preset='自定义',yaw=0,pitch=0,zoom=50)
    body.update(source_asset=body['references'][0]['asset'],references=[],control_parameters={**controls,**change})
    assert c.post(url+'/images/preview',json=body).status_code==422
    assert not seen


def test_omitted_controls_preserve_legacy_input_hash(image_client):
    c,seen,db=image_client;p,url,body=setup(c)
    old=c.post(url+'/images/preview',json=body).json()
    explicit=c.post(url+'/images/preview',json={**body,'control_parameters':None}).json()
    assert old==explicit and 'control_parameters' not in old


def test_director_upload_binds_real_video_inputs_and_preserves_questions(image_client):
    c,seen,db=image_client
    p=c.post('/creative/api/projects',json={'message':'应用广告参考上传','model':'kling-video-v4_0'}).json()
    url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(300,400),'red').save(raw,'PNG')
    r=c.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=raw.getvalue()).json()
    p=r['project'];aid=r['asset']['id']
    saved=store.load(p['id'],1);saved['questions']=[dict(id='brand',question='请上传应用截图',why='核对外观',options=['上传'])];store.save(saved,1)
    body={'revision':p['revision'],'references':[dict(asset=aid,role='product',instruction='用户提供的应用界面') ]}
    assert c.post(url+'/director-references',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    result=c.post(url+'/director-references',json=body);assert result.status_code==200,result.text
    after=result.json();assert after['questions']==saved['questions']
    assert after['video_inputs']['references'][0]['asset']==aid
    assert after['input_manifest']['mode']=='references'
    assert len(after['input_manifest']['images'])==1 and len(after['canvas']['edges'])==1
    assert after['duration']==15 and not seen
    assert c.post(url+'/director-references',json=body).status_code==409
    bad={**body,'revision':after['revision'],'references':[dict(asset='0'*32,role='style',instruction='')]}
    assert c.post(url+'/director-references',json=bad).status_code==422
    assert c.get(url).json()['canvas']==after['canvas']


def test_agent_reference_generation_uses_bound_product_pixels_and_retains_video_anchor(image_client):
    c,seen,db=image_client
    p=c.post('/creative/api/projects',json={'message':'黑瓶概念广告','model':'kling-video-v4_0'}).json();url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(300,400),'black').save(raw,'PNG')
    uploaded=c.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=raw.getvalue()).json()
    source=uploaded['asset']['id'];refs=[dict(asset=source,role='product',instruction='保持黑色瓶体与几何形状')]
    bound=c.post(url+'/director-references',json=dict(revision=uploaded['project']['revision'],references=refs))
    assert bound.status_code==200,bound.text
    p=bound.json()
    body=dict(revision=p['revision'],model='hunyuan-image-v2.0-general-edit',prompt='黑瓶置于金色物理场景，无文字',
              director_reference=True,references=refs)
    # A text-only fallback or silently omitted product must fail before charging.
    assert c.post(url+'/images/preview',json={**body,'references':[]}).status_code==409
    assert c.post(url+'/images/preview',json={**body,'model':'hunyuan-image-v3.0'}).status_code==422
    assert c.post(url+'/images/preview',json={**body,'references':[dict(refs[0],role='style')]}).status_code==409
    assert not seen
    review=c.post(url+'/images/preview',json=body);assert review.status_code==200,review.text
    assert review.json()['references'][0]['asset']==source
    assert c.post(url+'/images',json=dict(body,input_hash=review.json()['input_hash'],request_id='b'*32,approved_credits=1)).status_code==200
    for _ in range(200):
        after=c.get(url).json()
        if after['state']=='ready':break
        time.sleep(.02)
    assert after['state']=='ready',after.get('error')
    assert len(seen)==1 and seen[0]['bytes']==[raw.getvalue()]
    result=after['image_task']['asset']
    assert after['canvas_lineage'][result]['sources']==[source]
    assert [(r['asset'],r['role']) for r in after['video_inputs']['references']]==[(source,'product'),(result,'style')]
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1


def test_director_reference_generates_once_then_binds_and_resumes_on_server(image_client,monkeypatch):
    c,seen,db=image_client;contexts=[]
    original=api.direct
    async def director(p,mode):
        contexts.append((p['video_inputs'],list(p['messages'])))
        return await original(p,mode)
    monkeypatch.setattr(api,'direct',director)
    p=c.post('/creative/api/projects',json={'message':'应用广告需要概念图','model':'kling-video-v4_0'}).json();url='/creative/api/projects/'+p['id']
    model=next(m['id'] for m in image_api.image_models() if m['mode'] in ('text','both'))
    body=dict(revision=p['revision'],model=model,prompt='暖色概念场景，无文字',connect_to_director=True,director_reference=True,director_context='直接帮我生成一个；双方选择后显示匹配成功')
    review=c.post(url+'/images/preview',json=body);assert review.status_code==200,review.text
    paid={**body,'input_hash':review.json()['input_hash'],'request_id':'c'*32,'approved_credits':1}
    result=c.post(url+'/images',json=paid);assert result.status_code==200,result.text
    for _ in range(150):
        after=c.get(url).json()
        if after['state']=='ready':break
        time.sleep(.02)
    assert after['state']=='ready',after.get('error')
    assert after['image_task']['state']=='completed' and len(seen)==len(contexts)==1
    aid=after['image_task']['asset'];assert contexts[0][0]['references'][0]['asset']==aid
    assert contexts[0][0]['references'][0]['role']=='style'
    assert any(m['content']==body['director_context'] for m in contexts[0][1])
    assert len(after['input_manifest']['images'])==1
    assert not after.get('film') and not after.get('auto_approval')
    assert c.post(url+'/images',json=paid).status_code==200 and len(seen)==1
    assert c.post(url+'/images',json={**paid,'director_context':'更换回答'}).status_code==409
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1


def test_director_binding_failure_keeps_generated_asset_without_retry(image_client,monkeypatch):
    from harness.tools import director_references
    c,seen,db=image_client
    p=c.post('/creative/api/projects',json={'message':'创建概念图','model':'kling-video-v4_0'}).json();url='/creative/api/projects/'+p['id']
    def fail(*args):raise ValueError('cannot bind')
    monkeypatch.setattr(director_references,'attach',fail)
    model=next(m['id'] for m in image_api.image_models() if m['mode'] in ('text','both'))
    body=dict(revision=p['revision'],model=model,prompt='丰富的概念场景',director_reference=True,request_id='d'*32,approved_credits=1)
    assert c.post(url+'/images',json=body).status_code==200
    for _ in range(100):
        after=c.get(url).json()
        if after.get('error'):break
        time.sleep(.02)
    assert after['image_task']['state']=='completed' and len(seen)==1
    assert after['image_task']['asset'] in after['canvas_assets']
    assert '不会再次生图' in after['error']


def test_concept_reference_policy_requires_completed_bound_image():
    from harness.agents.creative_policy import director_system
    p={'image_task':{'director_reference':True,'state':'completed','asset':'a'},'video_inputs':{'references':[{'asset':'a'}]}}
    assert '不要再次以缺少 Logo' in director_system(p,'广告合同')
    p['video_inputs']['references']=[]
    assert director_system(p,'广告合同')=='广告合同'
    p['video_inputs']['references']=[{'asset':'a'}];p['image_task']['state']='needs_review'
    assert director_system(p,'广告合同')=='广告合同'


@pytest.mark.parametrize('duration',[15,60])
def test_reference_to_film_runs_on_server_once_with_bound_budget(image_client,monkeypatch,duration):
    c,seen,db=image_client;produced=[];modes=[]
    with db() as conn:conn.execute('UPDATE users SET quota=100')
    original=api.direct
    async def direct(p,mode):
        modes.append(mode);result=await original(p,mode)
        result['shots']=[dict(result['shots'][0],id='s'+str(i),start=i*5) for i in range(duration//5)]
        return result
    async def production(app,p,uid,auth):
        produced.append(dict(model=p['model'],duration=p['duration'],references=p['video_inputs']['references'],approval=p['auto_approval']))
        p['state']='completed';store.save(p,uid);store.RUNNING.pop(p['id'],None)
    monkeypatch.setattr(api,'direct',direct);monkeypatch.setattr(api,'production',production)
    p=c.post('/creative/api/projects',json=dict(message='请自动制作概念广告',model='kling-video-v4_0',duration=duration,approval_mode='auto')).json()
    url='/creative/api/projects/'+p['id'];credits=4*(duration//5)
    model=next(m['id'] for m in image_api.image_models() if m['mode'] in ('text','both'))
    body=dict(revision=p['revision'],model=model,prompt='丰富的物理场景，不含文字',director_reference=True,director_video_credits=credits)
    preview=c.post(url+'/images/preview',json=body);assert preview.status_code==200,preview.text
    assert preview.json()['total_credits']==1+credits
    paid=dict(body,input_hash=preview.json()['input_hash'],request_id='e'*32,approved_credits=1)
    result=c.post(url+'/images',json=paid);assert result.status_code==200,result.text
    for _ in range(250):
        if produced:break
        time.sleep(.02)
    latest=c.get(url).json()
    assert len(produced)==1,latest.get('error')
    assert len(seen)==1 and modes==['plan']
    assert produced[0]['references'][0]['asset']==latest['image_task']['asset']
    assert produced[0]['approval']['credits']==credits and produced[0]['approval']['state']=='consumed'
    assert produced[0]['model']==p['model'] and produced[0]['duration']==duration
    assert c.post(url+'/images',json=paid).status_code==200
    assert c.post(url+'/images',json={**paid,'director_video_credits':credits+1}).status_code==409
    assert len(seen)==len(produced)==1


@pytest.mark.parametrize('stop,broken',[(True,False),(False,True)])
def test_reference_continuation_stop_and_planning_failure_never_submit_video(image_client,monkeypatch,stop,broken):
    c,seen,db=image_client;produced=[]
    with db() as conn:conn.execute('UPDATE users SET quota=100')
    original=api.direct
    async def direct(p,mode):
        if broken:raise ValueError('invalid director response')
        if stop:
            current=store.load(p['id'],1);current['stop_requested']=True;store.save(current,1)
        return await original(p,mode)
    async def production(*args):produced.append(True)
    monkeypatch.setattr(api,'direct',direct);monkeypatch.setattr(api,'production',production)
    p=c.post('/creative/api/projects',json=dict(message='自动制作广告',model='kling-video-v4_0',approval_mode='auto')).json();url='/creative/api/projects/'+p['id']
    model=next(m['id'] for m in image_api.image_models() if m['mode'] in ('text','both'))
    body=dict(revision=p['revision'],model=model,prompt='物理场景，不含文字',director_reference=True,director_video_credits=12,request_id='f'*32,approved_credits=1)
    assert c.post(url+'/images',json=body).status_code==200
    for _ in range(250):
        latest=c.get(url).json()
        if latest.get('auto_approval',{}).get('state') in ('stopped','needs_review'):break
        time.sleep(.02)
    assert latest['auto_approval']['state']==('stopped' if stop else 'needs_review')
    assert latest['image_task']['state']=='completed' and latest['image_task']['asset'] in latest['canvas_assets']
    assert len(seen)==1 and not produced


def test_reference_continuation_rejects_missing_authority_budget_and_balance_before_image(image_client):
    c,seen,db=image_client
    p=c.post('/creative/api/projects',json=dict(message='生成广告',model='kling-video-v4_0')).json();url='/creative/api/projects/'+p['id']
    model=next(m['id'] for m in image_api.image_models() if m['mode'] in ('text','both'))
    body=dict(revision=p['revision'],model=model,prompt='概念场景',director_reference=True,director_video_credits=12,request_id='a'*32,approved_credits=1)
    assert c.post(url+'/images',json=body).status_code==422
    current=store.load(p['id'],1);current['approval_mode']='auto';store.save(current,1)
    assert c.post(url+'/images',json={**body,'director_video_credits':11}).status_code==409
    assert c.post(url+'/images',json=body).status_code==402
    assert not seen and 'image_task' not in store.load(p['id'],1)
    with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==0
