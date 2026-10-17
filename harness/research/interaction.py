"""Finite, controlled-slot interactive development policy; not human simulation."""
import json
from harness.research.prerequisites import validate_record
from harness.tools.research_plan import bounded_text

VERSION='interactive-transfer-v3'
CONDITIONS=('general_review','prerequisite_review')
# Same public vocabulary for every product and condition; never derive from a selected card.
FACT_SLOTS=('rain_protection','wet_dry_separation','airline_size','closed_lid_leakage',
    'temperature_limit','dishwasher_safe','active_noise_reduction','multipoint',
    'wet_use','automatic_presence','dimming','battery_operation')
SYSTEM='''你为虚构商品规划广告。商品事实未知不等于支持，参考机器解释不等于证实。你可提出最多3个结构化事实问题，也可立即结束问答。每次只输出一个JSON动作，不调用外部工具，不输出私密推理。问题会由确定性事实槽协议回答；目录不是商品已有功能，不能由目录推断支持。重复或未知槽均扣一次问题预算。输出：{"action":"ask_fact或finish","question":{"fact_id":"目录中的槽名","text":"对用户的简短问题"}或null,"recommendation":"简短可审核的创意建议及限制","record":null或前提记录}。结束时question必须null。无必要不强制追问。'''
RECORD='''前提检查条件须输出record，格式：{"relation":"拟借鉴的叙事关系","target_action":"当前正在核对的原动作，不得混写替代动作","source_status":"observed_relation/interpretation/unverified之一","source_event_ids":["输入真实事件ID"],"requirements":[{"fact_id":"目标事实字段","status":"supported/contradicted/unknown之一","condition":"动作所需使用条件","basis":"提供的依据或缺口"}],"decision":"retain/constrain/ask/replace/abstain之一","question":null或与外层完全相同的问题,"replacement":null或{"target_action":"替代后的新动作","requirements":[{"fact_id":"支持替代动作的事实字段","status":"supported","condition":"新动作的使用条件","basis":"已披露依据"}]}}。这是可审核的决策说明，不是私密推理。留用或限定动作须所有列出的前提均已支持。replace必须保持外层target_action和requirements描述原动作，另在replacement中写新动作及其全部已支持前提；其他决策replacement必须null。追问须关联unknown前提；拒绝或改换动作可保留未满足前提。requirements最多8项，同一事实字段可支持多个不同条件；可选bridge_assumptions数组逐项写明source_condition、target_condition和桥接假设，不能把目标条件直接当作source fact。source_event_ids只能来自输入。'''


def decision_messages(visible,reference,history,condition,remaining,force_finish=False):
    if condition not in CONDITIONS or not 0<=remaining<=3:raise ValueError('invalid_interaction_state')
    instruction='综合考虑事实可靠性、创意、可制作性和缺失信息，自主选择最有用的问题或结束问答。record使用null。'
    if condition=='prerequisite_review':
        instruction='检查源证据是否支撑叙事关系，以及目标商品是否满足拟用动作的前提；缺口影响动作时再追问。'+RECORD
    if force_finish:
        instruction += ' 本轮是固定预算对照的收束轮，必须输出finish，question必须null；基于当前已披露事实给出最终可审核建议。'
    system=SYSTEM if remaining else SYSTEM+' 本轮问题预算为0，禁止ask_fact；仅可finish，question必须null。未披露事实保持未知，可以说明无法确认并提出有依据的替代。'
    if force_finish:
        system += ' 本轮固定要求finish，禁止ask_fact。'
    return [{'role':'system','content':system},{'role':'user','content':json.dumps({
        'task':visible,'reference':reference,'history':history,'remaining_questions':remaining,
        'available_fact_slots':list(FACT_SLOTS),'instruction':instruction},ensure_ascii=False)}]


def validate_decision(raw,visible,reference,condition):
    if not isinstance(raw,dict) or raw.get('action') not in ('ask_fact','finish'):
        raise ValueError('invalid_interaction_action')
    result={'action':raw['action'],'recommendation':bounded_text(raw.get('recommendation'),1800),'question':None,'record':None}
    if raw['action']=='ask_fact':
        q=raw.get('question')
        if not isinstance(q,dict):raise ValueError('invalid_question_action')
        # Unknown slots still reach the oracle and spend the same budget.
        result['question']={'fact_id':bounded_text(q.get('fact_id'),100),'text':bounded_text(q.get('text'),500)}
    elif raw.get('question') is not None:raise ValueError('unexpected_question')
    if condition=='prerequisite_review':
        result['record']=validate_record(raw.get('record'),visible,reference)
        if result['record']['question']!=result['question']:raise ValueError('question_record_mismatch')
        if (result['record']['decision']=='ask') != (result['action']=='ask_fact'):raise ValueError('question_record_mismatch')
    elif condition=='general_review':
        if raw.get('record') is not None:raise ValueError('unexpected_record')
    else:raise ValueError('invalid_condition')
    return result
