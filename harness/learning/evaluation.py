"""Deterministic evaluator for director plans; it is not a quality approval."""
import re


def evaluate_plan(plan, *, forbidden_terms=()):
    failures=[];warnings=[];shots=plan.get('shots') or [];duration=plan.get('duration')
    if duration!=15:failures.append('duration_not_15_seconds')
    if len(shots)!=3:failures.append('requires_three_five_second_beats')
    expected=[(0,5),(5,5),(10,5)]
    for i,shot in enumerate(shots):
        if not isinstance(shot,dict):failures.append(f'shot_{i+1}_not_object');continue
        if i >= len(expected) or (shot.get('start'),shot.get('duration')) != expected[i]:
            failures.append(f'shot_{i+1}_clock_invalid')
        if not str(shot.get('prompt','')).strip():failures.append(f'shot_{i+1}_visual_prompt_missing')
        if not str(shot.get('audio_prompt','')).strip():failures.append(f'shot_{i+1}_audio_prompt_missing')
        if not str(shot.get('caption','')).strip():warnings.append(f'shot_{i+1}_caption_missing')
        text=(str(shot.get('prompt',''))+' '+str(shot.get('audio_prompt',''))).lower()
        for term in forbidden_terms:
            if term and term.lower() in text:failures.append(f'copied_term_in_shot_{i+1}')
    brief=plan.get('brief') or {}
    if not str(brief.get('message','')).strip():failures.append('single_claim_missing')
    if len(plan.get('questions') or [])>3:failures.append('too_many_questions')
    for decision in plan.get('decisions') or []:
        if not str(decision.get('reason','')).strip():failures.append('decision_reason_missing')
    candidates=plan.get('strategy_candidates') or []
    selection=plan.get('strategy_selection') or []
    strategy_selection_valid=True
    if candidates and not selection:
        warnings.append('strategy_selection_missing')
        strategy_selection_valid=False
    for choice in selection:
        index=choice.get('candidate_index') if isinstance(choice,dict) else None
        if type(index) is not int or not 0<=index<len(candidates) or not str(choice.get('reason','')).strip():
            failures.append('strategy_selection_invalid');strategy_selection_valid=False
    # This is a contract/evidence check, not an aesthetic or commercial score.
    passed=not failures
    from harness.learning.director_gates import evaluate_director_gates
    stage_gates = evaluate_director_gates(plan)
    return {'schema':'visualagent.plan-evaluation.v1','passed':passed,'failures':sorted(set(failures)),
        'warnings':sorted(set(warnings)),'checks':{'single_claim':not any(x=='single_claim_missing' for x in failures),
        'three_timed_beats':'requires_three_five_second_beats' not in failures,
        'native_audio_prompts':not any('audio_prompt_missing' in x for x in failures),
        'originality_guard':not any('copied_term' in x for x in failures),
        'strategy_selection':strategy_selection_valid},'stage_gates':stage_gates,
        'training_eligible':False}
