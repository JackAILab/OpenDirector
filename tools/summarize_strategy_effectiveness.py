#!/usr/bin/env python3
"""Write a private strategy retrieval/adoption aggregate; never publish training data."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.strategy_effectiveness import summarize


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--queue',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.queue.is_symlink() or not args.queue.is_file():raise ValueError('Invalid candidate queue')
    queue=json.loads(args.queue.read_text(encoding='utf-8'))
    if queue.get('schema')!='visualagent.training-candidate-queue.v1':raise ValueError('Unsupported candidate queue')
    result=summarize(queue.get('records',[]));result['source_queue_sha256']=__import__('hashlib').sha256(args.queue.read_bytes()).hexdigest()
    if args.output.exists() or args.output.is_symlink():raise FileExistsError('Refusing to overwrite effectiveness report')
    args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'observed_records':result['observed_records'],'strategy_count':len(result['strategies'])},ensure_ascii=False))


if __name__=='__main__':main()
