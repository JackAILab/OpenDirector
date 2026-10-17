#!/usr/bin/env python3
"""Promote exact-reviewed private candidates; requires an explicit confirmation."""
import argparse,json,os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.candidate_review import validate_release

def main():
    p=argparse.ArgumentParser();p.add_argument('--queue',type=Path,required=True);p.add_argument('--reviews',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--confirm-release',action='store_true');a=p.parse_args()
    if not a.confirm_release:raise ValueError('Pass --confirm-release only after reviewing every candidate')
    queue=json.loads(a.queue.read_text(encoding='utf-8'));reviews=json.loads(a.reviews.read_text(encoding='utf-8'))
    if isinstance(reviews,dict):reviews=reviews.get('receipts',[reviews] if reviews.get('schema')=='visualagent.training-candidate-review.v1' else [])
    records=validate_release(queue,reviews)
    payload={'schema':'visualagent.training-release.v1','record_count':len(records),'training_eligible':True,'content_exported':True,'records':records}
    if a.output.exists() or a.output.is_symlink():raise FileExistsError('Refusing to overwrite training release')
    a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(payload,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'record_count':len(records),'training_eligible':True},ensure_ascii=False))
if __name__=='__main__':main()
