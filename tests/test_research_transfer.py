import json
import pytest
from harness.research.transfer import review_messages, plan_messages, validate_transfer_plan


def test_equal_reference_and_facts_and_no_hidden_condition_in_final_prompt():
    visible={'facts':{'safe':'yes'}};ref={'evidence':{'events':[]},'interpretation':{'principle':'hypothesis'}}
    prompts=[review_messages(visible,ref,c) for c in ('general_review','prerequisite_review')]
    a,b=[json.loads(p[1]['content']) for p in prompts]
    assert prompts[0][0]==prompts[1][0]
    assert a['task']==b['task']==visible and a['reference']==b['reference']==ref
    assert a['instruction']!=b['instruction']
    assert 'condition' not in json.loads(plan_messages(visible,ref,{})[1]['content'])


def test_continuous_timeline_allows_four_shots_but_rejects_gap_overlap_and_nonfinite():
    raw={'claim':'claim','shots':[{'start':s,'end':e,'visual':'v','audio':'a','caption':'c'}
         for s,e in [(0,4),(4,8),(8,12),(12,15)]],'fact_basis':['safe'],'unresolved':[]}
    assert len(validate_transfer_plan(raw,['safe'])['shots'])==4
    for value in (3,5,float('nan'),float('inf'),True):
        raw['shots'][1]['start']=value
        with pytest.raises(ValueError,match='invalid_plan_timing'):validate_transfer_plan(raw,['safe'])


def test_runner_stops_failed_branch_and_never_reuses_output(tmp_path, monkeypatch):
    import asyncio
    from pathlib import Path
    from types import SimpleNamespace
    from tools import run_paper_transfer as runner
    refs=tmp_path/'references.json'
    refs.write_text(json.dumps({'references':[{'reference_id':'R008','evidence':{},'interpretation':{}}]}))
    args=SimpleNamespace(briefs=Path('data/research/advertising_briefs_v1.json'),
        card_id='fede6b1cfac7',references=refs,reference_id='R008',execute=True,
        out=tmp_path/'run',model='mock',max_tokens=4400)
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE','unused')
    monkeypatch.setenv('CREATIVE_MODEL_URL','unused')
    calls=[]
    async def fake(messages,model,stage,fact_ids,max_tokens):
        calls.append(stage)
        if len(calls)==1:raise ValueError('invalid_review')
        return {'result':{'stub':True},'usage':{},'semantic_review':'pending','training_eligible':False}
    monkeypatch.setattr(runner,'transfer_step',fake)
    asyncio.run(runner.run(args))
    assert calls==['review','review','plan']
    summary=json.loads((args.out/'summary.json').read_text())
    assert summary['calls']==3 and summary['failed_stages']==1 and summary['completed_plans']==1
    with pytest.raises(FileExistsError):asyncio.run(runner.run(args))
    assert len(calls)==3


def test_failure_diagnostics_exclude_model_text():
    from harness.tools.research_transfer import TransferValidationError
    from harness.models.research_planner import IncompletePlanningError
    error=TransferValidationError('invalid_plan_text',{'shots':[{'visual':'PRIVATE','audio':'a','caption':''}]},{'total_tokens':5})
    assert error.diagnostics['shot_text_lengths']==[{'visual':7,'audio':1,'caption':0}]
    assert 'PRIVATE' not in json.dumps(error.diagnostics)
    assert error.usage=={'total_tokens':5}
    assert IncompletePlanningError('PRIVATE',{}).diagnostics=={'finish_reason':'other'}


def test_caption_can_be_absent_visually_but_not_missing_from_contract():
    plan={'claim':'claim','shots':[{'start':0,'end':15,'visual':'action','audio':'music','caption':''}],
          'fact_basis':['safe'],'unresolved':[]}
    assert validate_transfer_plan(plan,['safe'])['shots'][0]['caption']==''
    del plan['shots'][0]['caption']
    with pytest.raises(ValueError):validate_transfer_plan(plan,['safe'])


def test_requirement_diagnostics_keep_counts_not_field_values():
    from harness.tools.research_transfer import TransferValidationError
    raw={'record':{'requirements':[{'fact_id':'PRIVATE','status':'supported'},
        {'fact_id':'PRIVATE','status':'BAD'}],'replacement':None}}
    error=TransferValidationError('invalid_requirement',raw,{})
    assert error.diagnostics['original_requirements']=={'count':2,'non_object_count':0,'invalid_status_count':1,'repeated_fact_id_count':1}
    assert 'PRIVATE' not in json.dumps(error.diagnostics) and 'BAD' not in json.dumps(error.diagnostics)
