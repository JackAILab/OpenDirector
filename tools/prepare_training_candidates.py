#!/usr/bin/env python3
"""Create a private exact-content review queue; never publish training data."""
import argparse,hashlib,json,os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.inventory import input_fingerprints
from harness.learning.training_records import collect_candidates

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--salt-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.manifest.is_symlink() or not a.manifest.is_file():raise ValueError('Invalid manifest')
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'))
    if manifest.get('schema')!='visualagent.private-dataset-preparation.v1':raise ValueError('Unsupported manifest')
    if manifest.get('input_fingerprints') and manifest['input_fingerprints']!=input_fingerprints():raise ValueError('Manifest inputs changed; regenerate preparation manifest')
    records=collect_candidates(manifest,a.salt_file)
    payload={'schema':'visualagent.training-candidate-queue.v1','source_manifest_sha256':hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
             'record_count':len(records),'training_eligible':False,'content_exported':False,
             'salt_sha256':hashlib.sha256(a.salt_file.read_bytes()).hexdigest(),
             'review_policy':'Every record requires exact-content privacy/rights/sanitization review before release.','records':records}
    if a.output.exists() or a.output.is_symlink():raise FileExistsError('Refusing to overwrite candidate queue')
    a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(payload,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'record_count':len(records),'training_eligible':False},ensure_ascii=False))
if __name__=='__main__':main()
