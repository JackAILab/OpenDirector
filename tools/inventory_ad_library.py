#!/usr/bin/env python3
"""Non-overwriting corpus inventory; counts never masquerade as creative review."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library import store


def inventory():
    with store.connection() as c:
        c.execute('BEGIN')
        rows=[dict(r) for r in c.execute('SELECT i.*,a.sha256,a.bytes,a.duration,a.audio FROM items i LEFT JOIN assets a ON a.item=i.id')]
        reviews=c.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
        media_bytes=store.registered_media_bytes(c)
    durations=[r['duration'] for r in rows if r['duration']]
    digests=defaultdict(list)
    for r in rows:
        r['metadata']=json.loads(r['data'])
        if r['sha256']:digests[r['sha256']].append(r['id'])
    count=lambda key:dict(Counter(r[key] or 'unknown' for r in rows))
    return {'schema':'visualagent.library-inventory.v1','created_at':time.time(),
        'total':len(rows),'playable':len(durations),'audio_tracks':sum(bool(r['audio']) for r in rows),
        'industry':count('industry'),'ad_type':count('ad_type'),
        'source':dict(Counter(r['metadata'].get('source_name','unknown') for r in rows)),
        'years':dict(Counter(r['metadata'].get('published','unknown') for r in rows)),
        'duration_bands':dict(Counter('<=30s' if d<=30 else '30-60s' if d<=60 else '60-180s' if d<=180 else '>180s' for d in durations)),
        'duration_median':statistics.median(durations) if durations else None,
        'unique_media_hashes':len(digests),'exact_duplicate_groups':[ids for ids in digests.values() if len(ids)>1],
        'media_bytes':media_bytes,'blank_brand':sum(not r['brand'] for r in rows),
        'human_review_rows':reviews,'training_eligible':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    data=inventory();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps({'total':data['total'],'playable':data['playable'],'output':str(args.output)}))
