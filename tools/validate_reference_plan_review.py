#!/usr/bin/env python3
"""Read-only intake for staged cross-reference ratings; no gold-label promotion."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from tools.validate_relation_review import require,fields,text

CHOICES={'violation':('有','无','无法判断'),'goal':('是','部分','否','无法判断'),
         'utility':('1','2','3','4','5','无法判断'),
         'view':('完整观看并听取','完整观看但声音无法判断'),
         'relation':('保留具体叙事关系','仅表层或通用结构相似','未发现对应关系','无法判断')}


def packet_labels(packet):
    require(isinstance(packet,dict) and packet.get('schema')=='visualagent.reference-plan-review-packet.v1','invalid_packet')
    require(packet.get('training_eligible') is False,'packet_training_ineligible_required')
    require(isinstance(packet.get('form_template_sha256'),str) and re.fullmatch('[a-f0-9]{64}',packet['form_template_sha256']),'invalid_form_digest')
    result=[]
    for key,prefix in [('plans','P'),('sources','V')]:
        rows=packet.get(key);require(isinstance(rows,list) and bool(rows),'empty_packet_section')
        labels=[]
        for row in rows:
            require(isinstance(row,dict) and isinstance(row.get('label'),str) and re.fullmatch(prefix+'[0-9]+',row['label']),'invalid_packet_label')
            labels.append(row['label'])
        require(len(labels)==len(set(labels)),'duplicate_packet_label');result.append(labels)
    return result


def validate(packet,review):
    plans,sources=packet_labels(packet)
    require(fields(review,'schema packet_sha256 reviewer_code stage1_locked stage1 stage2 review_status independence_status training_eligible'),'invalid_review_fields')
    require(review['schema']=='visualagent.reference-plan-review.v1','invalid_review_schema')
    require(review['packet_sha256']==digest(packet),'packet_digest_mismatch')
    require(review['review_status']=='submitted_unverified','submitted_review_required')
    require(review['training_eligible'] is False,'training_ineligible_required')
    require(review['independence_status']=='not_verified','independence_not_verified_required')
    require(review['stage1_locked'] is True,'stage1_not_locked')
    require(isinstance(review['reviewer_code'],str) and re.fullmatch('[A-Za-z0-9_-]{1,40}',review['reviewer_code']),'invalid_reviewer_code')
    expected1={p+'_'+k for p in plans for k in ('violation','goal','utility','evidence')}
    expected2={v+'_view' for v in sources}|{p+'_'+v+'_'+k for p in plans for v in sources for k in ('relation','evidence')}
    for stage,expected in [('stage1',expected1),('stage2',expected2)]:
        data=review[stage];require(isinstance(data,dict) and set(data)==expected,'rating_coverage_mismatch')
        for key,value in data.items():
            kind=key.rsplit('_',1)[1]
            if kind=='evidence':require(text(value),'missing_evidence')
            else:require(isinstance(value,str) and value in CHOICES[kind],'invalid_rating')
    return review


def summarize(packet,reviews):
    packet_labels(packet);unique={};by_code={};duplicate=0
    for review in reviews:
        r=validate(packet,review);sha=digest(r)
        if sha in unique:duplicate+=1;continue
        unique[sha]=r;by_code.setdefault(r['reviewer_code'],[]).append(r)
    # Do not let multiple revisions cast multiple votes or pick a revision by timestamp.
    eligible=[rs[0] for rs in by_code.values() if len(rs)==1]
    counts={}
    for stage in ('stage1','stage2'):
        counts[stage]={}
        for r in eligible:
            for key,value in r[stage].items():
                if not key.endswith('_evidence'):counts[stage].setdefault(key,Counter())[value]+=1
        counts[stage]={key:dict(value) for key,value in counts[stage].items()}
    return {'schema':'visualagent.reference-plan-intake-summary.v1','packet_sha256':digest(packet),
        'unique_submissions':len(unique),'duplicate_submissions':duplicate,'declared_reviewer_codes':len(by_code),
        'reviewer_codes_with_conflicting_versions':sum(len(rs)>1 for rs in by_code.values()),
        'unconflicted_submissions_in_counts':len(eligible),'rating_counts':counts,
        'independent_reviews_completed':0,'independence_status':'not_verified','training_eligible':False,
        'semantic_effect':None,'limitations':['Lock flag is a declaration, not proof of viewing order.',
            'Unknown ratings remain a separate category; no automatic zero or average imputation.',
            'Distinct codes do not establish reviewer independence.',
            'Revision conflicts are excluded from counts until explicitly resolved.',
            'Counts of supplied reviews are not an external-inbox scan or adjudicated gold.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--reviews',type=Path,nargs='*',default=[]);a=p.parse_args()
    try:r=summarize(json.loads(a.packet.read_text()),[json.loads(x.read_text()) for x in a.reviews])
    except (ValueError,TypeError,KeyError) as e:
        code=str(e) if type(e) is ValueError and re.fullmatch('[a-z_]+',str(e)) else 'malformed_input'
        print(json.dumps({'state':'rejected','code':code}));sys.exit(1)
    print(json.dumps(r,ensure_ascii=False,indent=2))
