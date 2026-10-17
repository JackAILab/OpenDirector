import copy
import hashlib
import hmac
import io
import json
import struct
import time
from PIL import Image
import pytest
from harness.studio import store
from harness.tools.creative_scene import default_scene,validate_scene,validate_glb,scene_hash
from test_creative_studio import client,ready


def glb(**extra):
    doc={'asset':{'version':'2.0'},'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'meshes':[{'primitives':[]}]}
    doc.update(extra);data=json.dumps(doc).encode();data+=b' '*((-len(data))%4)
    return struct.pack('<4sIIII',b'glTF',2,len(data)+20,len(data),0x4E4F534A)+data


def glb_with_bounds(node=None):
    return glb(
        nodes=[node or {'mesh': 0}],
        accessors=[{'count': 4, 'type': 'VEC3', 'min': [-.5, -1, -.5], 'max': [.5, 1, .5]}],
        meshes=[{'primitives': [{'attributes': {'POSITION': 0}}]}],
    )


def test_scene_limits_and_asset_ownership():
    scene=default_scene();assert len(scene['objects'])==6
    assert scene_hash(scene)==scene_hash(validate_scene(scene,{}))
    for change in ['duplicate','nan','foreign','huge_path','infinite_duration']:
        bad=copy.deepcopy(scene)
        if change=='duplicate':bad['objects'][1]['id']=bad['objects'][0]['id']
        elif change=='nan':bad['objects'][0]['position'][0]=float('nan')
        elif change=='foreign':bad['objects'][0].update(kind='glb',asset='a'*32)
        elif change=='huge_path':bad['shots'][0]['camera']['points']=[[1,2,3]]*65
        else:bad['duration']=float('inf')
        with pytest.raises(ValueError):validate_scene(bad,{})


def test_glb_self_contained_bounded_graph():
    assert validate_glb(glb())['nodes']==1
    metadata = validate_glb(glb_with_bounds())
    assert metadata['bounds_status'] == 'available'
    assert metadata['bounds'] == {'min': [-.5, -1.0, -.5], 'max': [.5, 1.0, .5], 'size': [1.0, 2.0, 1.0]}
    transformed = validate_glb(glb_with_bounds({'mesh': 0, 'translation': [2, 3, 4], 'scale': [2, 1, 3]}))
    assert transformed['bounds'] == {'min': [1.0, 2.0, 2.5], 'max': [3.0, 4.0, 5.5], 'size': [2.0, 2.0, 3.0]}
    for raw in [b'bad',glb(images=[{'uri':'https://example.com/private.png'}]),
                glb(nodes=[{'children':[0]}]),glb(nodes=[{'children':[1]},{'children':[0]}]),
                glb(accessors=[{'count':4_000_000}]),glb(accessors=[{'count':-4_000_000},{'count':4_000_001}]),glb(extensionsRequired=['KHR_draco_mesh_compression'])]:
        with pytest.raises(ValueError):validate_glb(raw)


def test_scene_roundtrip_revision_owned_glb_and_handoff(client):
    p=ready(client);base='/creative/api/projects/'+p['id']+'/scene3d';doc=client.get(base).json()
    assert doc['project_skill']['id']=='ad-video';assert doc['reference_assets']==[]
    assert client.get(base,headers={'Authorization':'Bearer two'}).status_code==404
    spec=doc['spec'];spec['objects'][2]['position']=[1.25,2,3];spec['shots'][0]['camera']['points']=[[0,2,5],[2,3,1],[-2,1,2],[0,2,-4]]
    saved=client.put(base,json={'revision':p['revision'],'spec':spec});assert saved.status_code==200
    assert client.get(base).json()['spec']==saved.json()['spec']
    assert client.put(base,json={'revision':p['revision'],'spec':spec}).status_code==409
    revision=saved.json()['revision']
    raw_reference=io.BytesIO();Image.new('RGB',(120,80),'blue').save(raw_reference,format='PNG')
    uploaded_reference=client.post('/creative/api/projects/'+p['id']+'/canvas/assets',params={'kind':'image','revision':revision},content=raw_reference.getvalue());assert uploaded_reference.status_code==200
    reference_asset=uploaded_reference.json()['asset']['id'];revision=uploaded_reference.json()['project']['revision']
    scene_with_reference=client.get(base).json();assert scene_with_reference['reference_assets'][0]['id']==reference_asset;assert scene_with_reference['layout_observation']['status']=='clear';assert scene_with_reference['station_keyframe_observation']['training_eligible'] is False;assert scene_with_reference['layout_observation']['training_eligible'] is False;assert scene_with_reference['asset_task']['state']=='no_draft';assert scene_with_reference['asset_task']['next_action']=='save_draft'
    draft=client.post(base+'/asset-intent',json={'revision':revision,'model':'meshforge-3d-pro','skill_id':'ad-video','skill_version':1,'approval_mode':'manual','prompt':'黑色机车皮夹克，保留拉链、翻领和金属扣，生成可用于 3D-BOX 的 GLB。','reference_asset':reference_asset})
    assert draft.status_code==200,draft.text
    intent=draft.json()['asset_intent'];assert intent['state']=='draft';assert intent['model']=='meshforge-3d-pro';assert intent['skill_id']=='ad-video';assert intent['skill_title'];assert intent['skill_version']==1;assert intent['reference_asset']==reference_asset;assert intent['approval_mode']=='manual';assert intent['paid_generation'] is False;assert intent['provider_task_id'] is None;assert intent['training_eligible'] is False;assert intent['stale'] is False;assert draft.json()['asset_task']['state']=='draft';assert draft.json()['asset_task']['next_action']=='prepare_quote'
    quote=client.post(base+'/asset-intent/quote',json={'revision':draft.json()['revision']});assert quote.status_code==200,quote.text
    quoted=quote.json()['quote'];assert quoted['state']=='provider_unconfigured';assert quoted['provider_available'] is False;assert quoted['credits'] is None;assert quoted['requires_explicit_approval'] is True;assert quoted['approval_state']=='not_requested';assert quoted['paid_generation'] is False;assert quoted['provider_task_id'] is None;assert quoted['stale'] is False;assert len(quoted['quote_digest'])==64;assert quote.json()['task']['state']=='blocked_provider_unconfigured';assert quote.json()['task']['next_action']=='configure_provider'
    approval=client.post(base+'/asset-intent/approve',json={'revision':draft.json()['revision'],'quote_digest':quoted['quote_digest'],'confirm':'approve'});assert approval.status_code==200,approval.text
    approved=approval.json()['quote'];assert approved['approval_state']=='blocked_provider_unconfigured';assert approved['paid_generation'] is False;assert approved['provider_task_id'] is None;assert approved['approval_attempted_at'];assert approval.json()['task']['state']=='blocked_provider_unconfigured';assert approval.json()['task']['training_eligible'] is False
    assert client.get(base+'/asset-intent/quote').json()['quote']['approval_state']=='blocked_provider_unconfigured';assert client.get(base+'/asset-intent/status').json()['task']['state']=='blocked_provider_unconfigured'
    invalid_reference=client.post(base+'/asset-intent',json={'revision':draft.json()['revision'],'model':'meshforge-3d-pro','skill_id':'ad-video','skill_version':1,'approval_mode':'manual','prompt':'保留商品结构并生成 GLB','reference_asset':'a'*32});assert invalid_reference.status_code==422
    stale_saved=client.put(base,json={'revision':draft.json()['revision'],'spec':spec});assert stale_saved.status_code==200;assert stale_saved.json()['asset_intent']['stale'] is True
    revision=stale_saved.json()['revision']
    raw_glb = glb_with_bounds()
    uploaded=client.post(base+'/assets',params={'revision':revision},content=raw_glb);assert uploaded.status_code==200
    aid=uploaded.json()['asset']['id'];revision=uploaded.json()['revision']
    assert uploaded.json()['asset']['bounds_status']=='available'
    assert client.get(base+'/assets/'+aid,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(base+'/assets/'+aid).content==raw_glb
    raw=io.BytesIO();Image.new('RGB',(120,80),'blue').save(raw,format='PNG')
    result=client.post(base+'/reference',params={'revision':revision,'at':3},content=raw.getvalue());assert result.status_code==200
    current=store.load(p['id'],1);node=current['canvas']['nodes'][-1]
    assert current['state']=='intake' and current['shots']==[]
    assert node['label']=='3D 预演 · 3.0s'
    assert current['canvas']['edges'][-1]['source']==node['id']
    assert current['canvas_assets'][node['asset']]['provenance']['verified_render'] is False
    assert current['training_eligible'] is False
    assert all('spec' not in e and 'position' not in e for e in client.get('/creative/api/projects/'+p['id']).json()['events'])


def test_signed_scene_asset_callback_binds_owned_glb_and_is_idempotent(client, monkeypatch):
    secret='scene-asset-callback-secret';monkeypatch.setenv('CREATIVE_3D_ASSET_CALLBACK_SECRET',secret)
    p=ready(client);base='/creative/api/projects/'+p['id']+'/scene3d';doc=client.get(base).json()
    saved=client.put(base,json={'revision':p['revision'],'spec':doc['spec']});assert saved.status_code==200
    uploaded=client.post(base+'/assets',params={'revision':saved.json()['revision']},content=glb_with_bounds());assert uploaded.status_code==200
    aid=uploaded.json()['asset']['id'];revision=uploaded.json()['revision']
    draft=client.post(base+'/asset-intent',json={'revision':revision,'model':'meshforge-3d-pro','skill_id':'ad-video','skill_version':1,'approval_mode':'manual','prompt':'生成黑色皮夹克 GLB'})
    quote=client.post(base+'/asset-intent/quote',json={'revision':draft.json()['revision']});assert quote.status_code==200
    intent_id=draft.json()['asset_intent']['id'];project_id=p['id'];task_id='mesh-task-001'
    current=store.load(project_id,1);current['scene_asset_quote'].update(provider_available=True,approval_state='approved',provider_task_id=task_id);store.save(current,1)
    body={'project_id':project_id,'asset_intent_id':intent_id,'task_id':task_id,'status':'completed','progress':100,'result_asset_id':aid}
    raw=json.dumps(body,separators=(',',':')).encode();timestamp=str(int(time.time()));signature=hmac.new(secret.encode(),(timestamp+'.').encode()+raw,hashlib.sha256).hexdigest()
    headers={'X-Provider-Timestamp':timestamp,'X-Provider-Signature':'sha256='+signature}
    result=client.post('/creative/internal/scene-asset-callback',content=raw,headers=headers);assert result.status_code==200,result.text;assert result.json()['training_eligible'] is False
    status=client.get(base+'/asset-intent/status').json()['task'];assert status['state']=='needs_review';assert status['asset_id']==aid;assert status['progress']==100
    duplicate=client.post('/creative/internal/scene-asset-callback',content=raw,headers=headers);assert duplicate.status_code==200 and duplicate.json()['idempotent'] is True
    saved_callback=store.load(project_id,1);assert saved_callback['scene_asset_quote']['provider_task_id']==task_id;assert saved_callback['scene_asset_quote']['result_asset_id']==aid
    assert 'provider_payload' not in json.dumps(saved_callback)
    current_scene=client.get(base).json();bound=client.post(base+'/asset-intent/bind',json={'revision':current_scene['revision'],'asset_id':aid,'confirm':'bind'});assert bound.status_code==200,bound.text;bound_id=bound.json()['object_id'];assert any(obj['id']==bound_id and obj['asset']==aid for obj in bound.json()['scene']['spec']['objects']);assert bound.json()['scene']['asset_task']['state']=='bound'
    again=client.post(base+'/asset-intent/bind',json={'revision':bound.json()['scene']['revision'],'asset_id':aid,'confirm':'bind'});assert again.status_code==200 and again.json()['idempotent'] is True and again.json()['object_id']==bound_id
