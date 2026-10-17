"""Bounded action: validate plan observations and discard unspecified fields."""
from harness.models.research_planner import ResearchPlanner


class PlanShapeError(ValueError):
    def __init__(self, raw):
        super().__init__('invalid_plan_shape')
        self.diagnostics = {'top_level_object':isinstance(raw,dict),
                            'shots_is_list':isinstance(raw.get('shots'),list) if isinstance(raw,dict) else False,
                            'shot_count':len(raw['shots']) if isinstance(raw,dict) and isinstance(raw.get('shots'),list) else None,
                            'has_plan_wrapper':isinstance(raw.get('plan'),dict) if isinstance(raw,dict) else False}


class BoundedTextError(ValueError):
    def __init__(self, value, limit, field):
        super().__init__('invalid_plan_text')
        self.text_diagnostic = {
            'field': field,
            'reason': 'not_string' if not isinstance(value,str) else 'blank' if not value.strip() else 'over_limit',
            'length': len(value) if isinstance(value,str) else None,
            'limit': limit}


def bounded_text(value, limit, *, field=None):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise BoundedTextError(value, limit, field)
    return value


def validate_plan(raw, fact_ids):
    if not isinstance(raw,dict) or not isinstance(raw.get('shots'),list) or len(raw['shots'])!=3:
        raise PlanShapeError(raw)
    plan={'claim':bounded_text(raw.get('claim'),500),'shots':[]}
    for i,shot in enumerate(raw['shots']):
        if not isinstance(shot,dict) or any(type(shot.get(k)) is not int for k in ('start','end')) or shot['start']!=i*5 or shot['end']!=(i+1)*5:
            raise ValueError('invalid_plan_timing')
        plan['shots'].append({'start':shot['start'],'end':shot['end'],
            **{k:bounded_text(shot.get(k),2000 if k!='caption' else 150) for k in ('visual','audio','caption')}})
    basis=raw.get('fact_basis');unresolved=raw.get('unresolved')
    if not isinstance(basis,list) or not basis or any(not isinstance(k,str) or k not in fact_ids for k in basis):
        raise ValueError('invalid_fact_reference')
    if not isinstance(unresolved,list) or len(unresolved)>10:
        raise ValueError('invalid_unresolved')
    plan['fact_basis']=list(dict.fromkeys(basis))
    plan['unresolved']=[bounded_text(v,600) for v in unresolved]
    return plan


async def plan_once(messages, model, fact_ids):
    raw,usage=await ResearchPlanner(model).complete(messages)
    return {'plan':validate_plan(raw,fact_ids),'usage':usage,
            'semantic_review':'pending','training_eligible':False}
