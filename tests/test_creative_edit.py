import json
import subprocess
import time
import pytest
from harness.studio import store,edit_api
from harness.tools.creative_edit import validate_edit,initial_edit,skill_rhythm,skill_track_plan,skill_material_bindings,skill_version_impact,digest
from harness.studio.edit_api import scene_handoff_view, creative_review_summary
from harness.tools.creative_scene import station_keyframe_observation
from harness.tools import creative_edit_media as media
from harness.tools.creative_scene import station_manifest
from test_creative_studio import client,ready


def test_edit_bounds_source_binding_and_caption_clock():
    spec={'source_sha256':'abc','clips':[{'start':5,'end':8},{'start':1,'end':3}],
          'captions':[{'start':0,'end':2,'text':'<script>安全字幕</script>'}],'volume':.5}
    clean=validate_edit(spec,15,'abc');assert clean['duration']==5
    for bad in [dict(spec,source_sha256='old'),dict(spec,volume=float('nan')),
                dict(spec,clips=[{'start':0,'end':16}]),dict(spec,clips=[]),
                dict(spec,captions=[{'start':4,'end':6,'text':'越界'}])]:
        with pytest.raises(ValueError):validate_edit(bad,15,'abc')


def test_final_only_source_does_not_duplicate_burned_captions():
    p={'duration':15,'shots':[{'start':0,'duration':5,'caption':'已经烧录'}]}
    assert initial_edit(p,'hash')['captions']==[]


def test_skill_rhythm_is_bounded_and_preserved_as_editable_metadata():
    p={'duration':15,'skill':{'steps':['0–5 秒 · 吸引注意','5–10 秒 · 证明细节','10–15 秒 · 场景归因'],
                              'checks':['商品一致','卖点有证据','行动入口真实']}}
    rhythm=skill_rhythm(p)
    assert [(item['start'],item['end']) for item in rhythm]==[(0,5),(5,10),(10,15)]
    spec=validate_edit({'source_sha256':'hash','clips':[{'start':0,'end':15}],
                        'rhythm':rhythm},15,'hash')
    assert spec['rhythm'][1]['label']=='证明细节' and spec['rhythm'][2]['check']=='行动入口真实'
    with pytest.raises(ValueError):
        validate_edit({'source_sha256':'hash','clips':[{'start':0,'end':15}],
                       'rhythm':[{'start':0,'end':16,'label':'越界'}]},15,'hash')


def test_skill_track_plan_reports_bounded_multitrack_coverage():
    project={'duration':15,'skill':{'steps':['设计三个节拍','后期字幕与口播'],'checks':['字幕来自后期','旁白可听']}}
    spec={'rhythm':[{'start':0,'end':5,'label':'开场'},{'start':5,'end':10,'label':'证明'}],
          'clips':[{'start':0,'end':5},{'start':5,'end':10}],
          'captions':[{'start':0,'end':5,'text':'开场'}],
          'audio':[{'start':0,'end':5,'at':0}]}
    plan=skill_track_plan(project,spec)
    assert plan['summary']=={'beats':2,'picture_covered':2,'caption_required':True,
                              'caption_covered':1,'audio_required':True,'audio_covered':1,'gaps':2}
    assert plan['beats'][0]['picture_indices']==[0]
    assert plan['beats'][1]['picture_status']=='covered'
    assert plan['beats'][1]['caption_status']=='missing' and plan['beats'][1]['audio_status']=='missing'
    assert plan['training_eligible'] is False


def test_skill_track_plan_reports_same_track_collisions_without_mutating_spec():
    project={'duration':10,'skill':{'steps':['后期字幕'],'checks':['字幕可读']}}
    spec={'rhythm':[{'start':0,'end':10,'label':'整段'}],
          'clips':[{'start':0,'end':10}],
          'captions':[{'start':0,'end':4,'text':'一','track':0},
                      {'start':3,'end':6,'text':'二','track':0}],
          'audio':[]}
    before=json.loads(json.dumps(spec))
    plan=skill_track_plan(project,spec)
    assert plan['constraints']['status']=='caption_overlap'
    assert plan['constraints']['caption_collisions']==[{'kind':'caption','track':0,'left_index':0,'right_index':1}]
    assert plan['constraints']['requires_manual_review'] is True
    assert spec==before


def test_skill_version_impact_is_read_only_and_compares_track_gaps():
    project={'duration':15,'skill':{'version':1,'steps':['0–15 秒 · 展示商品'],
                                    'checks':['商品一致']}}
    spec={'clips':[{'start':0,'end':15}], 'captions':[], 'audio':[]}
    impact=skill_version_impact(project,spec,{'version':2,
        'steps':['0–7 秒 · 展示商品','7–15 秒 · 添加字幕与旁白'],
        'checks':['商品一致','字幕可读','旁白可听']})
    assert impact['from_version']==1 and impact['to_version']==2
    assert {item['field'] for item in impact['changed_fields']}=={'steps','checks'}
    assert impact['track_plan']['before']['beats']==1
    assert impact['track_plan']['after']['beats']==2
    assert impact['requires_explicit_confirmation'] is True
    assert impact['training_eligible'] is False


