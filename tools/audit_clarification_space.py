#!/usr/bin/env python3
"""Audit controlled oracle disclosure opportunities, not semantic information gain."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import validate,visible_input,digest
from harness.research.interaction import FACT_SLOTS


def audit(path):
    data=json.loads(path.read_text());cards=validate(data);rows=[]
    for card in cards:
        visible=visible_input(card,'underspecified')['facts']
        rows.append({'card_id':card['id'],'family_id':card['family_id'],
            'hidden_field_count':len(card['hidden_fact_ids']),
            'newly_returnable_catalog_fields':sum(k in card['facts'] and k not in visible for k in FACT_SLOTS),
            'already_visible_catalog_fields':sum(k in visible for k in FACT_SLOTS),
            'unavailable_catalog_fields':sum(k not in card['facts'] for k in FACT_SLOTS)})
    return {'dataset':path.name,'dataset_sha256':digest(data),'cards':len(rows),
        'families':len({r['family_id'] for r in rows}),
        'distributions':{k:dict(Counter(r[k] for r in rows)) for k in
            ('hidden_field_count','newly_returnable_catalog_fields','already_visible_catalog_fields','unavailable_catalog_fields')},
        'rows':rows}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('datasets',type=Path,nargs='+');a=p.parse_args()
    print(json.dumps({'schema':'visualagent.clarification-space-audit.v1','catalog_size':len(FACT_SLOTS),
        'datasets':[audit(x) for x in a.datasets],'training_eligible':False,'model_calls':0,
        'limitations':['Card sets share authored families and are not independent samples.',
          'Returnable fields count disclosures, not semantic information gain or true product capabilities.',
          'Question text is not semantically matched by the deterministic oracle.']},ensure_ascii=False,indent=2))
