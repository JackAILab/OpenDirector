import json
import pytest
from harness.learning.training_records import sanitize_plan,build_record,sanitize_episode
from test_creative_studio import client,ready


def test_sanitized_director_example_is_whitelisted_and_redacted():
    plan={'duration':15,'aspect':'16:9','generation_mode':'single_native',
          'brief':{'message':'展示产品','secret':'discarded','claim':'更快'},
          'shots':[{'start':0,'duration':5,'prompt':'联系 me@example.com https://private.invalid/x','audio_prompt':'旁白','caption':'字幕','provider_payload':'drop'}],
          'questions':[{'question':'谁是受众？','why':'需要确定语气','raw':'drop'}],
          'decisions':[{'decision':'保留真实规格','reason':'用户确认'}],
          'plan_evaluation':{'schema':'visualagent.plan-evaluation.v1','passed':True,'failures':[],'warnings':[]}}
    clean=sanitize_plan(plan);text=json.dumps(clean,ensure_ascii=False)
    assert '[REDACTED_EMAIL]' in text and '[REDACTED_URL]' in text
    assert 'secret' not in text and 'provider_payload' not in text and 'raw' not in text
    assert clean['shots'][0]['audio_prompt']=='旁白'


def test_strategy_context_is_kept_without_source_identity():
    plan={'strategy_candidates':[{'source_item':'award-123','confidence':'high',
        'principle':'让功能结果可见','mechanism':'用户在具体任务中看到前后差异',
        'grill_questions':['哪个事实已核实？','raw@example.com'],
        'transfer_rules':['只借鉴机制，不复制镜头'], 'avoid':['照搬原品牌文案'],
        'evidence_scope':'sampled_frames'}]}
    clean=sanitize_plan(plan);item=clean['strategy_candidates'][0]
    assert 'source_item' not in item and item['principle']=='让功能结果可见'
    assert '[REDACTED_EMAIL]' in item['grill_questions'][1]


def test_strategy_selection_keeps_candidate_index_and_reason():
    clean=sanitize_plan({'strategy_selection':[{'candidate_index':1,'reason':'与续航主张的结果证明一致'},
                                               {'candidate_index':'bad','reason':'丢弃'}]})
    assert clean['strategy_selection']==[{'candidate_index':1,'reason':'与续航主张的结果证明一致'}]


def test_director_decision_title_is_preserved_as_training_decision():
    clean=sanitize_plan({'decisions':[{'title':'先证明真实动作','reason':'用户确认商品可在三秒内完成'}]})
    assert clean['decisions']==[{'decision':'先证明真实动作','reason':'用户确认商品可在三秒内完成'}]


def test_nonfinite_strategy_scores_and_time_windows_are_excluded():
    clean=sanitize_plan({'strategy_candidates':[{'principle':'动作证明',
        'relevance_score':float('nan'),'shooting_grammar':{'windows':[
            {'start':0,'end':float('inf')},{'start':-1,'end':5},
            {'start':0,'end':5,'purpose':'可见动作'}]}}]})
    item=clean['strategy_candidates'][0]
    assert 'relevance_score' not in item
    assert len(item['shooting_grammar']['windows'])==1
    json.dumps(clean,allow_nan=False)


def test_training_record_contains_only_anonymous_binding():
    record=build_record('a'*64,'train','b'*64,{'duration':15,'brief':{'message':'展示产品'},'shots':[]})
    assert record['schema']=='visualagent.training-record-candidate.v1'
    assert record['training_eligible'] is False and record['public_release'] is False
    assert record['plan']['duration']==15
    assert record['provenance']['strategy_context']=='external_reference_strategy_observation'
    assert record['provenance']['trajectory']=='missing_until_runner_observation'


def test_sanitized_trajectory_keeps_ordered_actions_without_identifiers():
    episode={'chain_verified':True,'unrecorded_event_count':0,'revisions':[{
        'revision':3,
        'events':[{'event_seq':991,'stage':'agent','code':'plan_ready','time':123.4},
                  {'event_seq':992,'stage':'tool','code':'submit_requested','project':'private'}],
        'artifacts':[{'artifact_sha256':'f'*64,'qa':{'technical':'passed','audio':True,'duration':15,'path':'/private'}}],
        'missing_evidence':[]}]}
    clean=sanitize_episode(episode,3)
    assert [event['code'] for event in clean['events']]==['plan_ready','submit_requested']
    text=json.dumps(clean,ensure_ascii=False)
    assert 'event_seq' not in text and 'time' not in text and 'private' not in text
    assert clean['artifact_observations'][0]['qa']['duration']==15


def test_candidate_queue_stays_ineligible(tmp_path):
    from harness.learning.training_records import collect_candidates
    key=tmp_path/'key';key.write_bytes(b'x'*32);key.chmod(0o600)
    assert collect_candidates({'records':[]},key)==[]


def test_private_candidate_requires_current_consent_and_intact_snapshot(client):
    import sqlite3
    from harness.studio import store
    from harness.learning import governance
    from harness.learning.episodes import record_plan
    from harness.learning.training_records import prepare_candidate
    p=ready(client);p.update(state='completed',artifact='artifacts/candidate.mp4')
    path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'candidate film')
    store.save(p,1);record_plan(p,1)
    args=(p['id'],1,'a'*64,'train','b'*64)
    with pytest.raises(ValueError,match='consent'):prepare_candidate(*args)
    with pytest.raises(ValueError,match='Owned'):prepare_candidate(p['id'],2,'a'*64,'train','b'*64)
    artifact=governance.current_artifact(p);status=governance.status(p,1,artifact)
    governance.set_consent(p,1,artifact,True,False,status['policy'],status['policy_sha256'])
    candidate=prepare_candidate(*args)
    assert candidate['source_plan_sha256'] and candidate['artifact_sha256']==artifact
    assert candidate['review_status']=='pending_exact_content_review'
    assert not candidate['training_eligible'] and not candidate['public_release']
    with sqlite3.connect(store.DATA/'learning/episodes.sqlite3') as connection:
        connection.execute('UPDATE plans SET data=? WHERE project=?',(json.dumps({'shots':[]}),p['id']))
    with pytest.raises(ValueError,match='integrity'):prepare_candidate(*args)