def test_scene_handoff_view_binds_current_3d_timeline_application():
    project={'revision':4,'scene3d':{'objects':[{'id':'jacket','name':'商品外观','kind':'glb'},{'id':'model','name':'人物模特','kind':'glb'}],'shots':[{'id':'shot-1','name':'商品特写','duration':3},{'id':'shot-2','name':'人物展示','duration':7}]},
             'scene_render_intent':{'scene_revision':3,'scene_hash':'a'*64,'trajectory_sha256':'b'*64},
             'scene_render_review':{'decision':'accepted'},
             'scene_timeline_applications':{'app-1':{'revision_after':4,'scene_hash':'a'*64}}}
    handoff=scene_handoff_view(project)
    assert handoff['state']=='timeline_applied'
    assert handoff['shot_count']==2 and handoff['current_application_count']==1
    assert handoff['role_objects']==[{'object_id':'jacket','name':'商品外观','role':'product'},{'object_id':'model','name':'人物模特','role':'person'}]
    assert handoff['shot_windows']==[{'shot_id':'shot-1','name':'商品特写','role':'product','start':0.0,'end':3.0,'duration':3.0},{'shot_id':'shot-2','name':'人物展示','role':'person','start':3.0,'end':10.0,'duration':7.0}]
    assert handoff['trajectory']=='locked' and handoff['render_review']=='accepted'
    assert handoff['training_eligible'] is False


def test_scene_handoff_reports_bounded_keyframe_summary_and_stale_path_review():
    project={'revision':4,'scene3d':{'objects':[],'shots':[
        {'id':'shot-1','name':'商品特写','duration':3,'camera':{'points':[[0,2,4],[1,2,3],[2,2,2]],'closed':False,'easing':'smooth'}},
    ]},'scene_render_intent':{'scene_revision':3,'scene_hash':'a'*64,'trajectory_sha256':'b'*64}}
    handoff=scene_handoff_view(project)
    assert handoff['trajectory_shots']==[{'shot_id':'shot-1','path_points':3,'path_closed':False,'path_easing':'smooth'}]
    assert handoff['trajectory_stale'] is True
    summary=creative_review_summary(handoff,{'constraints':{}},{'shot_bindings':[]})
    assert any(item['kind']=='trajectory' and '关键帧路径' in item['message'] for item in summary['items'])
    assert summary['training_eligible'] is False


def test_scene_handoff_projects_object_keyframe_times_without_transforms():
    scene={'objects':[{'id':'product','name':'商品外观','kind':'box','position':[0,1,0],'scale':[1,1,1]}],
           'shots':[{'id':'shot-1','name':'商品特写','duration':3,
                     'station_keyframes':[{'object_id':'product','at':0.25,'position':[1,2,3]},
                                          {'object_id':'product','at':2.5,'position':[4,5,6], 'rotation':[0,30,0]}]}]}
    handoff=scene_handoff_view({'revision':1,'scene3d':scene})
    assert handoff['station_keyframes']==[{'shot_id':'shot-1','keyframe_count':2,'object_ids':['product','product'],'times':[0.25,2.5]}]
    assert 'position' not in json.dumps(handoff, ensure_ascii=False)
    assert 'rotation' not in json.dumps(handoff, ensure_ascii=False)


def test_scene_handoff_projects_object_keyframe_tracks_without_transforms():
    scene={'objects':[{'id':'product','name':'商品外观','kind':'box','position':[0,1,0],'scale':[1,1,1]},
                      {'id':'cap','name':'瓶盖','kind':'cylinder','position':[0,2,0],'scale':[1,1,1]},
                      {'id':'floor','name':'地面','kind':'plane','position':[0,0,0],'scale':[1,1,1]}],
           'shots':[{'id':'shot-1','name':'商品特写','duration':3,
                     'station_keyframes':[{'object_id':'product','at':0.5,'position':[1,2,3]},
                                          {'object_id':'cap','at':0.5,'position':[4,5,6]}]}]}
    handoff=scene_handoff_view({'revision':1,'scene3d':scene})
    track=handoff['station_keyframe_tracks']['shots'][0]
    assert track['missing_object_ids']==[]
    assert track['sync_groups']==[{'at':0.5,'object_ids':['cap','product']}]
    assert {row['object_id'] for row in track['tracks']}=={'cap','product'}
    assert 'position' not in json.dumps(handoff, ensure_ascii=False)


def test_station_keyframe_observation_surfaces_collision_without_coordinates():
    scene={'objects':[{'id':'a','name':'商品 A','kind':'box','position':[-3,1,0],'scale':[2,2,2]},
                      {'id':'b','name':'商品 B','kind':'box','position':[3,1,0],'scale':[2,2,2]}],
           'shots':[{'id':'shot-1','name':'商品特写','duration':3,
                     'station_keyframes':[{'object_id':'b','at':1,'position':[-3,1,0]}]}]}
    observation=station_keyframe_observation(scene)
    assert observation['shots']==[{'shot_id':'shot-1','keyframe_count':1,'status':'needs_check','collision_count':1,'collision_pairs':[['a','b']],'collision_times':[1.0],'collision_pairs_by_time':[{'at':1.0,'pairs':[['a','b']]}],'unknown_bounds_count':0}]
    handoff=scene_handoff_view({'revision':1,'scene3d':scene})
    assert handoff['station_keyframe_observation']['shots'][0]['status']=='needs_check'
    assert 'position' not in json.dumps(handoff, ensure_ascii=False)
    summary=creative_review_summary(handoff, {'constraints':{}}, {'shot_bindings':[]})
    assert any('对象关键帧需要核对' in item['message'] for item in summary['items'])


