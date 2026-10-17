#!/usr/bin/env python3
"""One development case, equal reference, two conditions, at most four text calls."""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import hashlib
import os
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest,validate,visible_input
from harness.research.transfer import VERSION,CONDITIONS,review_messages,plan_messages
from harness.tools.research_transfer import transfer_step, TransferValidationError
from harness.models.research_planner import IncompletePlanningError
from tools.run_paper_smoke import save,SAFE_ERRORS


async def run(args):
    if type(args.max_tokens) is not int or not 1000<=args.max_tokens<=8000:raise ValueError("Invalid token budget")
    data=json.loads(args.briefs.read_text())
    cards=[c for c in validate(data) if c['id']==args.card_id]
    if len(cards)!=1:raise ValueError('Expected one development card')
    source=json.loads(args.references.read_text())
    reference_rows=[r for r in source['references'] if r['reference_id']==args.reference_id]
    if len(reference_rows)!=1:raise ValueError('Expected one frozen reference')
    reference=reference_rows[0];visible=visible_input(cards[0],'complete')
    conditions=list(CONDITIONS);random.Random(17).shuffle(conditions)
    if args.execute and any(not os.environ.get(k) for k in ('CREATIVE_MODEL_KEY_FILE','CREATIVE_MODEL_URL')):
        raise ValueError('Missing research service configuration')
    manifest={'schema':'visualagent.transfer-development.v1','protocol_version':VERSION,
        'dataset_sha256':digest(data),'references_sha256':digest(source),
        'reference_sha256':digest(reference),'card_id':args.card_id,'reference_id':args.reference_id,
        'model':args.model,'requested_temperature':0,'max_output_tokens_per_call':args.max_tokens,
        'implementation_sha256':{name:hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
            for name in ('harness/research/transfer.py','harness/tools/research_transfer.py','harness/models/research_planner.py','tools/run_paper_transfer.py')},
        'max_calls':4,'max_calls_per_condition':2,'conditions':conditions,'order_seed':17,
        'execute':args.execute,'information':'complete','training_eligible':False,
        'scope':'Post-selected development case; equal-reference instruction comparison, not retrieval evaluation.',
        'initial_prompts':{c:review_messages(visible,reference,c) for c in conditions}}
    args.out.mkdir(parents=True,exist_ok=False);args.out.chmod(0o700)
    save(args.out/'manifest.json',manifest)
    if not args.execute:
        print(json.dumps({'state':'dry_run','calls':0,'planned_calls_max':4}));return
    results=[];calls=0
    for condition in conditions:
        review=None
        for stage in ('review','plan'):
            prompt=review_messages(visible,reference,condition) if stage=='review' else plan_messages(visible,reference,review)
            name=condition+'-'+stage
            save(args.out/(name+'-input.json'),{'messages':prompt,'prompt_sha256':digest(prompt)})
            event={'condition':condition,'stage':stage,'prompt_sha256':digest(prompt),
                   'started_at':datetime.now(timezone.utc).isoformat()}
            save(args.out/(name+'-attempt.json'),event);calls+=1;started=time.monotonic()
            try:
                observation=await transfer_step(prompt,args.model,stage,list(visible['facts']),max_tokens=args.max_tokens)
                save(args.out/(name+'-observation.json'),observation)
                event.update(state='completed',observation_sha256=digest(observation))
                if stage=='review':review=observation['result']
            except Exception as e:
                allowed=SAFE_ERRORS|{'invalid_review','invalid_transfer_plan'}
                code=str(e) if str(e) in allowed else 'json_decode_error' if isinstance(e,json.JSONDecodeError) else 'unclassified_error'
                event.update(state='failed',error_type=type(e).__name__,error_code=code)
                if isinstance(e,(TransferValidationError,IncompletePlanningError)):
                    event.update(diagnostics=e.diagnostics,usage=e.usage)
            event['elapsed_seconds']=round(time.monotonic()-started,3)
            save(args.out/(name+'-event.json'),event);results.append(event)
            print(json.dumps({k:event[k] for k in ('condition','stage','state','elapsed_seconds')}),flush=True)
            if event['state']=='failed':break
    summary={'calls':calls,'completed_stages':sum(e['state']=='completed' for e in results),
        'failed_stages':sum(e['state']=='failed' for e in results),
        'completed_plans':sum(e['stage']=='plan' and e['state']=='completed' for e in results),
        'semantic_review':'pending','effectiveness_conclusion':None,'training_eligible':False,'video_calls':0}
    save(args.out/'summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--briefs',type=Path,default=Path(__file__).resolve().parents[1]/'data/research/advertising_briefs_v1.json')
    p.add_argument('--references',type=Path,required=True)
    p.add_argument('--card-id',required=True);p.add_argument('--reference-id',required=True)
    p.add_argument('--max-tokens',type=int,default=4400)
    p.add_argument('--model',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args();asyncio.run(run(args))
