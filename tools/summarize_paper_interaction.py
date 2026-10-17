#!/usr/bin/env python3
"""Aggregate protocol outcomes without turning structure checks into quality scores."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest,validate


def summarize(dataset_path, runs):
    dataset=json.loads(dataset_path.read_text());cards={c['id']:c for c in validate(dataset)}
    rows=[];seen=set();protocols=set();models=set();references=set();code=set();initial_prompts={}
    for run in runs:
        manifest=json.loads((run/'manifest.json').read_text())
        if manifest['dataset_sha256']!=digest(dataset):raise ValueError('Dataset mismatch')
        card=cards[manifest['card_id']]
        protocols.add(manifest['protocol_version']);models.add(manifest['model']);references.add(manifest['reference_sha256'])
        code.add(digest(manifest['implementation_sha256']))
        summary=json.loads((run/'summary.json').read_text())
        for condition in manifest['conditions']:
            budget=manifest.get('max_questions_per_condition',3)
            key=(card['id'],condition,budget)
            if key in seen:raise ValueError('Duplicate case condition')
            seen.add(key)
            initial_prompts.setdefault(condition,set()).add(digest(manifest['initial_prompts'][condition]))
            stages=[];usage={k:0 for k in ('prompt_tokens','completion_tokens','total_tokens')};missing_usage=0
            events=sorted(run.glob(condition+'-*-event.json'))
            for path in events:
                event=json.loads(path.read_text());name=path.name.removesuffix('-event.json')
                inp=json.loads((run/(name+'-input.json')).read_text())['messages']
                if digest(inp)!=event['prompt_sha256']:raise ValueError('Prompt digest mismatch')
                if event['state']=='completed':
                    observation=json.loads((run/(name+'-observation.json')).read_text())
                    if digest(observation)!=event['observation_sha256']:raise ValueError('Observation digest mismatch')
                    reported=observation.get('usage',{})
                else:reported=event.get('usage',{})
                if all(type(reported.get(k)) is int for k in usage):
                    for k in usage:usage[k]+=reported[k]
                else:missing_usage+=1
                stages.append({'stage':event['stage'],'state':event['state'],'elapsed_seconds':event['elapsed_seconds']})
            entry=next(x for x in summary['conditions'] if x['condition']==condition)
            plan_completed=any(e['stage']=='plan' and e['state']=='completed' for e in stages)
            if plan_completed!=entry['plan_completed']:raise ValueError('Summary plan state mismatch')
            answers=[json.loads(p.read_text()) for p in sorted(run.glob(condition+'-answer-*.json'))]
            if len(answers)!=entry['questions_used']:raise ValueError('Summary question count mismatch')
            rows.append({'card_id':card['id'],'family_id':card['family_id'],
                'capability_status':card['evaluation_only']['capability_status'],'condition':condition,
                'question_budget':budget,
                'initial_task_sha256':digest(json.loads(manifest['initial_prompts'][condition][1]['content'])['task']),
                'calls':len(stages),'questions':len(answers),'asked_fact_ids':[a['question']['fact_id'] for a in answers],
                'completed_plan':plan_completed,'failed_calls':sum(x['state']=='failed' for x in stages),
                'usage':usage,'calls_with_missing_usage':missing_usage,
                'elapsed_seconds':round(sum(x['elapsed_seconds'] for x in stages),3),
                'semantic_review':'pending'})
    return {'schema':'visualagent.interaction-cohort-summary.v1','dataset_sha256':digest(dataset),
        'run_count':len(runs),'independent_family_count':len({r['family_id'] for r in rows}),
        'condition_count':len(rows),'calls':sum(r['calls'] for r in rows),
        'completed_plans':sum(r['completed_plan'] for r in rows),'failed_calls':sum(r['failed_calls'] for r in rows),
        'protocols':sorted(protocols),'models':sorted(models),'distinct_reference_hashes':len(references),
        'distinct_implementation_hashes':len(code),
        'distinct_initial_prompts_by_condition':{k:len(v) for k,v in initial_prompts.items()},
        'rows':rows,'independent_reviews_completed':0,'effectiveness_conclusion':None,'training_eligible':False,
        'limitations':['Developer-authored one-family probes are not an independent benchmark.',
            'Prompt identity does not guarantee deterministic remote model responses.',
            'Observed choices require separate semantic review; no automatic quality score computed.',
            'These variants test answer sensitivity, not the causal benefit of asking versus not asking.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=summarize(a.dataset,a.runs)
    with a.out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('run_count','independent_family_count','calls','completed_plans','failed_calls')}))