def test_scene_handoff_projects_bounded_station_observation_and_review():
    project={'revision':2,'scene3d':{
        'objects':[
            {'id':'a','name':'商品占位 A','kind':'box','position':[0,1,0],'scale':[2,2,2]},
            {'id':'b','name':'商品占位 B','kind':'box','position':[0,1,0],'scale':[2,2,2]},
        ],
        'shots':[{'id':'shot-1','name':'商品特写','duration':3}],
    }}
    handoff=scene_handoff_view(project)
    assert handoff['layout_observation']['status']=='needs_check'
    assert len(handoff['layout_observation']['collisions'])==1
    assert 'position' not in json.dumps(handoff, ensure_ascii=False)
    summary=creative_review_summary(handoff, {'constraints':{}}, {'shot_bindings':[]})
    station=[item for item in summary['items'] if item['kind']=='station']
    assert len(station)==1 and '重叠 1 组' in station[0]['message']
    assert summary['training_eligible'] is False


def test_scene_handoff_reports_station_change_without_exposing_transforms():
    scene={'objects':[{'id':'product','name':'商品外观','kind':'box','position':[0,1,0],'scale':[1,1,1]}],
           'shots':[{'id':'shot-1','name':'商品特写','duration':3}]}
    project={'revision':2,'scene3d':scene,'scene_render_intent':{'scene_hash':'a'*64,
             'station_sha256':'b'*64,'trajectory_sha256':'c'*64}}
    handoff=scene_handoff_view(project)
    assert handoff['station_stale'] is True
    assert handoff['station_objects']==[{'object_id':'product','role':'product','placement_sha256':station_manifest(scene)['objects'][0]['placement_sha256'][:12]}]
    assert 'position' not in json.dumps(handoff, ensure_ascii=False)
    summary=creative_review_summary(handoff, {'constraints':{}}, {'shot_bindings':[]})
    assert any(item['kind']=='station' and '对象站位' in item['message'] for item in summary['items'])


def test_skill_material_bindings_are_read_only_and_role_scoped():
    project={'skill':{'references':['商品外观与材质','人物出镜'],'steps':['场景氛围']},
             'canvas':{'nodes':[
                 {'id':'product-node','kind':'image','role':'product','label':'商品图'},
                 {'id':'person-node','kind':'image','role':'person','label':'人物图'},
             ]}}
    result=skill_material_bindings(project)
    assert result['training_eligible'] is False
    assert [(row['role'],row['status']) for row in result['rows']]==[
        ('product','matched'),('person','matched'),('scene','missing')]
    assert result['rows'][0]['candidate_labels']==['商品图']
    shot=skill_material_bindings({**project,'duration':10,'skill':{'steps':['0–5 秒 · 展示商品','5–10 秒 · 人物出镜']}})['shot_bindings']
    assert [(item['role'],item['status']) for item in shot]==[('product','matched'),('person','matched')]
    assert shot[0]['start']==0 and shot[1]['end']==10
    video_project={**project,'duration':10,'canvas':{'nodes':[
        {'id':'video-node','kind':'video','role':'person','asset':'f'*32,'label':'人物视频'}]}}
    video_shot=skill_material_bindings({**video_project,'skill':{'steps':['0–10 秒 · 人物出镜']}})['shot_bindings'][0]
    assert video_shot['candidate_source_ids']==['canvas_'+'f'*32]


def test_creative_review_summary_combines_scene_tracks_and_material_gaps():
    summary=creative_review_summary(
        {'state':'scene_ready','trajectory':'needs_review'},
        {'constraints':{'caption_collisions':[{'left_index':0,'right_index':1}]}},
        {'shot_bindings':[{'status':'missing'},{'status':'matched'}]})
    assert summary['status']=='needs_review'
    assert [item['kind'] for item in summary['items']]==['3d','trajectory','caption','material']
    assert [item['target'] for item in summary['items']]==['scene_handoff','scene_handoff','track_plan','material_bindings']
    assert summary['items'][2]['severity']=='block'
    assert summary['training_eligible'] is False


def test_creative_review_summary_flags_trajectory_review_and_shot_timing_gaps():
    summary=creative_review_summary(
        {'state':'timeline_applied','trajectory':'locked','render_review':'changes_requested',
         'shot_windows':[{'duration':3},{'duration':5}]},
        {'beats':[{'start':0,'end':4}], 'constraints':{}},
        {'shot_bindings':[]})
    assert [item['kind'] for item in summary['items']]==['3d','trajectory','timing']
    assert summary['items'][1]['severity']=='block'
    assert summary['items'][2]['target']=='track_plan'


def test_creative_review_summary_flags_scene_and_skill_role_mismatch():
    summary=creative_review_summary(
        {'state':'timeline_applied','trajectory':'locked','shot_windows':[
            {'role':'product'}, {'role':'person'}]},
        {'beats':[{'start':0,'end':5},{'start':5,'end':10}], 'constraints':{}},
        {'shot_bindings':[{'role':'person'},{'role':'product'}]})
    assert summary['items'][-1]['kind']=='role'
    assert summary['items'][-1]['message']=='3D 镜头与 Skill 节拍有 2 处角色不一致'
    assert summary['items'][-1].get('shot_id') is None


