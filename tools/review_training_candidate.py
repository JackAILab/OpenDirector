#!/usr/bin/env python3
"""Record one exact-content review receipt without changing the candidate queue."""
import argparse,json,os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.candidate_review import make_receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('--queue',type=Path,required=True);p.add_argument('--candidate',required=True);p.add_argument('--reviewer-id',required=True);p.add_argument('--reviewer-token',required=True);p.add_argument('--note',required=True);p.add_argument('--privacy',action='store_true');p.add_argument('--rights',action='store_true');p.add_argument('--sanitized-context',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    queue=json.loads(a.queue.read_text(encoding='utf-8'))
    decisions={'privacy_review':a.privacy,'rights_review':a.rights,'sanitized_context_review':a.sanitized_context}
    receipt=make_receipt(queue,a.candidate,a.reviewer_id,decisions,a.note,reviewer_token=a.reviewer_token)
    if a.output.exists() or a.output.is_symlink():raise FileExistsError('Refusing to overwrite review receipt')
    a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(receipt,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'candidate':a.candidate,'receipt_sha256':receipt['receipt_sha256']},ensure_ascii=False))
if __name__=='__main__':main()
