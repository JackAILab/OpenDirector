"""Exact-content review receipts for sanitized director candidate queues."""
import hashlib
import json

GATES=('privacy_review','rights_review','sanitized_context_review')
EXPECTED_PROVENANCE={
    'plan':'actual_agent_plan_snapshot',
    'strategy_context':'external_reference_strategy_observation',
    'trajectory':'actual_agent_observed_events',
    'policy':'reference observations and user episodes must never be mixed as supervision',
}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def queue_digest(queue):
    if queue.get('schema')!='visualagent.training-candidate-queue.v1':raise ValueError('Unsupported candidate queue')
    return digest({'schema':queue['schema'],'source_manifest_sha256':queue.get('source_manifest_sha256'),
                   'salt_sha256':queue.get('salt_sha256'),
                   'records':queue.get('records',[])})


def validate_receipt_shape(queue, receipt):
    """Validate one receipt's binding without deciding whether it passes."""
    if not isinstance(receipt, dict) or receipt.get('schema') != 'visualagent.training-candidate-review.v1':
        raise ValueError('Unsupported candidate review receipt')
    expected_queue = queue_digest(queue)
    if receipt.get('queue_sha256') != expected_queue:
        raise ValueError('Candidate review queue binding failed')
    candidate = next((r for r in queue.get('records', [])
                      if r.get('record_sha256') == receipt.get('candidate_sha256')), None)
    if not candidate:
        raise ValueError('Candidate review references an unknown candidate')
    if receipt.get('independent') is not True:
        raise ValueError('Candidate review must be independent')
    if set(receipt.get('decisions', {})) != set(GATES) or any(
            type(receipt.get('decisions', {}).get(g)) is not bool for g in GATES):
        raise ValueError('Candidate review gates are incomplete')
    if receipt.get('receipt_sha256') != digest({k: v for k, v in receipt.items() if k != 'receipt_sha256'}):
        raise ValueError('Candidate review receipt integrity failed')
    return candidate


def make_receipt(queue,candidate_id,reviewer_id,decisions,note,independent=True,reviewer_token=None):
    if not isinstance(reviewer_id,str) or not reviewer_id.strip():raise ValueError('Independent reviewer is required')
    if independent is not True:raise ValueError('Exact-content review must be independent')
    if set(decisions)!=set(GATES) or any(type(v) is not bool for v in decisions.values()):raise ValueError('All candidate gates are required')
    note=str(note or '').strip()
    if len(note)<10 or len(note)>1000:raise ValueError('Review note must be 10–1000 characters')
    record=next((r for r in queue.get('records',[]) if r.get('sample_id')==candidate_id),None)
    if not record:raise ValueError('Candidate not found')
    creator_token=record.get('creator_token')
    if creator_token and not reviewer_token:
        raise ValueError('Reviewer pseudonym is required')
    if creator_token and creator_token==reviewer_token:
        raise ValueError('Creator cannot review own candidate')
    payload={'schema':'visualagent.training-candidate-review.v1','queue_sha256':queue_digest(queue),
             'candidate_sha256':record.get('record_sha256'),'reviewer_id_sha256':hashlib.sha256(reviewer_id.encode()).hexdigest(),
             'independent':True,'decisions':dict(decisions),'note':note,'training_eligible':False}
    payload['receipt_sha256']=digest(payload)
    return payload


def validate_release(queue,receipts):
    """Return exact reviewed candidates; never changes the source queue."""
    expected=queue_digest(queue);by_id={r.get('sample_id'):r for r in queue.get('records',[])}
    receipts_by_id={r.get('candidate_sha256'):r for r in receipts}
    if not by_id:raise ValueError('Candidate queue is empty')
    output=[]
    for record in by_id.values():
        if record.get('provenance')!=EXPECTED_PROVENANCE:
            raise ValueError('Missing provenance separation')
        receipt=receipts_by_id.get(record.get('record_sha256'))
        if not receipt:
            raise ValueError('Missing exact-content review receipt')
        try:
            validate_receipt_shape(queue, receipt)
        except ValueError as exc:
            # Preserve the release gate's stable, non-specific failure class;
            # detailed binding errors remain available to the merge utility.
            raise ValueError('Missing exact-content review receipt') from exc
        if any(receipt.get('decisions',{}).get(g) is not True for g in GATES):
            raise ValueError('Candidate review gate failed')
        if receipt.get('receipt_sha256')!=digest({k:v for k,v in receipt.items() if k!='receipt_sha256'}):
            raise ValueError('Candidate review receipt integrity failed')
        promoted=dict(record,training_eligible=True,public_release=True,review_status='exact_content_reviewed')
        promoted.pop('creator_token',None)
        promoted.pop('limitations',None)
        promoted['record_sha256']=digest(promoted)
        output.append(promoted)
    return sorted(output,key=lambda r:r['sample_id'])