def test_creative_review_summary_prefers_fresh_explicit_role_binding():
    summary=creative_review_summary(
        {'state':'timeline_applied','trajectory':'locked','role_bindings_stale':False,
         'role_bindings':[{'shot_id':'shot-1','role':'person'}],
         'shot_windows':[{'shot_id':'shot-1','role':None}]},
        {'beats':[{'start':0,'end':5}], 'constraints':{}},
        {'shot_bindings':[{'role':'product'}]})
    assert summary['items'][-1]['kind']=='role'
    assert summary['items'][-1]['scene_role']=='person'


def source_project(client,monkeypatch):
    p=ready(client);directory=store.DATA/'artifacts'/'existing';directory.mkdir(parents=True)
    path=directory/'film.mp4';path.write_bytes(b'fixture-source')
    p.update(state='completed',run_id='existing',film={'state':'completed'},artifact='artifacts/existing/final.mp4')
    store.save(p,1)
    monkeypatch.setattr(media,'describe',lambda path:dict(sha256=digest(path),duration=15,kind='video',has_audio=True,width=1280,height=720))
    return p


def test_editor_owner_revisions_non_overwriting_export(client,monkeypatch):
    p=source_project(client,monkeypatch);base='/creative/api/projects/'+p['id']+'/edit'
    assert client.get(base,headers={'Authorization':'Bearer two'}).status_code==404
    doc=client.get(base).json();assert 'track_plan' in doc['creative_context'];assert 'skill_impact' in doc['creative_context'];assert doc['creative_context']['track_plan']['training_eligible'] is False;spec=doc['spec'];spec['clips']=[{'start':2,'end':7}];spec['captions']=[{'start':0,'end':2,'text':'字幕'}]
    saved=client.put(base,json={'revision':p['revision'],'spec':spec}).json()
    assert saved['spec']['duration']==5
    assert client.put(base,json={'revision':p['revision'],'spec':spec}).status_code==409
    assert store.load(p['id'],1)['artifact']==p['artifact']
    exports=[]
    def render(project,spec,directory):
        directory.mkdir(parents=True,exist_ok=False);(directory/'final.mp4').write_bytes(b'edited')
        exports.append(directory);return {'technical':'passed','audio':True,'training_eligible':False}
    monkeypatch.setattr(edit_api,'render_edit',render)
    for _ in range(2):
        r=client.post(base+'/export',json={'revision':saved['revision']});assert r.status_code==200
        for _ in range(100):
            if client.get(base).json()['export']['state']=='completed':break
            time.sleep(.01)
        assert client.get(base+'/media').content==b'edited'
    assert len(exports)==2 and exports[0]!=exports[1]
    assert client.get(base+'/media',headers={'Authorization':'Bearer two'}).status_code==404
    assert (store.DATA/'artifacts/existing/film.mp4').read_bytes()==b'fixture-source'


def test_editor_projects_approved_scene_retake_context_without_secrets(client,monkeypatch):
    p=source_project(client,monkeypatch);suggestion_id='c'*32
    p['scene_render_intent']={'scene_hash':'a'*64}
    p['scene_render_review']={'artifact_sha256':'b'*64}
    p['scene_retake_suggestions']={suggestion_id:{
        'id':suggestion_id,'state':'approved_for_generation','model':'kling-video-v3_0',
        'model_label':'Kling 3.0','approval_mode':'manual','aspect':'16:9',
        'intent':'修正首镜头站位','segments':[{'shot_id':'main','name':'主机位',
        'start':0,'end':5,'duration':5,'billable_duration':5,'credits':3,
        'status':'deviation','note':'站位偏移'}],'credits':3,'quote_digest':'d'*64,
        'scene_revision':1,'scene_hash':'a'*64,'artifact_sha256':'b'*64,
        'requires_explicit_approval':True,'training_eligible':False,
        'request_digest':'e'*64}}
    p['canvas_assets']={
        'a'*32:{'id':'a'*32,'kind':'image','sha256':'1'*64,'provenance':{
            'kind':'scene_browser_preview','scene_hash':'a'*64,'shot_id':'main',
            'shot_name':'主机位','shot_index':0,'at':0,'local_time':0}},
        'b'*32:{'id':'b'*32,'kind':'image','sha256':'2'*64,'provenance':{
            'kind':'scene_browser_preview','scene_hash':'0'*64,'shot_id':'old',
            'shot_name':'旧版本','shot_index':0,'at':0,'local_time':0}},
    }
    p['scene_reference_batches']={'r'*32:{'references':[
        {'asset':'a'*32,'shot_id':'main','at':0},
        {'asset':'b'*32,'shot_id':'old','at':0},
    ]}}
    p['edit_retakes']={'f'*32:{'id':'f'*32,'scene_retake_id':suggestion_id,'state':'completed',
                               'credits':3,'approved_credits':3,'asset':'edit_'+'f'*32,
                               'candidate_sha256':'c'*64,'qa':{'technical':'passed'},
                               'training_eligible':False,'provider_job_id':'secret-provider-id',
                               'clip':{'source':'primary','start':0,'end':5},'duration':5,
                               'created_at':1}}
    store.save(p,1);base='/creative/api/projects/'+p['id']+'/edit'
    context=client.get(base+'?scene_retake='+suggestion_id).json()['scene_retake']
    assert context['state']=='approved_for_generation'
    assert context['segments'][0]['start']==0 and context['stale'] is False
    assert context['editor_url'].endswith('scene_retake='+suggestion_id)
    assert 'request_digest' not in context
    assert context['candidate']['state']=='completed' and 'provider_job_id' not in context['candidate']
    assert context['references'][0]['asset']=='a'*32 and context['references'][0]['training_eligible'] is False
    assert len(context['references'])==1 and 'preview_url' in context['references'][0]
    assert context['candidate']['media']['source_start']==0
    assert context['candidate']['media']['candidate_url'].endswith('/edit/sources/edit_'+'f'*32)
    assert 'provider_job_id' not in json.dumps(context)
    p['scene_render_review']['artifact_sha256']='f'*64;store.save(p,1)
    assert client.get(base+'?scene_retake='+suggestion_id).json()['scene_retake']['stale'] is True


