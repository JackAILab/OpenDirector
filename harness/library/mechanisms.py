"""Explainable mechanism vocabulary for reference-ad retrieval.

Labels are retrieval hints, not quality judgements or training labels.
"""
MECHANISMS=('pressure_test','observable_task','misdirection_reveal','contrast_reversal',
            'human_reaction','accumulation','product_as_action','brand_reveal')
_TERMS={
 'pressure_test':('极端','压力','受限','恶劣','混乱','障碍','风险','挑战','关键时刻','extreme','constraint','obstacle'),
 'observable_task':('任务','动作','结果','演示','可见','完成','操作','task','result','demonstrat'),
 'misdirection_reveal':('误判','悬念','寻找','看不见','揭示','重新解释','预期','puzzle','reveal','misdirect'),
 'contrast_reversal':('反差','反转','对照','相反','改写','转义','before','after','contrast','reversal'),
 'human_reaction':('情感','关系','笑点','亲密','反应','社交','human','reaction'),
 'accumulation':('反复','累积','逐渐','越来越','连续','大量','共享','accumulat','repeated'),
 'product_as_action':('功能','能力','完成','撤回','打开','手机','product','feature'),
 'brand_reveal':('品牌','标志','落版','归因','收束','logo','brand','attribution'),
}

def classify(*values):
    text=' '.join(str(value or '') for value in values).lower()
    scores={name:sum(text.count(term.lower()) for term in terms if term) for name,terms in _TERMS.items()}
    return [name for name in MECHANISMS if scores[name]>0][:5]

def annotate(record):
    result=dict(record)
    # Positive mechanism tags come from the strategy statement itself.  The
    # transfer and avoid lists are useful guidance, but including them here
    # made generic words such as “人物” turn every candidate into a reaction
    # example and polluted retrieval statistics.
    result['mechanism_tags']=classify(record.get('principle'),record.get('mechanism'))
    result['shooting_grammar']=shooting_grammar(result)
    return result


def shooting_grammar(record):
    """Summarize sampled evidence as transferable timing roles.

    These windows are observations, not reconstructed cuts or hidden author
    reasoning. They give the director a compact way to compare how a case
    moves from attention to proof and attribution without copying its shots.
    """
    import math
    raw = record.get('beats') or []
    if not isinstance(raw,list):raw=[]
    windows=[]
    for beat in raw[:8]:
        if not isinstance(beat,dict):
            continue
        start,end=beat.get('start'),beat.get('end')
        if type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
            continue
        purpose=str(beat.get('purpose') or '').strip()[:260]
        observation=str(beat.get('observation') or '').strip()[:420]
        if not purpose and not observation:
            continue
        windows.append({'start':start,'end':end,'purpose':purpose,'observation':observation})
    windows.sort(key=lambda item:(item['start'],item['end']))
    roles=[]
    if windows:
        for window in windows:
            purpose=window['purpose'].lower()
            role='unknown'
            for name,terms in (
                ('attribution_or_close',('品牌归因','落版','收束','结尾','attribution','close')),
                ('hook',('注意','悬念','开场','吸引','hook','attention')),
                ('proof_or_reframe',('证明','结果','反转','重释','揭示','proof','reframe')),
            ):
                if any(term in purpose for term in terms):
                    role=name;break
            roles.append({**window,'role':role,'role_basis':'heuristic_over_analysis_purpose'})
    return {
        'schema':'visualagent.sampled-shooting-grammar.v1',
        'evidence_type':'timecoded_sampled_windows',
        'windows':roles,
        'transfer_instruction':'核对观察与用途后选择适用的因果结构，重新设计商品、人物、场景和镜头；不要照搬原片时长。',
        'warning':'采样窗口不是原片精确剪辑点、运镜或声音事实。',
    }
