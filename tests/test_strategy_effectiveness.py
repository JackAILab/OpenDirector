from harness.learning.strategy_effectiveness import summarize


def candidate(index, score, selected):
    return {'quality_mean_score':score,'plan':{
        'strategy_candidates':[{'principle':'把功能结果变成可见动作','mechanism_tags':['observable_task']}, {'principle':'用反转解释价值','mechanism_tags':['contrast_reversal']}],
        'strategy_selection':[{'candidate_index':selected,'reason':'改变中段动作'}]}}


def test_strategy_effectiveness_aggregates_adoption_and_quality_without_text():
    result=summarize([candidate(0,4.8,0),candidate(0,4.2,0),candidate(0,3.8,1)])
    assert result['observed_records']==3 and result['training_eligible'] is False
    first=result['strategies'][0]
    assert first['recommendations']==3 and first['adoptions']==2 and first['adopted_quality_mean']==4.5
    assert 'principle' not in first and first['selection_reason_count']==2
    assert result['mechanisms'][0]['adoptions']==2


def test_owner_feedback_is_descriptive_and_does_not_become_quality():
    record = candidate(0, 4.5, 0)
    record['trajectory'] = {'owner_feedback': [
        {'decision': 'keep', 'rating': 5},
        {'decision': 'revise', 'rating': 3},
    ]}
    result = summarize([record])
    assert result['owner_feedback'] == {
        'count': 2, 'decisions': {'keep': 1, 'revise': 1}, 'rating_mean': 4.0
    }
    assert result['training_eligible'] is False


def test_missing_or_out_of_range_quality_cannot_support_strategy_comparison():
    valid=candidate(0,4,0)
    valid['plan']['strategy_candidates'][0]['mechanism_tags']=['observable_task','observable_task']
    result=summarize([valid,candidate(0,None,0),candidate(0,100,0)])
    assert result['observed_records']==1
    assert result['records_missing_valid_quality']==2
    assert result['comparison_ready'] is False
    assert max(item['recommendations'] for item in result['mechanisms'])==1