def test_scene_candidate_review_is_version_bound_and_idempotent(client,monkeypatch):
    p=source_project(client,monkeypatch);suggestion_id='c'*32;candidate_id='f'*32
    p['scene_render_intent']={'scene_hash':'a'*64};p['scene_render_review']={'artifact_sha256':'b'*64}
    p['scene_retake_suggestions']={suggestion_id:{'id':suggestion_id,'state':'approved_for_generation',
        'model':'kling-video-v3_0','model_label':'Kling 3.0','approval_mode':'manual','aspect':'16:9',
        'intent':'修正首镜头站位','segments':[{'shot_id':'main','name':'主机位','start':0,'end':5,
        'duration':5,'billable_duration':5,'credits':3,'status':'deviation','note':'站位偏移'},
        {'shot_id':'detail','name':'细节特写','start':5,'end':10,
        'duration':5,'billable_duration':5,'credits':3,'status':'deviation','note':'商品细节待回放'}],
        'credits':3,'quote_digest':'d'*64,'scene_revision':1,'scene_hash':'a'*64,'artifact_sha256':'b'*64,
        'requires_explicit_approval':True,'training_eligible':False,'request_digest':'e'*64}}
    p['revision']=2
    p['edit_retakes']={candidate_id:{'id':candidate_id,'scene_retake_id':suggestion_id,'state':'completed',
        'revision':1,'completed_revision':p['revision'],'asset':'edit_'+candidate_id,'candidate_sha256':'c'*64,
        'qa':{'technical':'passed','semantic':'pending'},'training_eligible':False,
        'clip':{'source':'primary','start':0,'end':5},'duration':5,'created_at':1}}
    store.save(p,1);base='/creative/api/projects/'+p['id']+'/edit'
    body={'revision':p['revision'],'candidate_id':candidate_id,
          'checks':{'product':'aligned','motion':'deviation','audio':'aligned'},'note':'候选在 2.4 秒处动作衔接略跳'}
    initial_context=client.get(base+'?scene_retake='+suggestion_id).json()['scene_retake']
    summary=initial_context['candidate']['candidate_review_summary']
    assert summary['state']=='not_recorded' and summary['segment_count']==2
    assert summary['covered_segment_count']==1 and summary['pending_segment_count']==2
    assert summary['segments'][0]['coverage']=='full' and summary['segments'][1]['coverage']=='uncovered'
    plan=client.post(base+'/scene-retake-batch-plan',json={'revision':p['revision'],'scene_retake_id':suggestion_id})
    assert plan.status_code==200,plan.text
    batch=plan.json()['plan']
    assert batch['state']=='ready_for_review' and batch['total_segment_count']==2
    assert batch['covered_segment_count']==1 and batch['remaining_segment_count']==1
    assert batch['remaining_credits']==3 and batch['review_pending_count']==1
    assert batch['requires_explicit_approval'] is True and batch['can_submit'] is False
    approval_body={'revision':p['revision'],'scene_retake_id':suggestion_id,'shots':[
        {'shot_id':'main','decision':'approved','note':'允许进入单镜头候选流程'},
        {'shot_id':'detail','decision':'blocked','note':'先补商品细节核对'}]}
    approval_response=client.post(base+'/scene-retake-batch-approval',json=approval_body)
    assert approval_response.status_code==200,approval_response.text
    approval=approval_response.json()['approval']
    assert approval['training_eligible'] is False and len(approval['shots'])==2
    batch=approval_response.json()['plan']
    assert batch['approval_recorded'] is True and batch['approved_segment_count']==1
    assert batch['blocked_segment_count']==1 and batch['segments'][1]['approval']=='blocked'
    replay=client.post(base+'/scene-retake-batch-approval',json=approval_body)
    assert replay.status_code==200 and replay.json()['approval']['receipt_sha256']==approval['receipt_sha256']
    assert client.post(base+'/scene-retake-batch-approval',json={**approval_body,'shots':approval_body['shots'][:1]}).status_code==422
    saved=client.post(base+'/scene-retake-review',json=body);assert saved.status_code==200,saved.text
    review=saved.json()['review'];assert review['training_eligible'] is False
    assert review['candidate_sha256']=='c'*64 and review['checks']['motion']=='deviation'
    context=client.get(base+'?scene_retake='+suggestion_id).json()['scene_retake']
    assert context['candidate']['candidate_review']['receipt_sha256']==review['receipt_sha256']
    summary=context['candidate']['candidate_review_summary']
    assert summary['state']=='recorded' and summary['recorded_segment_count']==1
    assert summary['pending_segment_count']==1 and summary['checks_recorded']==['product','motion','audio']
    assert summary['requires_full_replay'] is True and summary['requires_audio_check'] is True
    batch=client.post(base+'/scene-retake-batch-plan',json={'revision':p['revision'],'scene_retake_id':suggestion_id}).json()['plan']
    assert batch['covered_segment_count']==1 and batch['remaining_segment_count']==1
    assert batch['review_pending_count']==0 and batch['candidate']['candidate_review_summary']['state']=='recorded'
    assert batch['approved_segment_count']==1 and batch['blocked_segment_count']==1
    receipt=client.post(base+'/scene-retake-batch-receipt',json={'revision':p['revision'],'scene_retake_id':suggestion_id})
    assert receipt.status_code==200,receipt.text
    receipt=receipt.json()['receipt']
    assert receipt['overall']=='partial_success' and receipt['can_apply'] is False
    assert [row['status'] for row in receipt['segments']]==['succeeded','blocked']
    assert receipt['requires_manual_reconciliation'] is False and receipt['training_eligible'] is False
    replay=client.post(base+'/scene-retake-review',json=body);assert replay.status_code==200
    assert replay.json()['review']['receipt_sha256']==review['receipt_sha256']
    stale=dict(body,revision=p['revision']+1)
    assert client.post(base+'/scene-retake-review',json=stale).status_code==409


