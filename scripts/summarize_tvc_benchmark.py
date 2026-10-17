#!/usr/bin/env python3
"""Summarize persisted evidence; never promote unknown review results to passed."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bundle = ROOT/'productions/omni_tvc_benchmark_10_v1'
outputs = ROOT/'outputs/artifacts/omni_tvc_benchmark_10_v1'


def read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


cases = []
for path in sorted(bundle.glob('cases/*/input.json')):
    spec = read(path)
    folder = outputs/spec['case_id']
    receipt = read(folder/'omni-attempt-01.receipt.json')
    reservation = read(folder/'attempt-01.reservation.json')
    technical = read(folder/'media-review/technical.json')
    semantic = read(folder/'media-review/semantic.json')
    elapsed = None
    if receipt and reservation:
        elapsed = round((datetime.fromisoformat(receipt['created_at'])-datetime.fromisoformat(reservation['created_at'])).total_seconds(),1)
    cases.append({'case_id':spec['case_id'],'title':spec['title'],'reference_ready':bool(spec['references']),'reference_attempts':spec['reference_generation'].get('attempts_used',0),'video_attempted':bool(reservation),'video_submitted':(folder/'omni-attempt-01.submission.json').is_file() or bool(receipt),'video_ready':bool(receipt) and (folder/'omni-attempt-01.mp4').is_file(),'elapsed_seconds':elapsed,'credits_consumed':receipt.get('credits_consumed'),'technical_passed':technical.get('technical_passed'),'semantic_verdict':semantic.get('verdict','pending'),'perceptual_audio_review':semantic.get('perceptual_audio_review',semantic.get('audio',{}).get('perceptual_sync','not_verified')),'findings':semantic.get('findings',[]),'training_eligible':False})
summary = {'schema':'visualagent.tvc-benchmark-delivery.v1','updated_at':datetime.now(timezone.utc).isoformat(),'required_videos':10,'videos_ready':sum(c['video_ready'] for c in cases),'reference_images_ready':sum(c['reference_ready'] for c in cases),'semantic_reviews_recorded':sum(c['semantic_verdict']!='pending' for c in cases),'cases':cases,'training_eligible':False}
summary['video_credits_reported'] = sum(c['credits_consumed'] for c in cases if isinstance(c['credits_consumed'], (int,float)))
summary['video_receipts_without_credit_value'] = sum(c['video_ready'] and c['credits_consumed'] is None for c in cases)
blocker = read(bundle/'generation-blocker.json')
if blocker and not blocker.get('resolved_at'):
    summary['blocker'] = blocker
(bundle/'delivery-status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
batch = read(bundle/'benchmark.json')
batch['budget']['codebuddy_attempts_used'] = sum(c['reference_attempts'] for c in cases)
batch['budget']['kling_attempts_used'] = sum(c['video_attempted'] for c in cases)
batch['videos_generated'] = summary['videos_ready']
batch['reference_images_ready'] = summary['reference_images_ready']
batch['status'] = 'videos_generated_reviews_recorded' if summary['videos_ready']==10 and summary['semantic_reviews_recorded']==10 else 'video_generation_and_review_in_progress'
if summary.get('blocker'):
    batch['status'] = 'blocked_insufficient_kling_credits'
(bundle/'benchmark.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False))
