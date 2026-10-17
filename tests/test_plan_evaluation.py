from harness.learning.evaluation import evaluate_plan


def plan():
 return {'duration':15,'brief':{'message':'展示真实的快速加热'},'questions':[],'decisions':[{'reason':'基于用户提供的规格'}],
 'shots':[{'start':i*5,'duration':5,'prompt':'original product action '+str(i),'audio_prompt':'original music and kettle sound','caption':'字幕'} for i in range(3)]}


def test_plan_contract_passes_without_aesthetic_claims():
 r=evaluate_plan(plan(),forbidden_terms=('OldBrand','old line'));assert r['passed'] and r['training_eligible'] is False


def test_plan_contract_catches_timing_audio_copy_and_single_claim():
 p=plan();p['brief']['message']='';p['shots'][1]['start']=4;p['shots'][2]['audio_prompt']='';p['shots'][0]['prompt']='OldBrand exact copied sequence';p['questions']=[{}, {}, {}, {}]
 r=evaluate_plan(p,forbidden_terms=('OldBrand',));assert not r['passed'];assert 'single_claim_missing' in r['failures'];assert 'shot_2_clock_invalid' in r['failures'];assert 'shot_3_audio_prompt_missing' in r['failures'];assert 'too_many_questions' in r['failures'];assert any(x.startswith('copied_term') for x in r['failures'])


def test_strategy_selection_is_observed_without_becoming_aesthetic_score():
    p=plan();p['strategy_candidates']=[{'principle':'证明'}]
    missing=evaluate_plan(p);assert missing['passed'] and 'strategy_selection_missing' in missing['warnings'];assert not missing['checks']['strategy_selection']
    p['strategy_selection']=[{'candidate_index':0,'reason':'把功能结果变成可见动作'}]
    selected=evaluate_plan(p);assert selected['checks']['strategy_selection']
    p['strategy_selection']=[{'candidate_index':3,'reason':'越界'}]
    invalid=evaluate_plan(p);assert not invalid['passed'] and 'strategy_selection_invalid' in invalid['failures']
