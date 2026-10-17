#!/usr/bin/env python3
"""Blind all completed plans across a reference probe; retain missing conditions privately."""
import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from tools.prepare_relation_source_review import file_hash


def build(batch,source_packet,out,seed=211):
    assignment=json.loads((batch/'assignment.json').read_text());plans=[];missing=[]
    for run,_,_ in assignment['rows']:
        root=batch/run;summary=json.loads((root/'summary.json').read_text())
        for c in summary['conditions']:
            condition=c['condition']
            if not c['plan_completed']:
                missing.append({'run':run,'condition':condition});continue
            prefix=condition+'-plan';event=json.loads((root/(prefix+'-event.json')).read_text())
            obs=json.loads((root/(prefix+'-observation.json')).read_text())
            inp=json.loads((root/(prefix+'-input.json')).read_text())
            if event['state']!='completed' or digest(obs)!=event['observation_sha256'] or digest(inp['messages'])!=event['prompt_sha256']:
                raise ValueError('plan_evidence_mismatch')
            task=json.loads(inp['messages'][1]['content'])['task']
            plans.append({'plan':obs['result'],'task':task,'private':{'run':run,'condition':condition,'observation_sha256':digest(obs)}})
    if not plans:raise ValueError('no_completed_plans')
    rng=random.Random(seed);rng.shuffle(plans)
    source=json.loads((source_packet/'packet.json').read_text())
    mapping=json.loads((source_packet/'private-mapping.json').read_text())['mapping']
    clips=[c for c in source['clips'] if mapping[c['label']] in ('R009','R010')]
    if len(clips)!=2:raise ValueError('expected_two_reference_clips')
    rng.shuffle(clips)
    for c in clips:
        if file_hash(source_packet/c['media'])!=c['sha256']:raise ValueError('media_digest_mismatch')
    out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    private={'plans':{},'sources':{},'missing_conditions':missing,'seed':seed}
    exposed=[]
    for i,p in enumerate(plans,1):
        label=f'P{i:02d}';private['plans'][label]=p.pop('private');exposed.append({'label':label,**p})
    sources=[]
    for i,c in enumerate(clips,1):
        label=f'V{i:02d}';name=label+'.mp4';shutil.copyfile(source_packet/c['media'],out/name)
        if file_hash(out/name)!=c['sha256']:raise ValueError('copied_media_mismatch')
        private['sources'][label]=mapping[c['label']]
        sources.append({'label':label,'media':name,'sha256':c['sha256'],'duration':c['duration']})
    template_path=Path(__file__).with_name('reference_plan_review.html')
    packet={'schema':'visualagent.reference-plan-review-packet.v1','plans':exposed,'sources':sources,
            'form_template_sha256':file_hash(template_path),
            'training_eligible':False,'semantic_review':'pending'}
    for name,data in [('packet.json',packet),('private-mapping.json',private)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    payload=json.dumps({'packet':packet,'packet_sha256':digest(packet)},ensure_ascii=False).replace('<','\\u003c')
    html=template_path.read_text().replace('__PACKET_DATA__',payload)
    (out/'review.html').write_text(html)
    with zipfile.ZipFile(out/'reviewer-package.zip','x',compression=zipfile.ZIP_STORED) as z:
        for name in ['packet.json','review.html']+[c['media'] for c in sources]:z.write(out/name,name)
    return {'packet_sha256':digest(packet),'completed_plans':len(plans),'missing_conditions':len(missing),
            'source_clips':len(sources),'independent_reviews_completed':0,'training_eligible':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('batch','source-packet','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seed',type=int,default=211);a=p.parse_args()
    print(json.dumps(build(a.batch,a.source_packet,a.out,a.seed)))