def test_scene_batch_receipt_exposes_failed_and_unknown_without_retry(client,monkeypatch):
    p=source_project(client,monkeypatch);suggestion_id='d'*32
    p['scene_render_intent']={'scene_hash':'a'*64};p['scene_render_review']={'artifact_sha256':'b'*64}
    p['scene_retake_suggestions']={suggestion_id:{'id':suggestion_id,'state':'approved_for_generation',
        'scene_hash':'a'*64,'artifact_sha256':'b'*64,'segments':[
            {'shot_id':'main','name':'主机位','start':0,'end':5,'duration':5,'credits':3},
            {'shot_id':'detail','name':'细节特写','start':5,'end':10,'duration':5,'credits':3}]}}
    p['scene_retake_batch_approvals']={suggestion_id:{'scene_retake_id':suggestion_id,'revision':p['revision'],
        'scene_hash':'a'*64,'artifact_sha256':'b'*64,'shots':[
            {'shot_id':'main','decision':'approved','note':''},
            {'shot_id':'detail','decision':'approved','note':''}],
        'receipt_sha256':'c'*64,'training_eligible':False}}
    p['edit_retakes']={'e'*32:{'id':'e'*32,'scene_retake_id':suggestion_id,'state':'failed',
        'clip':{'source':'primary','start':0,'end':5},'created_at':1},
        'f'*32:{'id':'f'*32,'scene_retake_id':suggestion_id,'state':'needs_review',
        'clip':{'source':'primary','start':5,'end':10},'created_at':2}}
    store.save(p,1);base='/creative/api/projects/'+p['id']+'/edit'
    receipt=client.post(base+'/scene-retake-batch-receipt',json={'revision':p['revision'],'scene_retake_id':suggestion_id})
    assert receipt.status_code==200,receipt.text
    receipt=receipt.json()['receipt']
    assert receipt['overall']=='pending'
    assert [row['status'] for row in receipt['segments']]==['failed','unknown']
    assert receipt['requires_manual_reconciliation'] is True
    assert receipt['segments'][0]['candidate_id']=='e'*32 and receipt['segments'][1]['candidate_state']=='needs_review'
    assert client.post(base+'/scene-retake-batch-receipt',json={'revision':p['revision']+1,'scene_retake_id':suggestion_id}).status_code==409


