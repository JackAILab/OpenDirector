import base64
import copy
import io
import json
import subprocess
from pathlib import Path
import pytest
from PIL import Image
from tests.test_creative_studio import client,ready
from tests.test_creative_scene import glb
from harness.studio import store
from harness.tools.creative_scene import default_scene,validate_scene,scene_hash,shot_at,trajectory_manifest,station_manifest,station_keyframe_observation,station_keyframe_tracks,layout_observation
from harness.tools.trajectory_evaluator import evaluate_trajectory


def three_shots():
    spec=default_scene();first=spec['shots'][0];first['duration']=3
    for i in range(2):
        s=copy.deepcopy(first);s.update(id='shot'+str(i+2),name='机位'+str(i+2),duration=i+2)
        s['camera'].update(fov=30+i*20,points=[[i+1,2,4],[i+1,2,4]],closed=False)
        spec['shots'].append(s)
    spec['duration']=8
    return spec


def test_legacy_migration_and_shot_contract():
    new=default_scene();old={k:v for k,v in new.items() if k!='shots'};old.update(version=1,camera=new['shots'][0]['camera'])
    migrated=validate_scene(old,{})
    assert migrated==new and old['version']==1
    spec=three_shots();assert validate_scene(spec,{})==spec
    for change in ('duplicate','empty','too_many','duration','sum','nan','path'):
        bad=copy.deepcopy(spec)
        if change=='duplicate':bad['shots'][1]['id']=bad['shots'][0]['id']
        elif change=='empty':bad['shots']=[]
        elif change=='too_many':bad['shots']=bad['shots']*5
        elif change=='duration':bad['shots'][0]['duration']=.1
        elif change=='sum':bad['duration']=30
        elif change=='nan':bad['shots'][1]['camera']['fov']=float('nan')
        else:bad['shots'][1]['camera']['points'][0][0]=float('inf')
        with pytest.raises(ValueError):validate_scene(bad,{})


def test_station_keyframes_are_bounded_to_movable_objects_and_shot_time():
    spec=default_scene();shot=spec['shots'][0];shot['station_keyframes']=[
        {'object_id':'bottle','at':0.0,'position':[0,1,0]},
        {'object_id':'bottle','at':5.0,'position':[1,1,0],'rotation':[0,30,0]},
    ]
    clean=validate_scene(spec,{})
    assert len(clean['shots'][0]['station_keyframes'])==2
    base_manifest=station_manifest(default_scene())
    keyframe_manifest=station_manifest(clean)
    assert keyframe_manifest['keyframe_count']==2
    assert keyframe_manifest['sha256']!=base_manifest['sha256']
    for bad in (
        [{'object_id':'missing','at':1,'position':[0,1,0]}],
        [{'object_id':'bottle','at':11,'position':[0,1,0]}],
        [{'object_id':'floor','at':1,'position':[0,0,0]}],
        [{'object_id':'bottle','at':1,'position':[0,1,0]}, {'object_id':'bottle','at':1,'position':[1,1,0]}],
    ):
        changed=copy.deepcopy(spec);changed['shots'][0]['station_keyframes']=bad
        with pytest.raises(ValueError): validate_scene(changed,{})


def test_station_keyframes_can_sync_multiple_objects_at_one_time():
    spec=default_scene();shot=spec['shots'][0];shot['station_keyframes']=[
        {'object_id':'bottle','at':1.5,'position':[0,1,0]},
        {'object_id':'cap','at':1.5,'position':[0,2.3,0],'rotation':[0,15,0]},
    ]
    clean=validate_scene(spec,{})
    assert len(clean['shots'][0]['station_keyframes'])==2
    manifest=station_manifest(clean)
    assert manifest['keyframe_count']==2
    assert 'keyframes' not in manifest and 'position' not in str(manifest)


