import asyncio
import json
import pytest
from harness.research.reference_ablation import validate_decision
from harness.tools.research_plan import BoundedTextError,bounded_text
from harness.tools.research_transfer import TransferValidationError
from harness.tools import research_ablation


def output():
    return {'action':'finish','question':None,'recommendation':'manual operation',
        'record':{'relation':'source relation','target_action':'touch switch','source_status':'no_source',
        'source_event_ids':[],'requirements':[{'fact_id':'switch','status':'supported','condition':'touch','basis':'disclosed'}],
        'decision':'retain','question':None,'replacement':None}}


@pytest.mark.parametrize('value,reason,length',[(None,'not_string',None),(123,'not_string',None),('  ','blank',2),('secret'*100,'over_limit',600)])
def test_text_diagnostic_does_not_capture_value(value,reason,length):
    with pytest.raises(BoundedTextError) as caught:bounded_text(value,100,field='record.relation')
    e=caught.value
    assert str(e)=='invalid_plan_text'
    assert e.text_diagnostic=={'field':'record.relation','reason':reason,'length':length,'limit':100}
    assert 'secret' not in json.dumps(vars(e))


def test_nested_requirement_location_propagates_through_tool(monkeypatch):
    raw=output();raw['record']['requirements'][0]['basis']='SENSITIVE'*100
    calls=[]
    async def complete(self,messages):calls.append(1);return raw,{'total_tokens':5}
    monkeypatch.setattr(research_ablation.ResearchPlanner,'complete',complete)
    with pytest.raises(TransferValidationError) as caught:
        asyncio.run(research_ablation.decide_once({'facts':{'switch':'manual'}},None,[],
                    'general_review',0,'test-model',4400))
    e=caught.value
    assert len(calls)==1 and str(e)=='invalid_plan_text'
    assert e.diagnostics['text_failure']=={'field':'record.requirements[0].basis','reason':'over_limit','length':900,'limit':600}
    assert 'SENSITIVE' not in json.dumps(e.diagnostics)
    assert e.usage=={'total_tokens':5}


def test_bridge_and_replacement_locations():
    r=output();r['record']['bridge_assumptions']=[{'source_condition':'', 'target_condition':'test'}]
    with pytest.raises(BoundedTextError) as caught:
        validate_decision(r,{'facts':{'switch':'manual'}},None,'general_review',0)
    assert caught.value.text_diagnostic['field']=='record.bridge_assumptions[0].source_condition'
    r=output();r['record']['decision']='replace';r['record']['replacement']={'target_action':None}
    with pytest.raises(BoundedTextError) as caught:
        validate_decision(r,{'facts':{'switch':'manual'}},None,'general_review',0)
    assert caught.value.text_diagnostic['field']=='record.replacement.target_action'


def test_valid_text_and_legacy_error_code_unchanged():
    assert bounded_text('ok',2)=='ok'
    with pytest.raises(ValueError,match='^invalid_plan_text$'):bounded_text('',2)
    e=TransferValidationError('unknown_source_event',{}, {})
    assert 'text_failure' not in e.diagnostics