def test_scene_batch_apply_draft_only_includes_fully_reviewed_candidates(client,monkeypatch):
    p=source_project(client,monkeypatch);suggestion_id='d'*32;candidate_id='e'*32
    p['scene_render_intent']={'scene_hash':'a'*64};p['scene_render_review']={'artifact_sha256':'b'*64}
    primary_sha=media.digest(store.DATA/'artifacts'/'existing'/'film.mp4')
    p['edit']={'sources':{'primary':primary_sha},'source_sha256':primary_sha,
               'clips':[{'source':'primary','start':0,'end':5}], 'captions':[], 'audio':[]}
    candidate_dir=store.DATA/'edit-assets'/p['id']/candidate_id;candidate_dir.mkdir(parents=True)
    (candidate_dir/'source.mp4').write_bytes(b'candidate')
    p['edit_assets']={candidate_id:{'label':'重拍候选','filename':'source.mp4','sha256':media.digest(candidate_dir/'source.mp4')}}
    p['scene_retake_suggestions']={suggestion_id:{'id':suggestion_id,'state':'approved_for_generation',
        'scene_hash':'a'*64,'artifact_sha256':'b'*64,'segments':[{'shot_id':'main','name':'主机位',
        'start':0,'end':5,'duration':5,'credits':3}]}}
    p['scene_retake_batch_approvals']={suggestion_id:{'scene_retake_id':suggestion_id,'revision':p['revision'],
        'scene_hash':'a'*64,'artifact_sha256':'b'*64,'shots':[{'shot_id':'main','decision':'approved','note':''}],
        'receipt_sha256':'c'*64,'training_eligible':False}}
    p['edit_retakes']={candidate_id:{'id':candidate_id,'scene_retake_id':suggestion_id,'state':'completed',
        'completed_revision':p['revision'],'asset':'edit_'+candidate_id,'candidate_sha256':'f'*64,
        'clip':{'source':'primary','start':0,'end':5},'created_at':1,
        'candidate_review':{'checks':{'product':'aligned','motion':'aligned','audio':'aligned'},'training_eligible':False}}}
    store.save(p,1);base='/creative/api/projects/'+p['id']+'/edit'
    response=client.post(base+'/scene-retake-batch-apply-draft',json={'revision':p['revision'],'scene_retake_id':suggestion_id})
    assert response.status_code==200,response.text
    draft=response.json()['draft']
    assert draft['state']=='ready' and draft['ready_count']==1 and draft['can_apply'] is False
    assert draft['reversible'] is True and draft['candidate_ids']==[candidate_id]
    assert draft['rows'][0]['eligibility']=='ready' and draft['rows'][0]['target_clip_index']==0
    assert store.load(p['id'],1)['edit']==p['edit']
    check_body={'revision':p['revision'],'scene_retake_id':suggestion_id,
                'base_document_sha256':draft['base_document_sha256'],'candidate_ids':[candidate_id]}
    check=client.post(base+'/scene-retake-batch-apply-check',json=check_body)
    assert check.status_code==200 and check.json()['check']['safe_to_apply'] is True
    applied=client.post(base+'/scene-retake-batch-apply',json={**check_body,'confirm':'apply'})
    assert applied.status_code==200,applied.text
    applied_body=applied.json();assert applied_body['application']['state']=='applied'
    assert applied_body['spec']['clips'][0]['source']=='edit_'+candidate_id
    assert applied_body['application']['reversible'] is True
    reloaded=client.get(base).json()
    assert reloaded['batch_applications'][-1]['id']==applied_body['application']['id']
    assert reloaded['batch_applications'][-1]['state']=='applied'
    diff=reloaded['batch_applications'][-1]['timeline_diff']
    assert diff[0]['index']==0 and diff[0]['before']['source']=='primary'
    assert diff[0]['after']['source']=='edit_'+candidate_id
    track_diff=reloaded['batch_applications'][-1]['track_diff']
    assert track_diff['captions']['changed'] is False and track_diff['audio']['changed'] is False
    assert 'before_spec' not in json.dumps(reloaded)
    undone=client.post(base+'/scene-retake-batch-undo',json={
        'revision':applied_body['revision'],'application_id':applied_body['application']['id']})
    assert undone.status_code==200,undone.text
    assert undone.json()['application']['state']=='undone'
    assert undone.json()['spec']['clips'][0]['source']=='primary'
    current=store.load(p['id'],1);current['edit']['clips'][0]['end']=4;store.save(current,1)
    conflict=client.post(base+'/scene-retake-batch-apply-check',json={**check_body,'revision':current['revision']})
    assert conflict.status_code==200 and conflict.json()['check']['safe_to_apply'] is False
    assert 'document_changed' in conflict.json()['check']['conflicts'] and conflict.json()['check']['can_apply'] is False
    assert client.post(base+'/scene-retake-batch-apply-draft',json={'revision':p['revision'],'scene_retake_id':suggestion_id}).status_code==409


def test_multisource_binding_audio_clock_and_overlapping_captions():
    catalog={'v':dict(sha256='v1',duration=10,kind='video',has_audio=True),
             'a':dict(sha256='a1',duration=8,kind='audio',has_audio=True)}
    spec=dict(sources={'v':'v1','a':'a1'},clips=[dict(source='v',start=2,end=7)],
              captions=[dict(start=0,end=2,text='字幕',track=0),dict(start=0,end=2,text='标注',track=1)],
              audio=[dict(source='a',start=2,end=4,at=1,gain=.2,fade_in=.4,fade_out=.5)])
    clean=validate_edit(spec,catalog=catalog)
    assert clean['duration']==5 and clean['audio'][0]['at']==1
    for bad in [dict(spec,sources={'v':'v1','a':'old'}),
                dict(spec,audio=[dict(source='a',start=2,end=4,at=4)]),
                dict(spec,audio=[dict(source='a',start=2,end=4,at=1,fade_in=3)]),
                dict(spec,captions=[dict(start=0,end=2,text='a'),dict(start=1,end=3,text='b')]),
                dict(spec,clips=[dict(source='a',start=0,end=1)]),
                dict(spec,clips=[dict(source='foreign',start=0,end=1)])]:
        with pytest.raises(ValueError): validate_edit(bad,catalog=catalog)


def test_editor_empty_project_and_ownership_of_extra_sources(client,monkeypatch):
    p=ready(client);base='/creative/api/projects/'+p['id']+'/edit'
    assert client.get(base).json()['spec']['clips']==[]
    aid='a'*32;directory=store.DATA/'edit-assets'/p['id']/aid;directory.mkdir(parents=True)
    (directory/'source.mp4').write_bytes(b'owned')
    p['edit_assets']={aid:{'filename':'source.mp4','label':'Owned clip'}};store.save(p,1)
    monkeypatch.setattr(media,'describe',lambda path:dict(sha256=digest(path),duration=3,kind='video',has_audio=False,width=320,height=240))
    assert client.get(base+'/sources/edit_'+aid).content==b'owned'
    assert client.get(base+'/sources/edit_'+aid,headers={'Authorization':'Bearer two'}).status_code==404
    other=ready(client)
    assert client.get('/creative/api/projects/'+other['id']+'/edit/sources/edit_'+aid).status_code==404
    spec=client.get(base).json()['spec']
    saved=client.put(base,json={'revision':p['revision'],'spec':spec})
    assert saved.status_code==200
    (directory/'source.mp4').write_bytes(b'changed')
    assert client.post(base+'/export',json={'revision':saved.json()['revision']}).status_code==422
    doc=client.get(base).json()
    assert doc['warning'] and doc['spec']['sources']==spec['sources']
    assert not store.RUNNING


