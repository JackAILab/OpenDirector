#!/usr/bin/env python3
"""At most six explicit text-planning calls on one development family; no video generation."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest,validate,visible_input
from harness.research.planning import CONDITIONS,PROMPT_VERSION,messages
from harness.tools.research_plan import plan_once, PlanShapeError

SAFE_ERRORS = {'planning_incomplete','invalid_plan_text','invalid_plan_shape','invalid_plan_timing',
               'invalid_fact_reference','invalid_unresolved'}


def save(path, data):
    with path.open('x') as f:
        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


async def run(args):
    data=json.loads(args.briefs.read_text());cards=[c for c in validate(data) if c['family_id']==args.family]
    if len(cards)!=3:raise ValueError('Expected exactly three counterfactual variants')
    tasks=[]
    for card in cards:
        visible=visible_input(card,'complete')
        for condition in CONDITIONS:
            prompt=messages(visible,condition)
            tasks.append({'card_id':card['id'],'condition':condition,'prompt':prompt,
                          'prompt_sha256':digest(prompt),'fact_ids':list(visible['facts'])})
    random.Random(17).shuffle(tasks)
    if not 1 <= args.max_calls <= 6:raise ValueError("max_calls must be between 1 and 6")
    tasks=tasks[:args.max_calls]
    if args.execute:
        for k in ('CREATIVE_MODEL_KEY_FILE','CREATIVE_MODEL_URL'):
            if not os.environ.get(k):raise ValueError('Missing research service configuration')
    args.out.mkdir(parents=True,exist_ok=False)
    args.out.chmod(0o700)
    save(args.out/'manifest.json',{'schema':'visualagent.paper-smoke.v1','dataset_sha256':digest(data),
        'prompt_version':PROMPT_VERSION,'model':args.model,'requested_temperature':0,'max_output_tokens':2200,
        'max_calls':len(tasks),'execute':args.execute,'family':args.family,'information':'complete',
        'order_seed':17,'tasks':tasks,'scope':'Development protocol smoke test, not a mechanism-transfer experiment.'})
    counts={'completed':0,'failed':0,'not_started':len(tasks)}
    if not args.execute:
        print(json.dumps({'state':'dry_run','calls':0}));return
    for i,task in enumerate(tasks):
        started=time.monotonic();counts['not_started']-=1
        event={'index':i,'condition':task['condition'],'prompt_sha256':task['prompt_sha256'],
               'started_at':datetime.now(timezone.utc).isoformat()}
        # Persist the attempted-call boundary before calling the provider. A new invocation
        # refuses this directory, including when delivery/acceptance was uncertain.
        save(args.out/f'{i:02d}-attempt.json',event)
        try:
            result=await plan_once(task['prompt'],args.model,task['fact_ids'])
            save(args.out/f'{i:02d}-observation.json',result)
            event.update(state='completed',observation_sha256=digest(result));counts['completed']+=1
        except Exception as e:
            code = str(e) if str(e) in SAFE_ERRORS else 'planning_http_error' if str(e).startswith('planning_http_') and str(e)[14:].isdigit() else 'json_decode_error' if isinstance(e,json.JSONDecodeError) else 'unclassified_error'
            event.update(state='failed',error_type=type(e).__name__,error_code=code);counts['failed']+=1
            if isinstance(e,PlanShapeError):event['shape_diagnostics']=e.diagnostics
        event['elapsed_seconds']=round(time.monotonic()-started,3)
        save(args.out/f'{i:02d}-event.json',event)
        print(json.dumps({'index':i,'state':event['state'],'elapsed_seconds':event['elapsed_seconds']}),flush=True)
    save(args.out/'summary.json',{'counts':counts,'semantic_review':'pending','comparison_ready':False,
                                 'training_eligible':False,'paid_video_calls':0})
    print(json.dumps(counts))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--briefs',type=Path,default=Path(__file__).resolve().parents[1]/'data/research/advertising_briefs_v1.json')
    p.add_argument('--max-calls',type=int,default=6)
    p.add_argument('--family',default='carry');p.add_argument('--model',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true')
    asyncio.run(run(p.parse_args()))


if __name__=='__main__':main()
