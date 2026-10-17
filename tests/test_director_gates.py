from harness.learning.director_gates import evaluate_director_gates
from harness.learning.evaluation import evaluate_plan


def test_director_gates_report_evidence_without_training_approval():
    plan = {
        'brief': {'message': '让产品帮助用户完成任务', 'product': '真实商品'},
        'assumptions': [],
        'strategy_selection': [{'candidate_index': 0}],
        'shots': [
            {'prompt': 'Show the product action and reveal the result for the user.',
             'audio_prompt': 'Original music, room sound and voice over.', 'rationale': 'brand product result'},
        ],
    }
    result = evaluate_director_gates(plan)
    assert result['schema'] == 'visualagent.director-stage-gates.v1'
    assert result['passed_stage_count'] == 5
    assert result['stages'][-1]['evidence'] is False
    assert result['training_eligible'] is False


def test_plan_evaluation_exposes_stage_gates():
    result = evaluate_plan({'duration': 15, 'shots': [], 'brief': {}, 'questions': []})
    assert result['stage_gates']['schema'] == 'visualagent.director-stage-gates.v1'
    assert result['training_eligible'] is False
