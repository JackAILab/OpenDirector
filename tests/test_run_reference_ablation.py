import asyncio
import json
from argparse import Namespace
from pathlib import Path
import pytest
from tools import run_reference_ablation as runner


def args(tmp_path, mode='present', execute=False):
    refs=tmp_path/'refs.json'
    refs.write_text(json.dumps({'references':[{'reference_id':'R1',
        'evidence':{'events':[{'event_id':'R1:E1','visual_observation':'synthetic test'}]},
        'interpretation':{},'training_eligible':False}]}))
    briefs=Path('data/research/advertising_goal_dependent_briefs_v2.json')
    card=json.loads(briefs.read_text())['cards'][0]['id']
    return Namespace(briefs=briefs,references=refs,card_id=card,reference_id='R1',
        model='test-only',question_budget=3,max_tokens=4400,seed=17,
        reference_mode=mode,execute=execute,out=tmp_path/mode)


def test_dry_run_only_reference_treatment_changes(tmp_path,monkeypatch):
    async def prohibited(*a,**kw): raise AssertionError('unexpected model call')
    monkeypatch.setattr(runner,'decide_once',prohibited)
    a=args(tmp_path); asyncio.run(runner.run(a))
    b=args(tmp_path,'absent'); asyncio.run(runner.run(b))
    x=json.loads((a.out/'manifest.json').read_text());y=json.loads((b.out/'manifest.json').read_text())
    for key in ['visible_input_sha256','dataset_sha256','assigned_reference_sha256','max_output_tokens','max_calls','conditions']:
        assert x[key]==y[key]
    assert x['max_calls']==6 and x['effective_max_questions_per_condition']==1
    for policy in x['conditions']:
        px=json.loads(x['initial_prompts'][policy][1]['content'])
        py=json.loads(y['initial_prompts'][policy][1]['content'])
        assert px.pop('reference') is not None and py.pop('reference') is None
        assert px==py
        assert 'evaluation_only' not in px['task'] and 'parent_card_id' not in px['task']
    assert y['reference_id'] is None
    assert not list(b.out.glob('*-attempt.json'))
    with pytest.raises(FileExistsError):asyncio.run(runner.run(b))


def test_first_failure_stops_policy_without_retry(tmp_path,monkeypatch):
    a=args(tmp_path,'absent',True)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','test-only-unused')
    monkeypatch.setenv('CREATIVE_MODEL_URL','test-only-unused')
    calls=[]
    async def failing(*args,**kwargs):
        calls.append(args[3]);raise RuntimeError('private upstream detail must not be stored')
    monkeypatch.setattr(runner,'decide_once',failing)
    asyncio.run(runner.run(a))
    s=json.loads((a.out/'summary.json').read_text())
    assert len(calls)==2 and len(set(calls))==2
    assert s['calls']==s['failed_calls']==2
    assert all(not c['plan_completed'] for c in s['conditions'])
    assert not list(a.out.glob('*-plan-attempt.json'))
    assert 'private upstream detail' not in ''.join(p.read_text() for p in a.out.glob('*-event.json'))


def test_fixed_two_slots_finish_then_plan(tmp_path,monkeypatch):
    a=args(tmp_path,'absent',True)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','test-only-unused')
    monkeypatch.setenv('CREATIVE_MODEL_URL','test-only-unused')
    flags=[]
    async def finish(*args,**kwargs):
        flags.append(kwargs['force_finish'])
        return {'result':{'action':'finish','question':None,'recommendation':'test','record':{}},'usage':{}}
    async def plan(*args,**kwargs):return {'result':{'claim':'test'},'usage':{}}
    monkeypatch.setattr(runner,'decide_once',finish);monkeypatch.setattr(runner,'transfer_step',plan)
    asyncio.run(runner.run(a))
    s=json.loads((a.out/'summary.json').read_text())
    assert flags==[False,True,False,True]
    assert s['calls']==6 and s['failed_calls']==0
    assert all(c['plan_completed'] for c in s['conditions'])


def test_observation_projection_reaches_decisions_and_plan(tmp_path, monkeypatch):
    a=args(tmp_path, execute=True)
    a.reference_content='observations'
    data=json.loads(a.references.read_text())
    ref=data['references'][0]
    ref['interpretation']={'transfer_rules':['FORBIDDEN_ADVICE']}
    ref['alternate_advice']='FORBIDDEN_ADVICE'
    ref['evidence']['events'][0]['purpose']='FORBIDDEN_ADVICE'
    a.references.write_text(json.dumps(data))
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','test-only-unused')
    monkeypatch.setenv('CREATIVE_MODEL_URL','test-only-unused')
    seen=[]
    async def finish(visible, reference, *args, **kwargs):
        seen.append(reference)
        return {'result':{'action':'finish','question':None,'recommendation':'test','record':{}},'usage':{}}
    async def plan(messages,*args,**kwargs):
        assert 'FORBIDDEN_ADVICE' not in json.dumps(messages)
        assert 'synthetic test' in json.dumps(messages)
        return {'result':{},'usage':{}}
    monkeypatch.setattr(runner,'decide_once',finish)
    monkeypatch.setattr(runner,'transfer_step',plan)
    asyncio.run(runner.run(a))
    assert len(seen)==4
    assert all('FORBIDDEN_ADVICE' not in json.dumps(r) for r in seen)
    manifest=json.loads((a.out/'manifest.json').read_text())
    assert manifest['reference_content']=='observations'
    assert manifest['reference_sha256']!=manifest['assigned_reference_sha256']
    assert 'FORBIDDEN_ADVICE' not in json.dumps(manifest['initial_prompts'])


def test_projection_preserves_original_and_validates_treatment():
    from harness.research.reference_ablation import project_reference
    source={'reference_id':'R1','evidence':{'events':[{'event_id':'E1','visual_observation':'seen'}]},
            'interpretation':{'transfer_rules':['advice']},'training_eligible':False}
    before=json.dumps(source,sort_keys=True)
    full=project_reference(source,'full')
    assert full==source and full is not source
    assert 'interpretation' not in project_reference(source,'observations')
    assert json.dumps(source,sort_keys=True)==before
    assert project_reference(None,'observations') is None
    with pytest.raises(ValueError):project_reference(source,'unknown')
