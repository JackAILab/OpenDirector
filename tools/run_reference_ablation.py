#!/usr/bin/env python3
"""Common-record reference ablation: two decision slots plus plan per policy."""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import validate,visible_input,FactOracle,digest
from harness.research.reference_ablation import VERSION, POLICIES as CONDITIONS, decision_messages, reference_input, project_reference, REFERENCE_CONTENTS
from harness.research.transfer import plan_messages
from harness.models.research_planner import IncompletePlanningError
from harness.tools.research_ablation import decide_once
from harness.tools.research_transfer import transfer_step,TransferValidationError
from harness.tools.research_question import ask_research_fact,apply_answer
from tools.run_paper_smoke import save


async def run(args):
    if type(args.max_tokens) is not int or not 1000<=args.max_tokens<=8000:raise ValueError('Invalid token budget')
    question_budget=getattr(args,'question_budget',3)
    if type(question_budget) is not int or question_budget not in (0,3):raise ValueError('Invalid question budget')
    fixed_turns=2
    if fixed_turns is not None and (type(fixed_turns) is not int or not 1<=fixed_turns<=3):raise ValueError('Invalid fixed decision turns')
    max_decisions=fixed_turns if fixed_turns is not None else max(1,question_budget)
    data=json.loads(args.briefs.read_text());cards=[c for c in validate(data) if c['id']==args.card_id]
    source=json.loads(args.references.read_text());refs=[r for r in source['references'] if r['reference_id']==args.reference_id]
    if len(cards)!=1 or len(refs)!=1:raise ValueError('Expected one card and reference')
    card=cards[0];assigned_ref=refs[0]
    if args.reference_mode not in ('present','absent'):raise ValueError('Invalid reference mode')
    reference_input(assigned_ref)
    reference_content=getattr(args,'reference_content','full')
    projected_ref=project_reference(assigned_ref,reference_content)
    ref=projected_ref if args.reference_mode=='present' else None
    initial=visible_input(card,'underspecified')
    conditions=list(CONDITIONS);random.Random(args.seed).shuffle(conditions)
    if args.execute and any(not os.environ.get(k) for k in ('CREATIVE_MODEL_KEY_FILE','CREATIVE_MODEL_URL')):
        raise ValueError('Missing research service configuration')
    code_files=['harness/research/bridge_assumptions.py','harness/tools/research_plan.py','tools/run_paper_smoke.py','harness/research/briefs.py','harness/research/reference_ablation.py','harness/research/prerequisites.py',
        'harness/research/transfer.py','harness/models/research_planner.py','harness/tools/research_ablation.py',
        'harness/tools/research_question.py','harness/tools/research_transfer.py','tools/run_reference_ablation.py']
    root=Path(__file__).resolve().parents[1]
    manifest={'schema':'visualagent.reference-ablation-development.v1','protocol_version':VERSION,
        'dataset_sha256':digest(data),'reference_sha256':digest(ref),'card_id':args.card_id,'reference_id':args.reference_id if ref else None,
        'assigned_reference_id':args.reference_id,'assigned_reference_sha256':digest(assigned_ref),
        'reference_mode':args.reference_mode,'reference_content':reference_content,'order_seed':args.seed,
        'family_id':card['family_id'],'parent_card_id':card.get('evaluation_only',{}).get('parent_card_id'),
        'visible_input_sha256':digest(initial),'effective_max_questions_per_condition':min(question_budget,1),
        'information':'underspecified','model':args.model,'temperature':0,'max_output_tokens':args.max_tokens,
        'max_calls':2*(max_decisions+1),'max_questions_per_condition':question_budget,'fixed_decision_turns':fixed_turns,
        'conditions':conditions,'execute':args.execute,
        'implementation_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in code_files},
        'initial_prompts':{c:decision_messages(initial,ref,[],c,question_budget) for c in conditions},
        'training_eligible':False,'scope':'Development common-record strategy-priority comparison; not a representation ablation or independent benchmark.'}
    args.out.mkdir(parents=True,exist_ok=False);args.out.chmod(0o700);save(args.out/'manifest.json',manifest)
    if not args.execute:print(json.dumps({'state':'dry_run','calls':0,'max_calls':manifest['max_calls']}));return
    events=[];summaries=[]
    for condition in conditions:
        visible=visible_input(card,'underspecified');oracle=FactOracle(card,question_budget);history=[];recommendation=None;failed=False
        async def invoke(stage,prompt):
            event={'condition':condition,'stage':stage,'prompt_sha256':digest(prompt),'started_at':datetime.now(timezone.utc).isoformat()}
            name=condition+'-'+stage;save(args.out/(name+'-input.json'),{'messages':prompt})
            save(args.out/(name+'-attempt.json'),event);started=time.monotonic();observation=None
            try:
                if stage=='plan':observation=await transfer_step(prompt,args.model,'plan',list(visible['facts']),max_tokens=args.max_tokens)
                else:observation=await decide_once(visible,ref,history,condition,question_budget-oracle.used,
                    args.model,args.max_tokens,force_finish=force_finish)
                if stage!='plan' and question_budget==0 and observation['result']['action']!='finish':
                    raise ValueError('question_budget_exceeded')
                save(args.out/(name+'-observation.json'),observation)
                event.update(state='completed',observation_sha256=digest(observation))
            except Exception as e:
                observation=None
                event.update(state='failed',error_type=type(e).__name__,error_code='question_budget_exceeded' if str(e)=='question_budget_exceeded' else 'protocol_or_provider_failure')
                if isinstance(e,(TransferValidationError,IncompletePlanningError)):
                    # Exception codes are local fixed strings; diagnostics never contain model text.
                    event.update(error_code=str(e),diagnostics=e.diagnostics,usage=e.usage)
            event['elapsed_seconds']=round(time.monotonic()-started,3)
            save(args.out/(name+'-event.json'),event);events.append(event)
            print(json.dumps({k:event[k] for k in ('condition','stage','state','elapsed_seconds')}),flush=True)
            return observation
        for turn in range(max_decisions):
            force_finish=fixed_turns is not None and turn==max_decisions-1
            prompt=decision_messages(visible,ref,history,condition,question_budget-oracle.used,force_finish=force_finish)
            observation=await invoke(f'decision-{turn}',prompt)
            if observation is None:failed=True;break
            decision=observation['result'];recommendation=decision
            if decision['action']=='finish':
                if fixed_turns is None or force_finish or turn+1>=max_decisions:break
                history.append({'decision':decision,'answer':None})
                continue
            answer=ask_research_fact(oracle,decision['question'])
            save(args.out/f'{condition}-answer-{turn}.json',answer)
            history.append({'decision':decision,'answer':answer['observation']})
            visible=apply_answer(visible,answer)
        completed=False
        if not failed:
            # Latest disclosed facts remain authoritative even if the last decision preceded an answer.
            save(args.out/(condition+'-final-visible.json'),visible)
            obs=await invoke('plan',plan_messages(visible,ref,{'latest_decision':recommendation,'question_history':history}))
            completed=obs is not None
        summaries.append({'condition':condition,'questions_used':oracle.used,'plan_completed':completed})
    summary={'calls':len(events),'failed_calls':sum(e['state']=='failed' for e in events),'conditions':summaries,
        'semantic_review':'pending','training_eligible':False,'video_calls':0,'effectiveness_conclusion':None}
    save(args.out/'summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--briefs',type=Path,default=Path(__file__).resolve().parents[1]/'data/research/advertising_briefs_v1.json')
    p.add_argument('--references',type=Path,required=True);p.add_argument('--card-id',required=True)
    p.add_argument('--reference-id',required=True);p.add_argument('--model',required=True)
    p.add_argument('--question-budget',type=int,choices=(0,3),default=3)
    p.add_argument('--reference-mode',choices=('present','absent'),required=True)
    p.add_argument('--reference-content',choices=REFERENCE_CONTENTS,default='full',
                   help='full preserves historical input; observations excludes machine interpretations and transfer advice')
    p.add_argument('--seed',type=int,default=17)
    p.add_argument('--max-tokens',type=int,default=4400);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true');asyncio.run(run(p.parse_args()))
