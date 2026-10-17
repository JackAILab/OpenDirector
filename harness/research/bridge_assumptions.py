"""Represent transfer claims with explicit source, target and bridge assumptions."""
from harness.tools.research_plan import bounded_text

STATUSES=('supported','contradicted','unknown')
BRIDGE=('direct_match','reasonable_with_assumption','unsupported_leap','not_needed')

def validate_assumptions(raw, visible, *, field_prefix="bridge_assumptions"):
    if not isinstance(raw,list) or not 1<=len(raw)<=10:raise ValueError('invalid_bridge_assumptions')
    result=[]
    for index,row in enumerate(raw):
        if not isinstance(row,dict):raise ValueError('invalid_bridge_assumption')
        for key in ('source_condition','target_condition','bridge_assumption','basis'):
            bounded_text(row.get(key),800,field=f'{field_prefix}[{index}].{key}')
        status=row.get('status');bridge=row.get('bridge_status')
        if status not in STATUSES or bridge not in BRIDGE:raise ValueError('invalid_bridge_status')
        fact=row.get('fact_id');
        if not isinstance(fact,str) or not fact.strip():raise ValueError('invalid_bridge_fact')
        if status!='unknown' and fact not in visible['facts']:raise ValueError('undisclosed_bridge_fact')
        result.append({'fact_id':fact,'source_condition':row['source_condition'],'target_condition':row['target_condition'],
            'bridge_assumption':row['bridge_assumption'],'basis':row['basis'],'status':status,'bridge_status':bridge})
    return result
