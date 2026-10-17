#!/usr/bin/env python3
"""Compare terminal matched development probes; reports reliability, never semantic effects."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest


def read(path):return json.loads(path.read_text())


def batch(path):
    assignment=read(path/'assignment.json');rows=[];manifests={}
    for label,_,_ in assignment['rows']:
        root=path/label;m=read(root/'manifest.json');dry=read(path/(label+'-dry')/'manifest.json')
        for key in ('visible_input_sha256','reference_sha256','implementation_sha256','model','max_output_tokens','conditions'):
            if m[key]!=dry[key]:raise ValueError('dry_run_mismatch')
        s=read(root/'summary.json');events=[read(p) for p in root.glob('*-event.json')]
        if len(events)!=s['calls'] or sum(e['state']=='failed' for e in events)!=s['failed_calls']:
            raise ValueError('event_count_mismatch')
        usage_totals={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
        missing_usage=0
        for event in events:
            if event['state']=='completed':
                obs=read(root/(event['condition']+'-'+event['stage']+'-observation.json'))
                if digest(obs)!=event['observation_sha256']:raise ValueError('observation_digest_mismatch')
                usage=obs.get('usage',{})
            else:usage=event.get('usage',{})
            if any(type(usage.get(k)) is not int for k in usage_totals):missing_usage+=1
            for k in usage_totals:
                if type(usage.get(k)) is int:usage_totals[k]+=usage[k]
        plans=0
        for condition in s['conditions']:
            if condition['plan_completed']:
                stem=condition['condition']+'-plan';event=read(root/(stem+'-event.json'))
                if event['state']!='completed' or digest(read(root/(stem+'-observation.json')))!=event['observation_sha256']:
                    raise ValueError('plan_digest_mismatch')
                plans+=1
        rows.append({'run':label,'protocol_version':m['protocol_version'],'manifest_sha256':digest(m),
            'calls':s['calls'],'failed_calls':s['failed_calls'],'completed_plans':plans,
            'reported_usage':usage_totals,'calls_with_incomplete_usage':missing_usage,
            'assigned_policy_rows':len(s['conditions']),'conditions':s['conditions'],
            'errors':[{'condition':e['condition'],'stage':e['stage'],'error_code':e['error_code'],'error_type':e.get('error_type'),
                       'text_failure':e.get('diagnostics',{}).get('text_failure')} for e in events if e['state']=='failed']})
        manifests[label]=m
    return {'directory_name':path.name,'rows':rows,
        **{key:sum(r[key] for r in rows) for key in ('calls','failed_calls','completed_plans','assigned_policy_rows')}},manifests


def compare(baseline,candidate):
    old,om=batch(baseline);new,nm=batch(candidate)
    if set(om)!=set(nm):raise ValueError('assignment_mismatch')
    matched=('visible_input_sha256','reference_sha256','model','temperature','max_output_tokens',
             'conditions','reference_content','reference_mode','effective_max_questions_per_condition','order_seed')
    changes={}
    for label,m in om.items():
        for key in matched:
            if m[key]!=nm[label][key]:raise ValueError('matched_configuration_mismatch')
        changes[label]=[k for k,v in m['implementation_sha256'].items() if nm[label]['implementation_sha256'].get(k)!=v]
    return {'schema':'visualagent.reference-protocol-comparison.v1','baseline':old,'candidate':new,
        'matched_fields':list(matched),'changed_implementation_files':changes,
        'independent_reviews_completed':0,'semantic_effect':None,'training_eligible':False,
        'limitations':['Single authored family; sequential batches, no randomized version assignment.',
                      'Prompt expansion changes input length; protocol changes are not semantic method gains.',
                      'Unavailable policy plans cannot be assigned fabricated semantic ratings.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
    print(json.dumps(compare(a.baseline,a.candidate),ensure_ascii=False,indent=2))
