"""Bounded controlled-slot question action. No natural-language oracle inference."""
from harness.tools.research_plan import bounded_text


def ask_research_fact(oracle, action):
    if not isinstance(action,dict):raise ValueError('invalid_question_action')
    fact_id=bounded_text(action.get('fact_id'),100)
    question=bounded_text(action.get('text'),500)
    answer=oracle.ask(fact_id)  # Repeated and unknown slots spend the same budget.
    return {'action':'ask_fact','question':{'fact_id':fact_id,'text':question},
            'observation':answer,'questions_used':oracle.used,
            'answer_protocol':'deterministic_fact_slot_not_natural_language_matching',
            'question_slot_semantic_match':'not_evaluated','training_eligible':False}


def apply_answer(visible, observation):
    from copy import deepcopy
    result=deepcopy(visible)
    answer=observation['observation']
    if answer['state']=='provided':result['facts'][answer['fact_id']]=answer['answer']
    return result