def test_station_keyframe_tracks_report_coverage_missing_and_sync_without_transforms():
    spec=default_scene();shot=spec['shots'][0];shot['station_keyframes']=[
        {'object_id':'bottle','at':1.0,'position':[0,1,0]},
        {'object_id':'bottle','at':3.0,'position':[1,1,0]},
        {'object_id':'cap','at':1.0,'position':[0,2.3,0]},
    ]
    tracks=station_keyframe_tracks(validate_scene(spec,{}))
    row=tracks['shots'][0];by_id={item['object_id']:item for item in row['tracks']}
    assert by_id['bottle']['status']=='covered' and by_id['bottle']['start']==1.0 and by_id['bottle']['end']==3.0
    assert by_id['cap']['status']=='single'
    assert 'plinth' in row['missing_object_ids']
    assert row['sync_groups']==[{'at':1.0,'object_ids':['bottle','cap']}]
    assert 'position' not in str(tracks) and tracks['training_eligible'] is False
    conflicting=copy.deepcopy(spec);conflicting['shots'][0]['station_keyframes'].append({'object_id':'bottle','at':1.0,'position':[9,9,9]})
    conflict_row=station_keyframe_tracks(conflicting)['shots'][0]
    assert conflict_row['conflicts']==[{'object_id':'bottle','at':1.0}]


def test_station_keyframe_observation_reports_coordinate_free_risk_per_shot():
    spec=default_scene();shot=spec['shots'][0];shot['station_keyframes']=[
        {'object_id':'bottle','at':1.0,'position':[0,1.25,0]},
        {'object_id':'cap','at':1.0,'position':[0,1.4,0]},
    ]
    observation=station_keyframe_observation(validate_scene(spec,{}))
    row=observation['shots'][0]
    assert row['status']=='needs_check' and row['collision_count']==1
    assert row['collision_pairs']==[['bottle','cap']] and row['collision_times']==[1.0]
    assert row['keyframe_count']==2
    assert 'position' not in str(observation) and observation['training_eligible'] is False


def test_python_browser_boundaries_are_identical():
    spec=three_shots();times=[0,2.99,3,4.999,5,7.99,8]
    expected=[{k:v for k,v in shot_at(spec,t).items() if k!='shot'} for t in times]
    script="import {shotAt} from './tools/agent_studio/scene-timing.mjs';const spec="+json.dumps(spec)+";console.log(JSON.stringify("+json.dumps(times)+".map(t=>{const {shot,...state}=shotAt(spec,t);return state})))"
    actual=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],text=True))
    assert actual==expected and [s['index'] for s in expected]==[0,0,1,1,2,2,2]
    for t in (-.01,8.01,float('nan')):
        with pytest.raises(ValueError):shot_at(spec,t)


def test_browser_station_risk_sampling_merges_overlap_intervals():
    source={
        'objects':[
            {'id':'a','kind':'box','position':[0,0,0],'scale':[1,1,1],'visible':True},
            {'id':'b','kind':'box','position':[3,0,0],'scale':[1,1,1],'visible':True},
        ],
        'shots':[{'id':'s','station_keyframes':[{'object_id':'b','at':0,'position':[.4,0,0]}, {'object_id':'b','at':5,'position':[3,0,0]}]}],
    }
    script="import {sampleStationRisk} from './tools/agent_studio/scene-risk.mjs';const source="+json.dumps(source)+";console.log(JSON.stringify(sampleStationRisk(source,source.shots[0],5,{})))"
    observed=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],text=True))
    assert observed['samples']==17 and observed['peak']==1 and observed['intervals']
    assert len(observed['points'])==17 and observed['points'][0]['at']==0 and observed['points'][0]['count']==1
    assert observed['points'][0]['pairs']==[['a','b']]
    assert observed['points'][-1]['count']==0
    assert observed['pairIntervals'][0]['pair']==['a','b']
    assert observed['pairIntervals'][0]['samples'] < observed['samples']
    assert observed['intervals'][0]['start']==0 and observed['intervals'][0]['end']<5


