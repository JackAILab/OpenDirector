"""Separate development protocol with a common output contract across policies."""
from copy import deepcopy
import json
from harness.research.interaction import SYSTEM, RECORD, FACT_SLOTS
from harness.research.prerequisites import validate_record
from harness.tools.research_plan import bounded_text

VERSION = 'reference-ablation-v2'
POLICIES = ('general_review', 'prerequisite_review')
REFERENCE_CONTENTS = ('full', 'observations')
INSTRUCTIONS = {
    'general_review': '综合考虑事实可靠性、创意、可制作性和缺失信息，自主选择最有用的问题或结束问答。',
    'prerequisite_review': '优先核对源证据是否支持叙事关系及目标商品是否满足动作前提；只在缺口会改变动作选择时追问。',
}
# Both policies must emit exactly the same schema, including factual safeguards.
CONTRACT = RECORD.replace('前提检查条件须输出record', '两种策略均须输出record').replace(
    'observed_relation/interpretation/unverified之一',
    'observed_relation/interpretation/unverified/no_source之一') + (
    ' reference为null表示没有参考，source_status必须no_source，source_event_ids必须空数组；'
    '有参考时不得使用no_source且须引用输入事件。不得发明事件或把自创叙事写成源观察。'
    ' bridge_assumptions是可选字段，不使用时省略或设为null，不要写空数组。'
    '使用时须为1至10项对象，每项必须完整包含以下7个字段：'
    'source_condition、target_condition、bridge_assumption、basis均为非空字符串，每项最多800字符；'
    'fact_id为非空的目标事实字段名；status只能是supported、contradicted、unknown；'
    'bridge_status只能是direct_match、reasonable_with_assumption、unsupported_leap、not_needed。'
    'bridge_assumption是固定英文键名，值用简短文字说明桥接假设；无须假设也须明确写文字说明，不能用null、数组或对象。'
    'status为supported或contradicted时fact_id必须存在于当前可见facts中；未披露的目标事实只能标unknown。')


def reference_input(reference):
    if reference is None:
        return {'availability': 'absent', 'evidence': {'events': []}}
    if not isinstance(reference, dict) or reference.get('availability') == 'absent':
        raise ValueError('invalid_reference')
    events = reference.get('evidence', {}).get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('empty_reference_requires_null')
    ids = [e.get('event_id') if isinstance(e, dict) else None for e in events]
    if any(not isinstance(x,str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid_reference_event_ids')
    return deepcopy(reference)


def project_reference(reference, content):
    """Explicit input treatment; sampled machine observations remain unverified."""
    if content not in REFERENCE_CONTENTS:
        raise ValueError('invalid_reference_content')
    ref = reference_input(reference)
    if reference is None:
        return None
    if content == 'full':
        return ref
    # Allowlist prevents transfer advice, interpretations or future metadata from
    # entering either decision or plan prompts through an alternate field.
    evidence = ref['evidence']
    keys = ('scope', 'audio_semantics_reviewed', 'full_motion_reviewed', 'independent_review')
    event_keys = ('event_id', 'start', 'end', 'visual_observation', 'sampled_frame_indices', 'status')
    return {'reference_id': ref.get('reference_id'),
            'evidence': {**{k: evidence[k] for k in keys if k in evidence},
                         'events': [{k: e[k] for k in event_keys if k in e} for e in evidence['events']]},
            'training_eligible': False}


def decision_messages(visible, reference, history, policy, remaining, force_finish=False):
    if policy not in POLICIES or type(remaining) is not int or not 0 <= remaining <= 3:
        raise ValueError('invalid_ablation_state')
    reference_input(reference)
    system = SYSTEM + CONTRACT
    if not remaining or force_finish:
        system += ' 本轮仅允许finish，question必须null；不得再追问。'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps({
        'task': visible, 'reference': reference, 'history': history,
        'available_fact_slots': list(FACT_SLOTS), 'remaining_questions': remaining,
        'instruction': INSTRUCTIONS[policy]}, ensure_ascii=False)}]


def validate_decision(raw, visible, reference, policy, remaining, force_finish=False):
    if policy not in POLICIES or type(remaining) is not int or not 0 <= remaining <= 3:
        raise ValueError('invalid_ablation_state')
    ref = reference_input(reference)
    if not isinstance(raw, dict) or raw.get('action') not in ('ask_fact','finish'):
        raise ValueError('invalid_interaction_action')
    if raw['action'] == 'ask_fact' and (not remaining or force_finish):
        raise ValueError('question_budget_exceeded')
    record = validate_record(raw.get('record'), visible, ref, absent_reference=reference is None)
    question = None
    if raw['action'] == 'ask_fact':
        q = raw.get('question')
        if not isinstance(q, dict):
            raise ValueError('invalid_question_action')
        question = {k: bounded_text(q.get(k), limit,field='question.'+k) for k, limit in [('fact_id',100),('text',500)]}
    elif raw.get('question') is not None:
        raise ValueError('unexpected_question')
    if record['question'] != question or (record['decision'] == 'ask') != (raw['action'] == 'ask_fact'):
        raise ValueError('question_record_mismatch')
    return {'action': raw['action'], 'question': question, 'record': record,
            'recommendation': bounded_text(raw.get('recommendation'),1800,field='recommendation')}
