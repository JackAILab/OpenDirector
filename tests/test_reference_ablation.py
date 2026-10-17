import json
import pytest
from harness.research.reference_ablation import decision_messages, validate_decision, POLICIES
from harness.research.prerequisites import validate_record

VISIBLE={'facts':{'switch':'manual touch'}}
REF={'evidence':{'events':[{'event_id':'R1:E1'}]}}


def output():
    return {'action':'finish','question':None,'recommendation':'Show manual touch',
            'record':{'relation':'self-authored touch then light','target_action':'touch switch',
                      'source_status':'no_source','source_event_ids':[],
                      'requirements':[{'fact_id':'switch','status':'supported',
                                       'condition':'manual touch','basis':'disclosed'}],
                      'decision':'retain','question':None,'replacement':None}}


@pytest.mark.parametrize('policy',POLICIES)
def test_absent_reference_is_valid_for_both_policies(policy):
    r=validate_decision(output(),VISIBLE,None,policy,0)
    assert r['record']['source_event_ids']==[]
    assert r['record']['training_eligible'] is False


def test_same_schema_and_inputs_only_instruction_differs():
    a,b=[decision_messages(VISIBLE,None,[],p,3) for p in POLICIES]
    assert a[0]==b[0]
    x,y=[json.loads(m[1]['content']) for m in [a,b]]
    assert x.pop('instruction')!=y.pop('instruction')
    assert x==y


def test_absent_reference_cannot_fabricate_citation_or_source_status():
    r=output();r['record']['source_event_ids']=['invented']
    with pytest.raises(ValueError,match='invalid_absent_reference'):
        validate_decision(r,VISIBLE,None,POLICIES[0],0)
    r=output();r['record']['source_status']='observed_relation'
    with pytest.raises(ValueError,match='invalid_source_status'):
        validate_decision(r,VISIBLE,None,POLICIES[0],0)


def test_present_reference_requires_real_citation_and_legacy_stays_strict():
    r=output();r['record']['source_status']='interpretation'
    with pytest.raises(ValueError,match='unknown_source_event'):
        validate_record(r['record'],VISIBLE,{'evidence':{'events':[]}})
    with pytest.raises(ValueError,match='unknown_source_event'):
        validate_decision(r,VISIBLE,REF,POLICIES[0],0)
    r['record']['source_event_ids']=['R1:E1']
    assert validate_decision(r,VISIBLE,REF,POLICIES[0],0)['record']['source_event_ids']==['R1:E1']


@pytest.mark.parametrize('remaining,forced',[(0,False),(3,True)])
def test_ask_is_rejected_at_budget_boundary(remaining,forced):
    r=output();r['action']='ask_fact'
    with pytest.raises(ValueError,match='question_budget_exceeded'):
        validate_decision(r,VISIBLE,None,POLICIES[1],remaining,forced)


def test_absent_reference_does_not_relax_target_fact_validation():
    r=output();r['record']['requirements'][0]['fact_id']='unknown_feature'
    with pytest.raises(ValueError,match='undisclosed_fact_status'):
        validate_decision(r,VISIBLE,None,POLICIES[0],0)


def test_v2_bridge_contract_is_explicit_and_example_validates():
    from harness.research.reference_ablation import VERSION
    from harness.research.bridge_assumptions import validate_assumptions
    example={'source_condition':'source depicts a response','target_condition':'manual operation',
             'bridge_assumption':'No automatic feature is inferred','basis':'visible switch fact',
             'fact_id':'switch','status':'supported','bridge_status':'not_needed'}
    prompt=decision_messages(VISIBLE,None,[],POLICIES[0],0)[0]['content']
    assert VERSION=='reference-ablation-v2'
    assert all(key in prompt for key in example)
    assert '省略或设为null' in prompt
    assert validate_assumptions([example],VISIBLE)[0]==example
