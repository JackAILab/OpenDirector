"""Read-only boundary from Captioner machine observations into research evidence.

No paths, endpoints, provider payloads, inherited approvals or semantic verdict promotion.
"""
import math
import re
from harness.research.briefs import digest
from harness.tools.research_plan import bounded_text


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def convert(task,observations,reference_id):
    evidence=task['evidence'];offset=evidence['start'];duration=evidence['duration']
    if not finite(offset) or offset<0 or not finite(duration) or duration<=0:raise ValueError('invalid_evidence_window')
    if not finite(evidence['end']) or abs(evidence['end']-offset-duration)>.001:raise ValueError('inconsistent_evidence_window')
    items=list(evidence.get('frames',[]))+[evidence[k] for k in ('audio','video') if evidence.get(k)]
    if not isinstance(task.get('asset_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',task['asset_sha256']):raise ValueError('invalid_media_digest')
    if any(not isinstance(item.get('id'),str) or not re.fullmatch(r'[fav][0-9]+',item['id']) for item in items):raise ValueError('invalid_evidence_id')
    namespace=digest({'task':task['id'],'asset':task['asset_sha256'],'start':offset,'duration':duration,
        'items':[{k:item[k] for k in ('id','sha256','time','source_time') if k in item} for item in items]})[:20]
    ids={item['id']:item for item in items}
    if len(ids)!=len(items):raise ValueError('ambiguous_evidence_id')
    proof=[]
    for key,item in ids.items():
        if not isinstance(item.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):raise ValueError('invalid_evidence_digest')
        row={'evidence_id':f'{reference_id}:{namespace}:{key}','sha256':bounded_text(item.get('sha256'),64)}
        if key.startswith('f'):
            if not finite(item.get('time')) or not finite(item.get('source_time')) or abs(offset+item['time']-item['source_time'])>.001:
                raise ValueError('frame_time_mismatch')
            row.update(kind='sampled_frame',source_time=item['source_time'],timestamp_kind='requested_nearest_decoded_frame')
        else:row.update(kind='audio_window' if key.startswith('a') else 'video_window',start=offset,end=offset+duration)
        proof.append(row)
    events=[];coverage={};observer_warnings={}
    for role,allowed in [('vision',{'visual'}),('audio',{'audio'}),('omni',{'visual','audio','audiovisual'})]:
        if role not in observations:continue
        observation=observations[role];coverage[role]=len(observation.get('claims',[]))
        gaps=[]
        for gap in observation.get('uncertainties',[]):
            a,b=gap['start'],gap['end']
            if not finite(a) or not finite(b) or not 0<=a<b<=duration+.1:raise ValueError('invalid_uncertainty_window')
            gaps.append({'start':offset+a,'end':offset+b,'reason':bounded_text(gap['reason'],4000)})
        observer_warnings[role]={'generation_truncated':bool(observation.get('generation_truncated')),
            'format_repair_present':bool(observation.get('format_repair')),'uncertainties':gaps}
        for index,claim in enumerate(observation.get('claims',[])):
            start,end=claim['start'],claim['end'];modality=claim['modality'];refs=claim['evidence_ids']
            if not finite(start) or not finite(end) or not 0<=start<=end<=duration+.1:raise ValueError('invalid_claim_window')
            if modality not in allowed or not isinstance(refs,list) or not refs or any(r not in ids for r in refs):raise ValueError('invalid_claim_evidence')
            visual=any(r.startswith(('f','v')) for r in refs);audio=any(r.startswith('a') for r in refs)
            if (modality=='visual' and not visual) or (modality=='audio' and not audio) or (modality=='audiovisual' and not (visual and audio)):
                raise ValueError('modality_evidence_mismatch')
            events.append({'event_id':f'{reference_id}:{namespace}:{role}:C{index:03d}',
                'start':offset+start,'end':offset+end,'modality':modality,'observer_role':role,
                'observation':bounded_text(claim['text'],4000),
                'evidence_ids':[f'{reference_id}:{namespace}:{r}' for r in refs],
                'status':'machine_observation_unverified'})
    if not events:raise ValueError('missing_claims')
    return {'reference_id':reference_id,'schema':'visualagent.captioner-reference.v1',
        'media_sha256':task['asset_sha256'],'evidence':{'events':events,'items':proof,
        'scope':'single_clip_multimodal_machine_observations','source_window':{'start':offset,'end':offset+duration},
        'available_observer_claim_counts':coverage,'observer_warnings':observer_warnings,'audio_semantics_reviewed':False,'full_motion_reviewed':False,
        'independent_review':'pending','nominal_boundary_tolerance_seconds':.1},
        'interpretation':{'status':'not_extracted','principle':'','mechanism':'','transfer_rules':[], 'contraindications':[]},
        'training_eligible':False}