def test_browser_station_risk_pair_intervals_keep_separated_runs():
    script="import {aggregateRiskPairs} from './tools/agent_studio/scene-risk.mjs';console.log(JSON.stringify(aggregateRiskPairs([{at:0,count:1,pairs:[['a','b']]},{at:1,count:1,pairs:[['a','b']]},{at:2,count:0,pairs:[]},{at:3,count:1,pairs:[['a','b']]}],4)))"
    observed=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],text=True))
    assert len(observed)==2 and [row['samples'] for row in observed]==[2,1]


def test_trajectory_manifest_is_bounded_and_changes_with_path():
    spec=default_scene();manifest=trajectory_manifest(spec)
    assert manifest['version']==1 and len(manifest['sha256'])==64
    assert len(manifest['shots'])==len(spec['shots'])
    row=manifest['shots'][0]
    assert {'shot_id','path_sha256','path_points','path_closed','path_easing','path_length','duration'} <= set(row)
    assert 'points' not in row and row['path_points']==len(spec['shots'][0]['camera']['points'])
    changed=copy.deepcopy(spec);changed['shots'][0]['camera']['points'][0][0]+=1
    changed_manifest=trajectory_manifest(changed)
    assert changed_manifest['sha256']!=manifest['sha256']
    assert changed_manifest['shots'][0]['path_sha256']!=row['path_sha256']


def test_scene_role_bindings_are_revision_and_scene_hash_bound(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];scene=client.get(url+'/scene3d').json();spec=scene['spec']
    object_id=next(item['id'] for item in spec['objects'] if item['kind'] not in ('light','plane'))
    shot_id=spec['shots'][0]['id']
    result=client.post(url+'/scene3d/role-bindings',json={
        'revision':scene['revision'],'scene_hash':scene['hash'],
        'bindings':[{'shot_id':shot_id,'object_id':object_id,'role':'product'}],'confirm':'save'})
    assert result.status_code==200,result.text
    view=result.json()['role_bindings'];assert view['bindings'][0]['object_id']==object_id
    assert view['bindings'][0]['role']=='product' and view['training_eligible'] is False
    assert client.get(url+'/scene3d').json()['role_bindings']['stale'] is False
    stale=client.post(url+'/scene3d/role-bindings',json={
        'revision':scene['revision'],'scene_hash':scene['hash'],'bindings':[], 'confirm':'save'})
    assert stale.status_code==409


def test_layout_observation_reports_primitive_overlap_and_unknown_glb_bounds():
    spec=default_scene()
    assert layout_observation(spec)=={'version':1,'status':'clear','collisions':[],'unknown_bounds':[],'training_eligible':False}
    changed=copy.deepcopy(spec)
    changed['objects'][2]['position']=[0,1.25,0]
    changed['objects'][3]['position']=[0,1.4,0]
    observed=layout_observation(changed)
    assert observed['status']=='needs_check' and len(observed['collisions'])==1
    assert {'a','a_name','b','b_name'}<=set(observed['collisions'][0])
    changed['objects'][2].update(kind='glb',asset='a'*32)
    unknown=layout_observation(changed)
    assert unknown['status']=='needs_check' and unknown['unknown_bounds'][0]['id']==changed['objects'][2]['id']
    assert 'position' not in str(unknown) and 'scale' not in str(unknown)


def test_layout_observation_uses_safe_glb_accessor_bounds_when_available():
    spec = default_scene()
    aid = 'a' * 32
    spec['objects'][2].update(kind='glb', asset=aid, position=[4, 1.2, 0])
    assets = {aid: {'bounds_status': 'available',
                    'bounds': {'min': [-.5, -1, -.5], 'max': [.5, 1, .5], 'size': [1, 2, 1]}}}
    observed = layout_observation(spec, assets)
    assert observed['status'] == 'clear'
    assert observed['unknown_bounds'] == []


