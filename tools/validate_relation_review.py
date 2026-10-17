#!/usr/bin/env python3
"""Validate submitted source annotations; never certify semantics or independence."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest


def require(condition, code):
    if not condition:raise ValueError(code)


def number(x):
    return type(x) in (int,float) and math.isfinite(x)


def text(x):
    return isinstance(x,str) and bool(x.strip()) and len(x)<=12000


def fields(x,keys):
    return isinstance(x,dict) and set(x)==set(keys.split())


def validate_packet(packet):
    require(isinstance(packet,dict) and packet.get('schema')=='visualagent.source-relation-packet.v1','invalid_packet')
    require(packet.get('training_eligible') is False,'packet_training_ineligible_required')
    clips=packet.get('clips')
    require(isinstance(clips,list) and bool(clips),'invalid_packet_clips')
    labels={}
    for c in clips:
        require(isinstance(c,dict) and isinstance(c.get('label'),str),'invalid_packet_label')
        require(c['label'] not in labels,'duplicate_packet_label')
        require(number(c.get('duration')) and c['duration']>0,'invalid_packet_duration')
        require(isinstance(c.get('sha256'),str) and re.fullmatch('[a-f0-9]{64}',c['sha256']),'invalid_media_digest')
        labels[c['label']]=c
    return labels


def validate(packet,review):
    labels=validate_packet(packet)
    require(fields(review,'schema packet_sha256 reviewer_code review_status independence_status training_eligible clips'),'invalid_review_fields')
    require(review['schema']=='visualagent.source-relation-review.v1','invalid_review_schema')
    require(review['packet_sha256']==digest(packet),'packet_digest_mismatch')
    require(review['training_eligible'] is False,'training_ineligible_required')
    require(review['independence_status']=='not_verified','independence_not_verified_required')
    require(review['review_status']=='submitted_unverified','submitted_review_required')
    require(isinstance(review['reviewer_code'],str) and re.fullmatch('[A-Za-z0-9_-]{1,40}',review['reviewer_code']),'invalid_reviewer_code')
    rows=review['clips'];require(isinstance(rows,list) and len(rows)==len(labels),'clip_coverage_mismatch')
    seen=set()
    for r in rows:
        require(fields(r,'label watched audio role goal uncertainty events relations'),'invalid_clip_fields')
        require(isinstance(r['label'],str) and r['label'] in labels and r['label'] not in seen,'clip_label_mismatch')
        seen.add(r['label']);duration=labels[r['label']]['duration']
        require(r['watched'] is True,'watch_confirmation_required')
        require(r['audio'] in ('已完整听过','播放无声','无法播放声音'),'invalid_audio_status')
        require(r['role'] in ('原始广告','案例解说','混合内容','无法判断'),'invalid_source_role')
        require(text(r['goal']) and text(r['uncertainty']),'missing_overall_annotations')
        require(isinstance(r['events'],list) and 1<=len(r['events'])<=200,'invalid_events')
        ids=set()
        for e in r['events']:
            require(fields(e,'id start end modality observation'),'invalid_event_fields')
            require(isinstance(e['id'],str) and re.fullmatch('E[1-9][0-9]*',e['id']) and e['id'] not in ids,'invalid_event_id')
            ids.add(e['id'])
            require(number(e['start']) and number(e['end']) and 0<=e['start']<e['end']<=duration+0.25,'invalid_event_time')
            require(e['modality'] in ('视觉','声音','视听共同') and text(e['observation']),'invalid_event_evidence')
            require(e['modality']=='视觉' or r['audio']=='已完整听过','audio_evidence_without_listening')
        require(isinstance(r['relations'],list) and len(r['relations'])<=200,'invalid_relations')
        for rel in r['relations']:
            require(fields(rel,'events kind interpretation support alternatives'),'invalid_relation_fields')
            es=rel['events']
            require(isinstance(es,list) and bool(es) and all(isinstance(e,str) and e in ids for e in es),'invalid_relation_event_link')
            require(len(set(es))==len(es),'duplicate_relation_event_link')
            require(rel['kind'] in ('时间先后','人物反应','叙事归因','能力主张','其他'),'invalid_relation_kind')
            require(rel['support'] in ('直接观察','有依据的解释','无法确定'),'invalid_relation_support')
            require(text(rel['interpretation']) and text(rel['alternatives']),'missing_relation_explanation')
    return review


def summarize(packet,reviews):
    validate_packet(packet)
    unique={};duplicates=0;by_reviewer={}
    for review in reviews:
        r=validate(packet,review);sha=digest(r)
        if sha in unique:duplicates+=1;continue
        unique[sha]=r;by_reviewer.setdefault(r['reviewer_code'],[]).append(r)
    conflicts=sum(len(rs)>1 for rs in by_reviewer.values())
    # A revised export is not a second reviewer. Keep conflicts unresolved.
    rows=[]
    for clip in packet['clips']:
        rs=[next(c for c in r['clips'] if c['label']==clip['label']) for r in unique.values()]
        rows.append({'label':clip['label'],'source_role_counts':dict(Counter(r['role'] for r in rs)),
            'audio_status_counts':dict(Counter(r['audio'] for r in rs)),
            'event_counts':sorted(len(r['events']) for r in rs),
            'relation_counts':sorted(len(r['relations']) for r in rs),
            'needs_semantic_alignment':len(rs)>1})
    return {'schema':'visualagent.source-review-intake-summary.v1','packet_sha256':digest(packet),
        'valid_unique_submissions':len(unique),'duplicate_submissions':duplicates,
        'declared_reviewer_codes':len(by_reviewer),'reviewer_codes_with_conflicting_versions':conflicts,
        'independent_reviews_completed':0,'independence_status':'not_verified',
        'semantic_agreement':None,'clips':rows,'training_eligible':False,
        'limitations':['Distinct anonymous codes do not verify distinct independent people.',
            'Event IDs are local to each review; matching IDs do not establish semantic alignment.',
            'Counts are intake diagnostics, not inter-rater agreement or approved labels.',
            'Conflicting versions require explicit selection; no latest-file heuristic is applied.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--reviews',type=Path,nargs='*',default=[]);a=p.parse_args()
    try:
        result=summarize(json.loads(a.packet.read_text()),[json.loads(p.read_text()) for p in a.reviews])
    except (ValueError,TypeError,KeyError) as e:
        # Only locally generated validation codes are exposed, never file contents.
        if type(e) is ValueError and re.fullmatch('[a-z_]+',str(e)):code=str(e)
        else:code='malformed_input'
        print(json.dumps({'state':'rejected','code':code}));sys.exit(1)
    print(json.dumps(result,ensure_ascii=False,indent=2))
