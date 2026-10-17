#!/usr/bin/env python3
"""Offline checks of what the current pilot can identify; no model calls."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest, visible_input, validate
from harness.research.interaction import decision_messages
from harness.research.prerequisites import validate_record


def audit(dataset):
    cards = validate(dataset)
    families = sorted({c['family_id'] for c in cards})
    reference = {'reference_id':'synthetic-control', 'evidence':{'events':[]},
                 'interpretation':{}, 'training_eligible':False}
    rows=[]
    for family in families:
        group=[c for c in cards if c['family_id']==family]
        inputs=[visible_input(c,'underspecified') for c in group]
        hashes=[digest(decision_messages(v,reference,[],'general_review',0)) for v in inputs]
        rows.append({'family_id':family,'cards':len(group),
                     'unique_initial_visible_inputs':len({digest(v) for v in inputs}),
                     'unique_fixed0_initial_prompts':len(set(hashes)),
                     'explicit_action_request_count':sum('客户创意要求：' in c['brief'] for c in group)})
    visible=visible_input(cards[0],'underspecified')
    record={'relation':'source absent control','target_action':'use disclosed feature',
            'source_status':'unverified','source_event_ids':[]}
    try:
        validate_record(record,visible,reference)
        no_reference_result='accepted'
    except ValueError as exc:
        no_reference_result=str(exc)
    return {'schema':'visualagent.transfer-identifiability-audit.v1',
            'dataset_sha256':digest(dataset),'family_count':len(families),'card_count':len(cards),
            'families':rows,'prerequisite_empty_reference_validation':no_reference_result,
            'interpretation':'Identical visible inputs do not constitute independent capability-state observations in fixed0. Explicit requests do not establish reference-derived mechanism discovery.',
            'paid_calls':0,'training_eligible':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=Path('data/research/advertising_goal_dependent_briefs_v2.json'))
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); result=audit(json.loads(a.dataset.read_text()))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['family_count','card_count','prerequisite_empty_reference_validation','paid_calls']}))