def test_trajectory_evaluator_is_bounded_observation_and_never_approval():
    expected=[
        {'shot_id':'main','duration':5,'path_sha256':'a'*64,'path_points':4,'path_closed':True,'path_easing':'smooth'},
        {'shot_id':'end','duration':3,'path_sha256':'b'*64,'path_points':2,'path_closed':False,'path_easing':'linear'},
    ]
    observed={'shots':[
        {'shot_id':'main','duration':5.01,'path_sha256':'a'*64,'path_points':4,'path_closed':True,'path_easing':'smooth'},
        {'shot_id':'extra','duration':1,'path_sha256':'c'*64,'path_points':2,'path_closed':False},
    ]}
    result=evaluate_trajectory(expected,observed)
    assert result['status']=='partial_match' and result['matched_shots']==1
    assert result['expected_shots']==2 and result['observed_shots']==2
    assert result['extra_shots']==['extra'] and result['requires_human_review'] is True
    assert result['training_eligible'] is False
    assert 'points' not in str(result) and 'coordinates' not in str(result)
    assert result['shots'][1]['status']=='not_observed'


def png(color='red',size=(320,180)):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return base64.b64encode(out.getvalue()).decode()


def saved(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];spec=three_shots()
    scene=client.put(url+'/scene3d',json={'revision':p['revision'],'spec':spec}).json()
    body=dict(revision=scene['revision'],request_id='frames_fixed_001',scene_hash=scene['hash'],connect_to_director=False,
              frames=[dict(shot_id='main',at=0,png=png()),dict(shot_id='shot3',at=5,png=png('blue'))])
    return p,url,scene,body


def test_batch_handoff_preserves_plan_orders_frames_and_idempotency(client):
    p,url,scene,body=saved(client);body['frames'].reverse()
    before=client.get(url).json();r=client.post(url+'/scene3d/references',json=body);assert r.status_code==200,r.text
    result=r.json();after=client.get(url).json();assert after['shots']==before['shots'] and after['state']==before['state']
    assert [r['shot_id'] for r in result['references']]==['main','shot3']
    assert after['canvas']['edges']==[]
    nodes=after['canvas']['nodes'];assert nodes[1]['x']-nodes[0]['x']==310 and nodes[0]['y']==nodes[1]['y']
    for r in result['references']:
        origin=after['canvas_assets'][r['asset']]['provenance'];assert origin['scene_hash']==scene['hash'] and not origin['verified_render'] and not origin['training_eligible']
        assert origin['shot_id']==r['shot_id'] and origin['local_time']==0
    again=client.post(url+'/scene3d/references',json=body);assert again.json()==result
    assert client.get(url).json()['revision']==after['revision']
    assert client.post(url+'/scene3d/references',json={**body,'connect_to_director':True}).status_code==409
    assert 'points' not in str(after['events']) and body['frames'][0]['png'] not in str(after['events'])


def test_batch_rejects_stale_foreign_wrong_shot_and_bad_frames_atomically(client):
    p,url,scene,body=saved(client);before=client.get(url).json()
    assert client.post(url+'/scene3d/references',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url+'/scene3d/references',json={**body,'revision':0}).status_code==409
    edits=[dict(scene_hash='0'*64),dict(frames=[{**body['frames'][0],'at':3}]),dict(frames=body['frames']*2),dict(frames=[body['frames'][0],{**body['frames'][1],'png':'broken'}]),dict(frames=[{**body['frames'][0],'png':png(size=(180,320))}])]
    for delta in edits:assert client.post(url+'/scene3d/references',json={**body,**delta}).status_code==422
    assert client.get(url).json()==before
    assert not (store.DATA/'canvas'/p['id']).exists()


def test_explicit_director_connection_invalidates_plan_and_preserves_video_selection(client):
    p,url,scene,body=saved(client);before=store.load(p['id'],1);before['artifact']='fixed/final.mp4';before['film']={'inputs':{'mode':'text'}};before['auto_approval']={'remaining':1};store.save(before,1)
    result=client.post(url+'/scene3d/references',json={**body,'connect_to_director':True});assert result.status_code==200
    after=store.load(p['id'],1);assert after['shots']==[] and after['state']=='intake' and 'auto_approval' not in after
    assert len(after['canvas']['edges'])==2 and after['versions'][-1]['artifact']=='fixed/final.mp4'
    assert not after['training_eligible']


