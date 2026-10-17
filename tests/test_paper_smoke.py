import copy
import json
from pathlib import Path
import pytest
from harness.research.briefs import visible_input
from harness.research.planning import messages
from harness.tools.research_plan import validate_plan


def test_prompt_excludes_evaluation_metadata_and_hidden_facts():
    card=json.loads((Path(__file__).resolve().parents[1]/'data/research/advertising_briefs_v1.json').read_text())['cards'][0]
    for condition in ('direct','explicit_fact_check'):
        text=json.dumps(messages(visible_input(card,'underspecified'),condition),ensure_ascii=False)
        assert card['id'] not in text and 'evaluation_only' not in text
        assert card['facts'][card['hidden_fact_ids'][0]] not in text
        assert card['evaluation_only']['safe_alternative'] not in text


def test_validation_checks_timing_and_fact_references_not_semantic_truth():
    plan={'claim':'展示便捷取物','shots':[{'start':i*5,'end':(i+1)*5,'visual':'取出钥匙','audio':'音乐','caption':'随手取出'} for i in range(3)],'fact_basis':['known_features'],'unresolved':[], 'provider_extra':'discard'}
    clean=validate_plan(plan,['known_features']);assert 'provider_extra' not in clean
    bad=copy.deepcopy(plan);bad['fact_basis']=['hidden_fact']
    with pytest.raises(ValueError,match='fact_reference'):validate_plan(bad,['known_features'])
    bad=copy.deepcopy(plan);bad['shots'][1]['start']=4
    with pytest.raises(ValueError,match='timing'):validate_plan(bad,['known_features'])


def test_shape_error_keeps_only_safe_structure_diagnostics():
    from harness.tools.research_plan import PlanShapeError
    with pytest.raises(PlanShapeError) as caught:
        validate_plan({'plan':{'shots':[]},'provider_payload':'sensitive'}, [])
    assert caught.value.diagnostics == {'top_level_object':True,'shots_is_list':False,'shot_count':None,'has_plan_wrapper':True}
    assert 'sensitive' not in str(caught.value.diagnostics)
