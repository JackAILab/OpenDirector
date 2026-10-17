"""Fail-closed release gate for sanitized learning data."""
import hashlib
import json
import os
from pathlib import Path

REQUIRED=('training_consent','artifact_bound_human_approval','independent_quality_review',
          'privacy_review','rights_review','sanitized_context_review')


def _reserve(path):
    path=Path(path)
    if path.exists() or path.is_symlink():raise FileExistsError('Refusing to overwrite release report')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    return path,fd


def release(manifest_path,output_path):
    """Write an immutable release receipt only when every record is eligible.

    This does not copy user media or raw conversations. At present normal operation
    should return ``not_ready`` because release curation is intentionally manual.
    """
    manifest_path=Path(manifest_path).resolve()
    if not manifest_path.is_file() or manifest_path.is_symlink():raise ValueError('Invalid preparation manifest')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema')!='visualagent.private-dataset-preparation.v1':raise ValueError('Unsupported manifest')
    records=manifest.get('records',[])
    blockers={}
    saved_fingerprints=manifest.get('input_fingerprints')
    if saved_fingerprints:
        from harness.learning.inventory import input_fingerprints
        if saved_fingerprints!=input_fingerprints():blockers['manifest']=['stale_input_fingerprints']
    eligible=[]
    for record in records:
        missing=set(record.get('missing_evidence',[]))
        if record.get('training_eligible') is not True:missing.add('training_eligible_false')
        if record.get('public_dataset_consent') is not True:missing.add('public_dataset_consent')
        if missing:blockers[record.get('sample_id','unknown')]=sorted(missing)
        else:eligible.append(record)
    if not records:blockers.setdefault('manifest',[]).append('empty_manifest')
    state='ready' if not blockers and manifest.get('summary',{}).get('release_ready') is True else 'not_ready'
    payload={'schema':'visualagent.learning-release-receipt.v1','state':state,
        'preparation_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'record_count':len(records),'eligible_count':len(eligible),'training_records':[],
        'content_exported':False,'blockers':blockers,
        'policy':'No release unless explicit consent, independent review, privacy/rights review, sanitized context review, artifact binding and family split are all present.'}
    path,fd=_reserve(output_path)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            fd=None;json.dump(payload,f,ensure_ascii=False,indent=2);f.write('\n')
    finally:
        if fd is not None:os.close(fd)
    return payload
