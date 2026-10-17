#!/usr/bin/env python3
"""Create private preference-pair candidates; never publish training data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.learning.preferences import build_pairs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--min-gap', type=float, default=0.5)
    args=parser.parse_args()
    if args.queue.is_symlink() or not args.queue.is_file():raise ValueError('Invalid candidate queue')
    queue=json.loads(args.queue.read_text(encoding='utf-8'))
    if queue.get('schema')!='visualagent.training-candidate-queue.v1':raise ValueError('Unsupported candidate queue')
    pairs=build_pairs(queue.get('records',[]),args.min_gap)
    payload={'schema':'visualagent.preference-pair-candidate-queue.v1',
             'source_queue_sha256':hashlib.sha256(args.queue.read_bytes()).hexdigest(),
             'record_count':len(pairs),'training_eligible':False,'content_exported':False,
             'review_policy':'Preference pairs require an independent exact-content review before release.',
             'pairs':pairs}
    if args.output.exists() or args.output.is_symlink():raise FileExistsError('Refusing to overwrite preference queue')
    args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(payload,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'record_count':len(pairs),'training_eligible':False},ensure_ascii=False))


if __name__=='__main__':main()