def test_legacy_scene_read_does_not_mutate_document_and_old_reference_maps_shot(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];new=default_scene();old={k:v for k,v in new.items() if k!='shots'};old.update(version=1,camera=new['shots'][0]['camera'])
    p['scene3d']=old;store.save(p,1)
    response=client.get(url+'/scene3d').json();assert response['spec']['version']==2 and store.load(p['id'],1)['scene3d']==old
    r=client.post(url+'/scene3d/reference',params={'revision':p['revision'],'at':2},content=base64.b64decode(png()));assert r.status_code==200
    assert r.json()['asset']['provenance']['shot_id']=='main'


def test_scene_edits_wait_for_active_image_production(client):
    p,url,scene,body=saved(client);current=store.load(p['id'],1);current['image_task']={'state':'running'};store.save(current,1)
    assert client.put(url+'/scene3d',json={'revision':current['revision'],'spec':scene['spec']}).status_code==409
    assert client.post(url+'/scene3d/references',json=body).status_code==409
    assert store.load(p['id'],1)==current


def test_render_preflight_is_read_only_then_confirms_versioned_intent(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];scene=client.get(url+'/scene3d').json();assert len(scene['station_manifest']['sha256'])==64;saved_initial=client.put(url+'/scene3d',json={'revision':p['revision'],'spec':scene['spec']});assert saved_initial.status_code==200
    p=client.get(url).json();before=store.load(p['id'],1)
    first=client.get(url+'/scene3d/render-preflight');assert first.status_code==200
    packet=first.json();assert packet['ready'] is False
    assert {c['id'] for c in packet['checks'] if c['status']=='needs_check'} >= {'product_asset','reference_frames'}
    assert store.load(p['id'],1)==before

    scene=client.get(url+'/scene3d').json();uploaded=client.post(url+'/scene3d/assets',params={'revision':p['revision']},content=glb());assert uploaded.status_code==200
    aid=uploaded.json()['asset']['id'];revision=uploaded.json()['revision'];spec=copy.deepcopy(scene['spec'])
    spec['objects']=[o for o in spec['objects'] if '占位' not in o.get('name','')]
    product=copy.deepcopy(spec['objects'][0]);product.update(id='real_product',kind='glb',name='真实商品 GLB',asset=aid);spec['objects'].append(product)
    saved=client.put(url+'/scene3d',json={'revision':revision,'spec':spec});assert saved.status_code==200
    ready_packet=client.get(url+'/scene3d/render-preflight').json();assert ready_packet['ready'] is True
    assert len(ready_packet['trajectory_sha256'])==64 and ready_packet['trajectory']['sha256']==ready_packet['trajectory_sha256']
    assert len(ready_packet['station_sha256'])==64
    assert ready_packet['shots'][0]['path_sha256']==ready_packet['trajectory']['shots'][0]['path_sha256']
    assert 'points' not in ready_packet['trajectory']['shots'][0]
    body={k:ready_packet[k] for k in ('scene_hash','model','approval_mode','aspect')};body['revision']=ready_packet['revision']
    body['trajectory_sha256']=ready_packet['trajectory_sha256']
    assert client.post(url+'/scene3d/render-intent',json={**body,'trajectory_sha256':'0'*64}).status_code==409
    confirmed=client.post(url+'/scene3d/render-intent',json=body);assert confirmed.status_code==200,confirmed.text
    result=confirmed.json();assert result['intent']['scene_revision']==ready_packet['revision'];assert result['project']['revision']==ready_packet['revision']+1
    assert result['project']['scene_render_intent']['scene_hash']==ready_packet['scene_hash']
    assert result['project']['scene_render_intent']['trajectory_sha256']==ready_packet['trajectory_sha256']
    assert result['project']['scene_render_intent']['station_sha256']==ready_packet['station_sha256']
    assert client.get(url).json()['events'][-1]['code']=='scene_render_intent_confirmed'
    duplicate=client.post(url+'/scene3d/render-intent',json=body);assert duplicate.status_code==200;assert duplicate.json()['project']['revision']==result['project']['revision']
    current_scene=client.get(url+'/scene3d').json();changed=client.put(url+'/scene3d',json={'revision':result['project']['revision'],'spec':current_scene['spec']});assert changed.status_code==200
    assert 'scene_render_intent' not in client.get(url).json()


