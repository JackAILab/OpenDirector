from copy import deepcopy
import json
from pathlib import Path
import pytest
from harness.research.prerequisites import validate_record
from harness.research.briefs import FactOracle,visible_input
from harness.tools.research_question import ask_research_fact,apply_answer


def record():
    return {'relation':'Pressure then proof','target_action':'Brief water splash',
        'source_status':'interpretation','source_event_ids':['R008:E01'],
        'requirements':[{'fact_id':'rain_protection','status':'unknown','condition':'Short splash only','basis':'Not disclosed'}],
        'decision':'ask','question':{'fact_id':'rain_protection','text':'Has short splash protection been verified?'}}


def test_links_required_facts_and_questions_without_certifying_semantics():
    visible={'facts':{}};ref={'evidence':{'events':[{'event_id':'R008:E01'}]}}
    raw=record();result=validate_record(raw,visible,ref)
    assert result['semantic_review']=='pending' and result['training_eligible'] is False
    raw['requirements'][0]['status']='supported'
    with pytest.raises(ValueError,match='undisclosed_fact_status'):validate_record(raw,visible,ref)
    raw=record();raw['decision']='retain';raw['question']=None
    with pytest.raises(ValueError,match='declared_prerequisite_not_satisfied'):validate_record(raw,visible,ref)
    raw=record();raw['question']['fact_id']='price'
    with pytest.raises(ValueError,match='question_not_linked'):validate_record(raw,visible,ref)
    raw=record();raw['source_event_ids']=['fabricated']
    with pytest.raises(ValueError,match='unknown_source_event'):validate_record(raw,visible,ref)


def test_oracle_reveals_only_requested_fact_and_counts_repeated_unknown_slots():
    cards=json.loads(Path('data/research/advertising_briefs_v1.json').read_text())['cards']
    card=next(c for c in cards if c['id']=='fede6b1cfac7')
    visible=visible_input(card,'underspecified');oracle=FactOracle(card,max_questions=3)
    action=record()['question'];response=ask_research_fact(oracle,action)
    updated=apply_answer(visible,response)
    assert 'rain_protection' not in visible['facts']
    assert updated['facts']['rain_protection']==card['facts']['rain_protection']
    assert set(updated)==set(visible) and 'evaluation_only' not in response
    assert ask_research_fact(oracle,action)['questions_used']==2
    missing=ask_research_fact(oracle,{'fact_id':'not_a_slot','text':'Unknown?'})
    assert missing['questions_used']==3 and apply_answer(updated,missing)==updated
    with pytest.raises(ValueError,match='budget exhausted'):ask_research_fact(oracle,action)


def test_replacement_requires_its_own_supported_facts():
    visible={'facts':{'known_features':'Manual touch switch'}}
    ref={'evidence':{'events':[{'event_id':'R008:E01'}]}}
    raw=record();raw['decision']='replace';raw['question']=None
    with pytest.raises(ValueError,match='missing_replacement_record'):validate_record(raw,visible,ref)
    raw['replacement']={'target_action':'Touch then illuminate','requirements':[
        {'fact_id':'known_features','status':'supported','condition':'Manual touch','basis':'Given feature'}]}
    validated=validate_record(raw,visible,ref)
    assert validated['requirements'][0]['status']=='unknown'
    assert validated['replacement']['requirements'][0]['status']=='supported'
    raw['replacement']['requirements'][0]['status']='unknown'
    with pytest.raises(ValueError,match='replacement_prerequisite_not_satisfied'):validate_record(raw,visible,ref)


def test_distinct_requirements_can_cite_the_same_composite_fact():
    visible={'facts':{'known_features':'Manual touch switch and warm light'}}
    ref={'evidence':{'events':[{'event_id':'R008:E01'}]}}
    raw=record();raw['decision']='retain';raw['question']=None
    raw['requirements']=[{'fact_id':'known_features','status':'supported','condition':condition,'basis':'Given'}
        for condition in ('Touch switch','Warm illumination')]
    assert len(validate_record(raw,visible,ref)['requirements'])==2


def test_record_can_carry_explicit_bridge_assumption():
    visible={'facts':{'leak':'inverted 30 seconds'}}
    ref={'evidence':{'events':[{'event_id':'R008:E01'}]}}
    raw=record();raw['bridge_assumptions']=[{'fact_id':'leak','source_condition':'inverted 30s',
      'target_condition':'horizontal in bag','bridge_assumption':'orientation equivalence',
      'basis':'No structural evidence','status':'supported','bridge_status':'reasonable_with_assumption'}]
    out=validate_record(raw,visible,ref)
    assert out['bridge_assumptions'][0]['bridge_status']=='reasonable_with_assumption'
