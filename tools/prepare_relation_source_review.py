#!/usr/bin/env python3
"""Build an offline source-only review packet with verified local media copies."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from tools.prepare_paper_reference_review import read
from tools.prepare_relation_candidates import active_pairs


def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def media_duration(path, ffprobe):
    result=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration',
                           '-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True)
    duration=float(json.loads(result.stdout)['format']['duration'])
    if not math.isfinite(duration) or duration<=0:raise ValueError('invalid_media_duration')
    return duration


def build(root,selection,candidates,out,seed=53,ffprobe="ffprobe"):
    frozen=json.loads(selection.read_text()); config=json.loads(candidates.read_text())
    ids={p[k] for p in active_pairs(config) for k in ('candidate_reference','contrast_reference')}
    rows=[r for r in frozen['selected'] if r['review_id'] in ids]
    if len(rows)!=len(ids):raise ValueError('missing_or_duplicate_reference')
    random.Random(seed).shuffle(rows)
    sources=[]
    with read(root/'library.sqlite3') as c:
        for row in rows:
            match=c.execute('select path,sha256 from assets where item=?',(row['item'],)).fetchone()
            if not match or match[1]!=row['sha256']:raise ValueError('asset_binding_mismatch')
            path=(root/match[0]).resolve()
            if not path.is_relative_to(root.resolve()):raise ValueError('asset_outside_root')
            if file_hash(path)!=row['sha256']:raise ValueError('media_bytes_mismatch')
            sources.append((path,media_duration(path,ffprobe)))
    out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    clips=[];mapping={}
    for i,(row,(path,duration)) in enumerate(zip(rows,sources),1):
        label=f'S{i:02d}';name=label+'.mp4';shutil.copyfile(path,out/name)
        if file_hash(out/name)!=row['sha256']:raise ValueError('copied_media_mismatch')
        clips.append({'label':label,'media':name,'sha256':row['sha256'],
                      'duration':duration,'stored_duration':row['duration'],
                      'has_audio_stream':row['has_audio_stream']})
        mapping[label]=row['review_id']
    packet={'schema':'visualagent.source-relation-packet.v1','clips':clips,
            'training_eligible':False,'scope':'source_annotation_only_not_target_transfer_evaluation'}
    for name,data in [('packet.json',packet),('private-mapping.json',{'mapping':mapping,'seed':seed,
        'selection_sha256':digest(frozen),'candidate_sha256':digest(config)})]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    template=Path(__file__).with_name('relation_source_review.html').read_text()
    payload=json.dumps({'packet':packet,'packet_sha256':digest(packet)},ensure_ascii=False).replace('<','\\u003c')
    (out/'review.html').write_text(template.replace('__PACKET_DATA__',payload))
    return {'packet_sha256':digest(packet),'clip_count':len(clips),'media_bytes_verified':True,
            'independent_reviews_completed':0,'training_eligible':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','selection','candidates','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seed',type=int,default=53);p.add_argument('--ffprobe',default='ffprobe');a=p.parse_args()
    print(json.dumps(build(a.root,a.selection,a.candidates,a.out,a.seed,a.ffprobe)))