def test_upload_is_immutable_and_revision_guarded(client,monkeypatch):
    p=ready(client);base='/creative/api/projects/'+p['id']+'/edit'
    calls=[]
    def upload(project,raw,kind,label):
        calls.append((raw,kind));return dict(id='a'*32,filename='source.mp4',label=label,kind=kind,sha256='hash')
    monkeypatch.setattr(edit_api,'save_upload',upload)
    query='?revision='+str(p['revision'])+'&kind=video&label=Clip'
    assert client.post(base+'/assets'+query,content=b'video').status_code==200
    assert client.post(base+'/assets'+query,content=b'video').status_code==409
    assert len(calls)==1 and len(store.load(p['id'],1)['edit_assets'])==1
    assert client.app.state.test_account_limits['used']==0
    assert client.post(base+'/assets'+query,content=b'video',headers={'Authorization':'Bearer two'}).status_code==404


def test_upload_digest_recovers_response_without_duplicate(client,monkeypatch):
    import hashlib
    p=ready(client);base='/creative/api/projects/'+p['id']+'/edit';calls=[]
    def upload(project,raw,kind,label):
        calls.append(raw);return dict(id='b'*32,filename='source.mp4',label=label,kind=kind,sha256='normalized')
    monkeypatch.setattr(edit_api,'save_upload',upload)
    digest=hashlib.sha256(b'video').hexdigest();query='?revision=1&kind=video&label=Clip'
    first=client.post(base+'/assets'+query,content=b'video',headers={'X-Upload-Digest':digest})
    assert first.status_code==200
    # A lost response leaves the browser on the old revision; the exact same
    # request must recover the saved asset instead of failing the revision guard.
    replay=client.post(base+'/assets'+query,content=b'video',headers={'X-Upload-Digest':digest})
    assert replay.status_code==200 and replay.json()['revision']==first.json()['revision']
    recovered=client.get(base+'/assets/lookup',params={'upload_digest':digest})
    assert recovered.status_code==200 and recovered.json()['source']['id']=='edit_'+'b'*32
    assert len(calls)==1


def test_full_film_review_is_explicit_and_does_not_grant_training(client,monkeypatch):
    p=source_project(client,monkeypatch);base='/creative/api/projects/'+p['id']+'/edit'
    doc=client.get(base).json();saved=client.put(base,json={'revision':p['revision'],'spec':doc['spec']})
    assert saved.status_code==200
    review=client.get(base+'/review').json()
    assert review['packet']['technical']['source_integrity']['status']=='passed'
    assert review['packet']['content']['audio_semantics']['status']=='pending'
    tasks={task['id']:task for task in review['packet']['content_tasks']}
    assert set(tasks)=={'product_fidelity','claim_accuracy','motion_continuity','audio_semantics'}
    assert tasks['audio_semantics']['windows'][0]['start']==0
    assert tasks['audio_semantics']['windows'][0]['end']==pytest.approx(15,abs=.01)
    payload={'revision':saved.json()['revision'],'decision':'approved','checks':{'full_video_watched':False,'audio_listened':False,'product_facts_checked':False}}
    assert client.post(base+'/review',json=payload).status_code==422
    payload['decision']='needs_changes';record=client.post(base+'/review',json=payload)
    assert record.status_code==200 and record.json()['saved']['training_eligible'] is False
    payload.update(decision='approved',checks={'full_video_watched':True,'audio_listened':True,'product_facts_checked':True})
    record=client.post(base+'/review',json=payload)
    assert record.status_code==200 and record.json()['saved']['decision']=='approved'
    assert client.get(base).json()['review']['saved']['semantic']=='pending'


def test_real_audio_import_waveform_and_invalid_media(tmp_path,monkeypatch):
    import io, math, struct, wave
    from pathlib import Path
    if not Path(media.FFMPEG).is_file() or not Path(media.FFPROBE).is_file(): pytest.skip('Local media tools unavailable')
    monkeypatch.setattr(store,'DATA',tmp_path)
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(i*2*math.pi*440/8000))) for i in range(4000)))
    p={'id':'owned','edit_assets':{}}
    a=media.save_upload(p,buf.getvalue(),'audio','tone.wav');p['edit_assets'][a['id']]=a
    result=media.waveform(p,'edit_'+a['id'])
    assert result['has_audio'] and len(result['peaks'])>10 and max(result['peaks'])>.1
    assert media.waveform(p,'edit_'+a['id'])==result
    with pytest.raises(ValueError): media.save_upload(p,b'not media','video','bad')
    assert len(list((tmp_path/'edit-assets/owned').iterdir()))==1
    assert (tmp_path/'edit-assets/owned'/a['id']/'upload.bin').read_bytes()==buf.getvalue()
