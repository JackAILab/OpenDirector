#!/usr/bin/env python3
"""Freeze a private, read-only reference shortlist. Selection never approves labels."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library.store import ROOT


def read(path):
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
    return c


def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def duration_bin(t):
    return 'under_15' if t<15 else '15_to_30' if t<=30 else '30_to_60' if t<=60 else 'over_60'


def select(rows, per_bin=6, seed='paper-reference-pilot-v1'):
    if type(per_bin) is not int or not 1<=per_bin<=20:raise ValueError('invalid quota')
    bins={key:[] for key in ('under_15','15_to_30','30_to_60','over_60')}
    seen=set()
    for row in sorted(rows,key=lambda r:(r['sha256'],r['item'])):
        t=row['duration']
        if row['sha256'] in seen or not isinstance(t,(int,float)) or isinstance(t,bool) or not math.isfinite(t) or t<=0:continue
        seen.add(row['sha256']);bins[duration_bin(t)].append(row)
    chosen=[]
    for key,group in bins.items():
        order=sorted(group,key=lambda r:hashlib.sha256((seed+r['sha256']).encode()).hexdigest())
        chosen.extend({**r,'duration_stratum':key} for r in order[:per_bin])
    return chosen,{k:len(v) for k,v in bins.items()}


def build(root,out,per_bin,seed):
    with read(root/'library.sqlite3') as c:
        assets={r[0]:{'item':r[0],'sha256':r[1],'duration':r[2],'has_audio_stream':bool(r[3]),'width':r[4],'height':r[5]} for r in c.execute('select item,sha256,duration,audio,width,height from assets')}
    with read(root/'learning'/'analyses.sqlite3') as c:
        rows=c.execute('select item,media_sha256,version,data from analyses order by item,version desc').fetchall()
    eligible=[];seen=set();rejected=Counter()
    for item,sha,version,raw in rows:
        if item in seen or assets.get(item,{}).get('sha256')!=sha:continue
        seen.add(item)
        try:analysis=json.loads(raw)
        except (ValueError,TypeError):rejected['malformed_analysis']+=1;continue
        if not isinstance(analysis,dict) or analysis.get('media_role')!='original_ad':rejected['not_machine_classified_original_ad']+=1;continue
        eligible.append({**assets[item],'analysis_version':version,'analysis_sha256':digest(analysis)})
    chosen,coverage=select(eligible,per_bin,seed)
    out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    # Blinded packets omit source title, brand labels, model captions and mechanism suggestions.
    packets=[]
    for i,row in enumerate(chosen):
        packets.append({'review_id':f'R{i+1:03d}','duration_seconds':row['duration'],
            'declared_has_audio_stream':row['has_audio_stream'],
            'review_status':'pending','fully_watched':False,'fully_listened':False,
            'observed_events':[],'audio_events':[],'temporal_links':[],
            'mechanism_interpretations':[],'uncertainties':[],
            'independent_reviewer':None,'training_eligible':False})
    private={'schema':'visualagent.reference-review-selection.v1','seed':seed,
             'selected':[{'review_id':f'R{i+1:03d}',**r} for i,r in enumerate(chosen)],
             'selection_note':'Machine-classified original ads only; role must be independently checked.'}
    summary={'schema':'visualagent.reference-review-selection-summary.v1','observed_at_utc':datetime.now(timezone.utc).isoformat(),
        'eligible_analysis_records':len(eligible),'unique_candidates_by_duration':coverage,
        'selected_count':len(chosen),'target_count':per_bin*4,'selected_duration_strata':dict(Counter(r['duration_stratum'] for r in chosen)),
        'selected_with_audio_stream':sum(r['has_audio_stream'] for r in chosen),
        'selected_portrait':sum(r['height']>r['width'] for r in chosen),
        'rejected_analysis_roles_or_format':dict(rejected),'selection_sha256':digest(private),
        'independent_reviews_completed':0,'gold_ready':False,'training_eligible':False,
        'limitations':['SHA dedup only; campaign and re-encode relationships still need review.',
            'Duration strata are balanced deliberately and not population-representative.',
            'Source and semantic mechanism coverage have not been balanced.',
            'Separate SQLite reads are not a globally atomic snapshot.',
            'Selection binds stored media hashes; bytes must be verified when opening review media.']}
    for name,value in [('selection.json',private),('blind-review-forms.json',packets),('summary.json',summary)]:
        with (out/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--per-bin',type=int,default=6)
    p.add_argument('--seed',default='paper-reference-pilot-v1');a=p.parse_args()
    print(json.dumps(build(a.root,a.out,a.per_bin,a.seed),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
