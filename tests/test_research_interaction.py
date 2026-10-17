import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness.research.briefs import visible_input
from harness.research.interaction import decision_messages,validate_decision


def cards():return json.loads(Path('data/research/advertising_briefs_v1.json').read_text())['cards']


def test_initial_messages_do_not_reveal_counterfactual_oracle_or_variant():
    family=[c for c in cards() if c['family_id']=='light']
    ref={'evidence':{'events':[]}}
    prompts=[decision_messages(visible_input(c,'underspecified'),ref,[],'general_review',3) for c in family]
    assert prompts[0]==prompts[1]==prompts[2]
    payload=json.loads(prompts[0][1]['content'])
    assert 'automatic_presence' not in payload['task']['facts']
    assert set(payload)=={'task','reference','history','remaining_questions','available_fact_slots','instruction'}
    prereq=json.loads(decision_messages(visible_input(family[0],'underspecified'),ref,[],'prerequisite_review',3)[1]['content'])
    assert payload['available_fact_slots']==prereq['available_fact_slots']
    assert payload['task']==prereq['task']


def test_question_requires_matching_record_and_non_question_cannot_hide_question():
    ref={'evidence':{'events':[{'event_id':'R:E01'}]}};visible={'facts':{}}
    q={'fact_id':'automatic_presence','text':'Does it sense presence?'}
    record={'relation':'trigger','target_action':'automatic light','source_status':'interpretation',
        'source_event_ids':['R:E01'],'requirements':[{'fact_id':'automatic_presence','status':'unknown','condition':'presence','basis':'undisclosed'}],
        'decision':'ask','question':q}
    action={'action':'ask_fact','question':q,'recommendation':'check first','record':record}
    assert validate_decision(action,visible,ref,'prerequisite_review')['action']=='ask_fact'
    action['question']={'fact_id':'dimming','text':'Different question'}
    with pytest.raises(ValueError,match='question_record_mismatch'):validate_decision(action,visible,ref,'prerequisite_review')
    with pytest.raises(ValueError,match='unexpected_question'):
        validate_decision({'action':'finish','question':q,'recommendation':'done','record':None},visible,ref,'general_review')


def test_runner_caps_questions_and_calls_and_passes_answers_to_final_plan(tmp_path,monkeypatch):
    from tools import run_paper_interaction as runner
    ref=tmp_path/'refs.json';ref.write_text(json.dumps({'references':[{'reference_id':'R016','evidence':{'events':[]}}]}))
    args=SimpleNamespace(briefs=Path('data/research/advertising_briefs_v1.json'),references=ref,
        card_id='7643e6b62e21',reference_id='R016',out=tmp_path/'out',execute=True,model='mock',max_tokens=4400)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','unused');monkeypatch.setenv('CREATIVE_MODEL_URL','unused')
    called=[];plans=[]
    async def decide(messages,model,visible,reference,condition,max_tokens):
        called.append(condition)
        return {'result':{'action':'ask_fact','question':{'fact_id':'automatic_presence','text':'Presence?'},'recommendation':'review','record':None},'usage':{}}
    async def plan(messages,model,stage,fact_ids,max_tokens):
        plans.append(json.loads(messages[1]['content']))
        return {'result':{'stub':True},'usage':{}}
    monkeypatch.setattr(runner,'decide_once',decide);monkeypatch.setattr(runner,'transfer_step',plan)
    asyncio.run(runner.run(args))
    summary=json.loads((args.out/'summary.json').read_text())
    assert len(called)==6 and len(plans)==2 and summary['calls']==8
    assert all(r['questions_used']==3 for r in summary['conditions'])
    assert all(len(p['review']['question_history'])==3 for p in plans)
    assert all('automatic_presence' in p['task']['facts'] for p in plans)
    with pytest.raises(FileExistsError):asyncio.run(runner.run(args))
    assert len(called)==6


def test_zero_budget_prompt_keeps_hidden_facts_hidden_and_prohibits_ask():
    c=next(c for c in cards() if c['id']=='7643e6b62e21')
    prompt=decision_messages(visible_input(c,'underspecified'),{'evidence':{'events':[]}},[],'general_review',0)
    assert '禁止ask_fact' in prompt[0]['content']
    payload=json.loads(prompt[1]['content'])
    assert payload['remaining_questions']==0 and 'automatic_presence' not in payload['task']['facts']


def test_zero_budget_runner_rejects_attempted_question_without_oracle(tmp_path,monkeypatch):
    from tools import run_paper_interaction as runner
    ref=tmp_path/'refs.json';ref.write_text(json.dumps({'references':[{'reference_id':'R016','evidence':{'events':[]}}]}))
    args=SimpleNamespace(briefs=Path('data/research/advertising_briefs_v1.json'),references=ref,
        card_id='7643e6b62e21',reference_id='R016',out=tmp_path/'out',execute=True,model='mock',max_tokens=4400,question_budget=0)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','unused');monkeypatch.setenv('CREATIVE_MODEL_URL','unused')
    async def decide(*args,**kwargs):return {'result':{'action':'ask_fact','question':{'fact_id':'automatic_presence','text':'ask'}}}
    def oracle(*args,**kwargs):raise AssertionError('Oracle must not be reached')
    monkeypatch.setattr(runner,'decide_once',decide);monkeypatch.setattr(runner,'ask_research_fact',oracle)
    asyncio.run(runner.run(args))
    summary=json.loads((args.out/'summary.json').read_text())
    assert summary['calls']==2 and summary['failed_calls']==2
    assert all(c['questions_used']==0 and not c['plan_completed'] for c in summary['conditions'])


def test_fixed_decision_turns_pad_no_question_baseline_to_equal_call_slots(tmp_path,monkeypatch):
    from tools import run_paper_interaction as runner
    ref=tmp_path/'refs.json';ref.write_text(json.dumps({'references':[{'reference_id':'R016','evidence':{'events':[]}}]}))
    args=SimpleNamespace(briefs=Path('data/research/advertising_briefs_v1.json'),references=ref,
        card_id='7643e6b62e21',reference_id='R016',out=tmp_path/'out',execute=True,model='mock',
        max_tokens=4400,question_budget=0,fixed_decision_turns=2)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','unused');monkeypatch.setenv('CREATIVE_MODEL_URL','unused')
    decisions=[];plans=[]
    async def decide(messages,model,visible,reference,condition,max_tokens):
        decisions.append(json.loads(messages[1]['content']))
        return {'result':{'action':'finish','question':None,'recommendation':'保守方案','record':None},'usage':{}}
    async def plan(messages,model,stage,fact_ids,max_tokens):
        plans.append(json.loads(messages[1]['content']))
        return {'result':{'stub':True},'usage':{}}
    monkeypatch.setattr(runner,'decide_once',decide);monkeypatch.setattr(runner,'transfer_step',plan)
    asyncio.run(runner.run(args))
    summary=json.loads((args.out/'summary.json').read_text())
    assert summary['calls']==6 and summary['failed_calls']==0
    assert len(decisions)==4 and len(plans)==2
    assert all(c['questions_used']==0 and c['plan_completed'] for c in summary['conditions'])
    assert json.loads((args.out/'manifest.json').read_text())['fixed_decision_turns']==2
