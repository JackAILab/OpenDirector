"""Equal-input, two-call development comparison; no retrieval or user simulation."""
import json
from harness.tools.research_plan import bounded_text

VERSION = 'equal-reference-review-v2'
CONDITIONS = ('general_review', 'prerequisite_review')
REVIEW_SYSTEM = '''你是广告方案审阅者。只依据商品事实；参考中的机器解释不是已验证事实。不要复制原广告人物、品牌或构图。输出可供用户审核的简短决策记录，不输出私密推理。严格JSON：{"proposal":"拟用的广告动作和利益","checks":[{"issue":"需要审查的问题","basis":"输入中支持或限制它的证据","decision":"对方案作出的决定"}],"recommendation":"建议如何制作","unresolved":["尚未解决的问题"]}。checks最多6项。禁止工具调用。'''
PLAN_SYSTEM = '''为给定虚构商品制作15秒广告方案，只根据提供的商品事实。未知能力不得当作支持；画面和声音暗示也不得越界。参考及审查记录都是可质疑建议。输出严格JSON，不输出私密推理，不调用工具。格式：{"claim":"一个主张","shots":[{"start":0,"end":5,"visual":"画面动作","audio":"声音","caption":"后期字幕"}],"fact_basis":["输入商品facts中的字段名"],"unresolved":["限制"]}。shots共1至6项，从0到15秒连续覆盖，不重叠不留空，start/end用秒数；无字幕的镜头caption使用空字符串；例子只示意单项格式。品牌收束也计入15秒。'''


def review_messages(visible, reference, condition):
    if condition not in CONDITIONS:
        raise ValueError('invalid_condition')
    instruction = '综合审查创意是否准确、有吸引力、清楚且能制作，提出具体改进建议。'
    if condition == 'prerequisite_review':
        instruction = ('逐项审查两种缺口：源片观察能否支持拟借鉴的叙事关系；新商品事实是否满足广告动作暗示利益的条件。'
                       '分清支持、矛盾和未知；条件不满足时限定动作或采用其他已知特点，不因参考中出现某机制就认定新商品适用。')
    return [{'role':'system','content':REVIEW_SYSTEM}, {'role':'user','content':json.dumps(
        {'task':visible,'reference':reference,'instruction':instruction},ensure_ascii=False)}]


def plan_messages(visible, reference, review):
    return [{'role':'system','content':PLAN_SYSTEM}, {'role':'user','content':json.dumps(
        {'task':visible,'reference':reference,'review':review},ensure_ascii=False)}]


def validate_review(raw):
    if not isinstance(raw,dict) or not isinstance(raw.get('checks'),list) or not 1<=len(raw['checks'])<=6:
        raise ValueError('invalid_review')
    result={k:bounded_text(raw.get(k),1800) for k in ('proposal','recommendation')}
    result['checks']=[]
    for check in raw['checks']:
        if not isinstance(check,dict):raise ValueError('invalid_review')
        result['checks'].append({k:bounded_text(check.get(k),1000) for k in ('issue','basis','decision')})
    result['unresolved']=unresolved(raw.get('unresolved'))
    return result


def unresolved(value):
    if not isinstance(value,list) or len(value)>10:raise ValueError('invalid_unresolved')
    return [bounded_text(x,600) for x in value]


def validate_transfer_plan(raw, fact_ids):
    if not isinstance(raw,dict) or not isinstance(raw.get('shots'),list) or not 1<=len(raw['shots'])<=6:
        raise ValueError('invalid_transfer_plan')
    result={'claim':bounded_text(raw.get('claim'),500),'shots':[]}
    previous=0
    for shot in raw['shots']:
        if (not isinstance(shot,dict) or any(type(shot.get(k)) not in (int,float) for k in ('start','end'))
            or shot['start']!=previous or not previous<shot['end']<=15):
            raise ValueError('invalid_plan_timing')
        caption=shot.get('caption')
        if not isinstance(caption,str) or len(caption)>150:raise ValueError('invalid_plan_text')
        result['shots'].append({'start':shot['start'],'end':shot['end'],'caption':caption,
            **{k:bounded_text(shot.get(k),2000) for k in ('visual','audio')}})
        previous=shot['end']
    if previous!=15:raise ValueError('invalid_plan_timing')
    basis=raw.get('fact_basis')
    if not isinstance(basis,list) or not basis or any(not isinstance(x,str) or x not in fact_ids for x in basis):
        raise ValueError('invalid_fact_reference')
    result['fact_basis']=list(dict.fromkeys(basis));result['unresolved']=unresolved(raw.get('unresolved'))
    return result