def test_render_review_binds_completed_artifact_and_records_manual_deviation(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];scene=client.get(url+'/scene3d').json()
    uploaded=client.post(url+'/scene3d/assets',params={'revision':p['revision']},content=glb());assert uploaded.status_code==200
    aid=uploaded.json()['asset']['id'];spec=copy.deepcopy(scene['spec']);spec['objects']=[o for o in spec['objects'] if '占位' not in o.get('name','')]
    product=copy.deepcopy(spec['objects'][0]);product.update(id='review_product',kind='glb',name='回放商品 GLB',asset=aid);spec['objects'].append(product)
    saved=client.put(url+'/scene3d',json={'revision':uploaded.json()['revision'],'spec':spec});assert saved.status_code==200
    packet=client.get(url+'/scene3d/render-preflight').json();intent=client.post(url+'/scene3d/render-intent',json={**{k:packet[k] for k in ('scene_hash','model','approval_mode','aspect')},'revision':packet['revision']}).json()
    current=store.load(p['id'],1);current.update(state='completed',artifact='artifacts/review/final.mp4',qa={'technical':'passed','duration':current['duration'],'width':1280,'height':720,'audio':True},film={'provider_trajectory':{'version':1,'source':'provider_status','observed':True,'sha256':'b'*64,'shots':[{'shot_id':'main','duration':5,'path_sha256':'a'*64,'path_points':2,'path_closed':False}],'training_eligible':False}});path=store.DATA/current['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'fixture-final');store.save(current,1)
    review_packet=client.get(url+'/scene3d/render-review');assert review_packet.status_code==200;review_packet=review_packet.json();assert review_packet['state']=='ready';assert review_packet['media']['asset']=='final';assert review_packet['trajectory_evaluation']['status']=='manual_review_required';assert review_packet['trajectory_evaluation']['provider_metadata']['status']=='metadata_mismatch';assert review_packet['provider_trajectory']['shots'][0]['path_sha256']=='a'*64;assert 'points' not in review_packet['provider_trajectory']['shots'][0];assert review_packet['trajectory_lock']['status']=='locked';assert review_packet['shots'][0]['path_sha256'];assert review_packet['shots'][0]['status']=='not_reviewed'
    body={'revision':review_packet['project_revision'],'scene_revision':review_packet['scene_revision'],'scene_hash':review_packet['scene_hash'],'artifact_sha256':review_packet['artifact_sha256'],'decision':'changes_requested','note':'镜头站位需要重新核对','shots':[{'shot_id':shot['id'],'status':'deviation' if i==0 else 'aligned','note':'轨迹需要回看' if i==0 else ''} for i,shot in enumerate(review_packet['shots'])]}
    saved_review=client.post(url+'/scene3d/render-review',json=body);assert saved_review.status_code==200,saved_review.text;assert saved_review.json()['review']['decision']=='changes_requested';assert saved_review.json()['packet']['reviewed'] is True
    event_count=len(client.get(url).json()['events']);duplicate=client.post(url+'/scene3d/render-review',json=body);assert duplicate.status_code==200;assert duplicate.json()['review']['created_at']==saved_review.json()['review']['created_at'];assert len(client.get(url).json()['events'])==event_count
    accepted={**body,'decision':'accepted'};assert client.post(url+'/scene3d/render-review',json=accepted).status_code==422


def test_render_review_deviation_creates_explicit_retake_quote_and_approval(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];scene=client.get(url+'/scene3d').json()
    uploaded=client.post(url+'/scene3d/assets',params={'revision':p['revision']},content=glb());assert uploaded.status_code==200
    aid=uploaded.json()['asset']['id'];spec=copy.deepcopy(scene['spec']);spec['objects']=[o for o in spec['objects'] if '占位' not in o.get('name','')]
    product=copy.deepcopy(spec['objects'][0]);product.update(id='retake_product',kind='glb',name='重拍商品 GLB',asset=aid);spec['objects'].append(product)
    saved=client.put(url+'/scene3d',json={'revision':uploaded.json()['revision'],'spec':spec});assert saved.status_code==200
    packet=client.get(url+'/scene3d/render-preflight').json();intent=client.post(url+'/scene3d/render-intent',json={**{k:packet[k] for k in ('scene_hash','model','approval_mode','aspect')},'revision':packet['revision']}).json()
    current=store.load(p['id'],1);current.update(state='completed',artifact='artifacts/retake/final.mp4',qa={'technical':'passed','duration':current['duration'],'width':1280,'height':720,'audio':True});path=store.DATA/current['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'fixture-retake');store.save(current,1)
    review_packet=client.get(url+'/scene3d/render-review').json()
    review_body={'revision':review_packet['project_revision'],'scene_revision':review_packet['scene_revision'],'scene_hash':review_packet['scene_hash'],'artifact_sha256':review_packet['artifact_sha256'],'decision':'changes_requested','note':'首镜头站位偏移','shots':[{'shot_id':shot['id'],'status':'deviation' if i==0 else 'aligned','note':'首镜头需要重拍' if i==0 else ''} for i,shot in enumerate(review_packet['shots'])]}
    reviewed=client.post(url+'/scene3d/render-review',json=review_body).json();review_packet=reviewed['packet']
    prepare_body={'revision':review_packet['project_revision'],'scene_revision':review_packet['scene_revision'],'scene_hash':review_packet['scene_hash'],'artifact_sha256':review_packet['artifact_sha256'],'request_id':'a'*16,'intent':'保持商品外观，修正首镜头站位与环绕轨迹。'}
    prepared=client.post(url+'/scene3d/render-review/retake-suggestions',json=prepare_body);assert prepared.status_code==200,prepared.text
    suggestion=prepared.json()['suggestion'];assert suggestion['state']=='ready_for_approval';assert len(suggestion['trajectory_sha256'])==64;assert suggestion['requires_explicit_approval'] is True;assert suggestion['credits']>0;assert suggestion['segments'][0]['status']=='deviation';assert suggestion['training_eligible'] is False
    again=client.post(url+'/scene3d/render-review/retake-suggestions',json=prepare_body);assert again.status_code==200;assert again.json()['suggestion']['id']==suggestion['id'];assert len(client.get(url).json()['events'])==len(reviewed['project']['events'])+1
    approve_url=url+'/scene3d/render-review/retake-suggestions/'+suggestion['id']+'/approve';approve_body={'revision':suggestion['project_revision'],'suggestion_id':suggestion['id'],'quote_digest':suggestion['quote_digest'],'approved_credits':suggestion['credits']}
    approved=client.post(approve_url,json=approve_body);assert approved.status_code==200,approved.text;assert approved.json()['suggestion']['state']=='approved_for_generation';assert approved.json()['suggestion']['approved_credits']==suggestion['credits'];assert not store.RUNNING
    current=store.load(p['id'],1);current['edit_retakes']={'e'*32:{'id':'e'*32,'scene_retake_id':suggestion['id'],'state':'completed','credits':suggestion['credits'],'candidate_sha256':'c'*64,'training_eligible':False,'asset':'edit_'+'e'*32,'clip':{'source':'primary','start':0,'end':3},'duration':3,'created_at':1}};store.save(current,1)
    packet_with_candidate=client.get(url+'/scene3d/render-review').json();assert packet_with_candidate['retake_suggestions'][0]['candidate']['state']=='completed';assert packet_with_candidate['retake_suggestions'][0]['candidate']['candidate_sha256']=='c'*64
    assert packet_with_candidate['retake_suggestions'][0]['candidate']['media']['source_start']==0
    duplicate=client.post(approve_url,json=approve_body);assert duplicate.status_code==200;assert duplicate.json()['suggestion']['approved_at']==approved.json()['suggestion']['approved_at']
    assert client.post(approve_url,json={**approve_body,'approved_credits':suggestion['credits']+1}).status_code==409
