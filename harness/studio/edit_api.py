"""Owner scoped edit documents, source analysis and immutable export jobs."""
import asyncio
import secrets
import hashlib
import json
import re
import time
from copy import deepcopy
from typing import Literal
from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from harness.core.creative_edit_runner import run_suggestion
from harness.core.creative_speech_runner import run_transcription
from harness.models.creative_speech import settings as speech_settings, LANGUAGES
from harness.tools.creative_transcript import caption_plan
from harness.tools.creative_edit_publish import publish_export
from harness.tools.creative_edit_media import digest
from harness.tools.creative_edit_observe import MAX_SOURCES
from harness.studio import store
from harness.tools.creative_edit import initial_edit, skill_rhythm, skill_track_plan, skill_material_bindings, skill_version_impact, validate_edit, render_edit
from harness.tools.creative_retake import document_digest
from harness.tools.creative_edit_media import source_path, source_catalog, save_upload, waveform, MAX_EDIT_UPLOAD
from harness.tools.creative_edit_review import build_review
from harness.tools.creative_scene import layout_observation, station_manifest, station_keyframe_observation, station_keyframe_tracks, validate_scene, scene_hash as scene_document_hash
from harness.learning import edit_review


class EditDocument(BaseModel):
    revision: int
    spec: dict


class SuggestionRequest(BaseModel):
    revision: int
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    intent: str = Field(min_length=1, max_length=1000)


class TranscriptionRequest(BaseModel):
    revision: int
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source: str = Field(max_length=64)
    language: str = 'auto'


class Export(BaseModel):
    revision: int


class ReviewChecks(BaseModel):
    full_video_watched: bool = False
    audio_listened: bool = False
    product_facts_checked: bool = False


class ReviewRequest(BaseModel):
    revision: int
    decision: str = Field(pattern=r'^(pending|needs_changes|approved)$')
    checks: ReviewChecks
    note: str = Field(default='', max_length=1000)


class IndependentReviewRequest(BaseModel):
    revision: int
    export_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class CandidateReviewChecks(BaseModel):
    product: Literal['not_reviewed', 'aligned', 'deviation', 'unavailable'] = 'not_reviewed'
    motion: Literal['not_reviewed', 'aligned', 'deviation', 'unavailable'] = 'not_reviewed'
    audio: Literal['not_reviewed', 'aligned', 'deviation', 'unavailable'] = 'not_reviewed'


class SceneCandidateReviewRequest(BaseModel):
    revision: int
    candidate_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    checks: CandidateReviewChecks
    note: str = Field(default='', max_length=1000)


class SceneCandidateBatchPlanRequest(BaseModel):
    revision: int
    scene_retake_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class SceneCandidateBatchReceiptRequest(BaseModel):
    revision: int
    scene_retake_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class SceneCandidateBatchApplyDraftRequest(BaseModel):
    revision: int
    scene_retake_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class SceneCandidateBatchApplyCheckRequest(SceneCandidateBatchApplyDraftRequest):
    base_document_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    candidate_ids: list[str] = Field(min_length=1, max_length=12)


class SceneCandidateBatchApplyRequest(SceneCandidateBatchApplyCheckRequest):
    confirm: Literal['apply'] = 'apply'


class SceneCandidateBatchUndoRequest(BaseModel):
    revision: int
    application_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class SceneTimelineDraftRequest(BaseModel):
    revision: int
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class SceneTimelineApplyRequest(SceneTimelineDraftRequest):
    base_document_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    draft_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm: Literal['apply'] = 'apply'


class SceneTimelineUndoRequest(BaseModel):
    revision: int
    application_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class SceneBatchShotApproval(BaseModel):
    shot_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    decision: Literal['pending', 'approved', 'changes_requested', 'blocked'] = 'pending'
    note: str = Field(default='', max_length=500)


class SceneBatchApprovalRequest(BaseModel):
    revision: int
    scene_retake_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    shots: list[SceneBatchShotApproval] = Field(min_length=1, max_length=12)


def scene_reference_views(project, suggestion):
    """Return bounded, owner-scoped reference frames for a 3D retake card.

    Scene previews are canvas assets, but the editor must only show frames that
    belong to the exact scene hash used by the approved suggestion.  Keep the
    projection deliberately small: the browser receives a relative endpoint,
    provenance needed for comparison, and no local paths or provider data.
    """
    scene_hash = suggestion.get('scene_hash')
    if not isinstance(scene_hash, str):
        return []
    rows = []
    seen = set()
    assets = project.get('canvas_assets', {})
    for batch in project.get('scene_reference_batches', {}).values():
        for record in batch.get('references', []):
            aid = record.get('asset')
            if not isinstance(aid, str) or aid in seen:
                continue
            asset = assets.get(aid)
            provenance = asset.get('provenance', {}) if isinstance(asset, dict) else {}
            if not isinstance(asset, dict) or asset.get('kind') != 'image':
                continue
            if provenance.get('kind') != 'scene_browser_preview' or provenance.get('scene_hash') != scene_hash:
                continue
            seen.add(aid)
            rows.append({
                'asset': aid,
                'shot_id': record.get('shot_id') or provenance.get('shot_id'),
                'shot_name': provenance.get('shot_name'),
                'shot_index': provenance.get('shot_index'),
                'at': record.get('at', provenance.get('at')),
                'local_time': provenance.get('local_time'),
                'sha256': asset.get('sha256'),
                'scene_hash': scene_hash,
                'preview_url': f"/creative/api/projects/{project['id']}/canvas/assets/{aid}/preview",
                'training_eligible': False,
            })
    rows.sort(key=lambda item: (item.get('shot_index') if isinstance(item.get('shot_index'), int) else 999,
                                item.get('at') if isinstance(item.get('at'), (int, float)) else 0,
                                item['asset']))
    return rows[:6]


def scene_candidate_view(project, pid, job):
    """Expose the safe candidate projection used by scene and edit review cards."""
    view = {key: job.get(key) for key in
            ('id', 'state', 'credits', 'approved_credits', 'asset', 'candidate_sha256', 'qa',
             'training_eligible', 'revision')}
    if job.get('completed_revision') is not None:
        view['revision'] = job.get('completed_revision')
    if job.get('asset') and job.get('clip'):
        clip = job['clip']
        view['media'] = {
            'original_url': f'/creative/api/projects/{pid}/edit/source',
            'candidate_url': f"/creative/api/projects/{pid}/edit/sources/{job['asset']}",
            'source_start': clip.get('start'),
            'source_end': clip.get('end'),
            'duration': job.get('duration'),
        }
    review = job.get('candidate_review')
    if isinstance(review, dict):
        view['candidate_review'] = dict(review)
    view['candidate_review_summary'] = scene_candidate_review_summary(project, job)
    return view


def scene_candidate_review_summary(project, job):
    """Build a bounded multi-shot review summary for a completed candidate.

    A retake candidate can cover only one of several deviating 3D shots.  The
    summary makes that coverage visible without treating a saved observation
    as a semantic, motion, or audio pass.  It is presentation data only and
    never changes the edit document or training gate.
    """
    suggestion_id = job.get('scene_retake_id') if isinstance(job, dict) else None
    suggestion = project.get('scene_retake_suggestions', {}).get(suggestion_id, {}) if suggestion_id else {}
    raw_segments = suggestion.get('segments', []) if isinstance(suggestion, dict) else []
    segments = raw_segments if isinstance(raw_segments, list) else []
    clip = job.get('clip', {}) if isinstance(job, dict) else {}
    clip_start, clip_end = clip.get('start'), clip.get('end')
    has_clip = (clip.get('source', 'primary') == 'primary' and
                isinstance(clip_start, (int, float)) and isinstance(clip_end, (int, float)) and
                clip_end > clip_start)
    review = job.get('candidate_review') if isinstance(job, dict) else None
    recorded = isinstance(review, dict)
    rows = []
    for index, segment in enumerate(segments[:12]):
        if not isinstance(segment, dict):
            continue
        start, end = segment.get('start'), segment.get('end')
        valid_window = isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start
        overlap = has_clip and valid_window and min(clip_end, end) > max(clip_start, start)
        full = overlap and clip_start <= start and clip_end >= end
        coverage = 'full' if full else 'partial' if overlap else 'uncovered'
        rows.append({
            'shot_id': str(segment.get('shot_id') or '')[:48],
            'name': str(segment.get('name') or '未命名镜头')[:80],
            'start': float(start) if valid_window else 0,
            'end': float(end) if valid_window else 0,
            'coverage': coverage,
            'observation': 'recorded' if recorded and overlap else 'pending',
        })
    recorded_count = sum(row['observation'] == 'recorded' for row in rows)
    covered_count = sum(row['coverage'] != 'uncovered' for row in rows)
    checks = (review.get('checks', {}) if isinstance(review, dict) else {})
    checks_recorded = [key for key in ('product', 'motion', 'audio')
                       if checks.get(key) and checks.get(key) != 'not_reviewed']
    return {
        'state': 'recorded' if recorded else 'not_recorded',
        'segment_count': len(rows),
        'covered_segment_count': covered_count,
        'recorded_segment_count': recorded_count,
        'pending_segment_count': max(0, len(rows) - recorded_count),
        'checks_recorded': checks_recorded,
        'requires_full_replay': True,
        'requires_audio_check': True,
        'segments': rows,
        'training_eligible': False,
    }


def scene_candidate_batch_plan(project, pid, suggestion_id):
    """Return a read-only, per-shot plan for a multi-shot retake suggestion."""
    suggestion = project.get('scene_retake_suggestions', {}).get(suggestion_id)
    if not isinstance(suggestion, dict):
        return None
    candidates = [job for job in project.get('edit_retakes', {}).values()
                  if job.get('scene_retake_id') == suggestion_id]
    candidate = sorted(candidates, key=lambda item: item.get('created_at', 0))[-1] if candidates else None
    candidate_revision = candidate.get('completed_revision', candidate.get('revision')) if candidate else None
    current_candidate = bool(candidate and candidate.get('state') == 'completed' and
                             candidate_revision == project.get('revision'))
    summary = scene_candidate_review_summary(project, candidate) if current_candidate else None
    summary_rows = summary.get('segments', []) if summary else []
    stored_approval = project.get('scene_retake_batch_approvals', {}).get(suggestion_id)
    approval_matches = (isinstance(stored_approval, dict) and
                        stored_approval.get('revision') == project.get('revision') and
                        stored_approval.get('scene_hash') == suggestion.get('scene_hash') and
                        stored_approval.get('artifact_sha256') == suggestion.get('artifact_sha256'))
    approval_rows = {item.get('shot_id'): item for item in (stored_approval.get('shots', []) if approval_matches else [])
                     if isinstance(item, dict)}
    raw_segments = suggestion.get('segments', [])
    rows = []
    for index, segment in enumerate(raw_segments[:12] if isinstance(raw_segments, list) else []):
        if not isinstance(segment, dict):
            continue
        summary_row = summary_rows[index] if index < len(summary_rows) else {}
        coverage = summary_row.get('coverage') if summary else 'stale' if candidate else 'uncovered'
        observed = summary_row.get('observation') == 'recorded' if summary else False
        credits = segment.get('credits') if isinstance(segment.get('credits'), int) else 0
        rows.append({
            'shot_id': str(segment.get('shot_id') or '')[:48],
            'name': str(segment.get('name') or '未命名镜头')[:80],
            'start': float(segment.get('start', 0)),
            'end': float(segment.get('end', 0)),
            'duration': float(segment.get('duration', 0)),
            'billable_duration': float(segment.get('billable_duration', segment.get('duration', 0))),
            'credits': credits,
            'source_status': str(segment.get('status') or 'unavailable')[:24],
            'coverage': coverage,
            'observation': 'recorded' if observed else 'pending',
            'requires_candidate': coverage in ('uncovered', 'stale'),
            'approval': (approval_rows.get(str(segment.get('shot_id') or ''), {}).get('decision')
                        if approval_rows.get(str(segment.get('shot_id') or '')) else 'pending'),
        })
    total_credits = sum(item['credits'] for item in rows)
    remaining = [item for item in rows if item['requires_candidate']]
    review_pending = [item for item in rows if item['coverage'] in ('full', 'partial') and item['observation'] != 'recorded']
    approved = [item for item in rows if item['approval'] == 'approved']
    blocked = [item for item in rows if item['approval'] in ('blocked', 'changes_requested')]
    model_supported = suggestion.get('model') == 'kling-video-v3_0_omni'
    submission_blocker = None
    if not approval_matches:
        submission_blocker = '请先保存逐镜头审批回执'
    elif not approved:
        submission_blocker = '请至少批准一个镜头'
    elif not model_supported:
        submission_blocker = '当前批量提交仅接入 Kling O3；请重新选择模型并生成报价'
    return {
        'project_id': pid,
        'revision': project.get('revision'),
        'scene_retake_id': suggestion_id,
        'state': 'stale' if candidate and not current_candidate else 'ready_for_review',
        'model': str(suggestion.get('model') or '')[:80],
        'model_label': str(suggestion.get('model_label') or suggestion.get('model') or '')[:100],
        'approval_mode': suggestion.get('approval_mode') if suggestion.get('approval_mode') in ('manual', 'auto') else 'manual',
        'aspect': suggestion.get('aspect') if suggestion.get('aspect') in ('16:9', '9:16', '1:1') else '16:9',
        'candidate': ({
            'id': candidate.get('id'), 'state': candidate.get('state'),
            'revision': candidate_revision, 'candidate_review_summary': summary,
        } if candidate else None),
        'segments': rows,
        'total_segment_count': len(rows),
        'covered_segment_count': sum(not item['requires_candidate'] for item in rows),
        'remaining_segment_count': len(remaining),
        'review_pending_count': len(review_pending),
        'approval_recorded': approval_matches,
        'approved_segment_count': len(approved),
        'blocked_segment_count': len(blocked),
        'total_credits': total_credits,
        'remaining_credits': sum(item['credits'] for item in remaining),
        'requires_explicit_approval': True,
        'approval_receipt_sha256': stored_approval.get('receipt_sha256') if approval_matches else None,
        'can_submit': not submission_blocker,
        'submission_blocker': submission_blocker,
        'submission_model': 'kling-video-v3_0_omni',
        'training_eligible': False,
    }


def scene_retake_batch_execution(project, suggestion_id):
    """Safe projection of the explicit paid batch queue, if one exists."""
    queues = [item for item in project.get('edit_retake_batches', {}).values()
              if isinstance(item, dict) and item.get('scene_retake_id') == suggestion_id]
    if not queues:
        return None
    queue = sorted(queues, key=lambda item: item.get('created_at', 0))[-1]
    jobs = project.get('edit_retakes', {})
    rows = []
    for jid in queue.get('job_ids', [])[:12]:
        job = jobs.get(jid)
        if not isinstance(job, dict):
            continue
        rows.append({key: job.get(key) for key in (
            'id', 'scene_shot_id', 'state', 'credits', 'approved_credits', 'asset',
            'candidate_sha256', 'completed_revision', 'qa', 'error', 'training_eligible')})
    return {
        key: queue.get(key) for key in (
            'id', 'scene_retake_id', 'state', 'revision', 'base_document_sha256',
            'approval_receipt_sha256', 'shot_ids', 'job_ids', 'total_credits',
            'approved_credits', 'current_index', 'completed_count', 'error',
            'training_eligible', 'created_at')
    } | {'jobs': rows, 'project_revision': project.get('revision')}


def scene_candidate_batch_receipt(project, pid, suggestion_id):
    """Project existing single-shot jobs into a read-only batch receipt.

    This is deliberately derived from persisted retake states. It never
    creates a batch job or infers provider success from a missing callback.
    """
    suggestion = project.get('scene_retake_suggestions', {}).get(suggestion_id)
    if not isinstance(suggestion, dict):
        return None
    intent = project.get('scene_render_intent', {})
    render_review = project.get('scene_render_review', {})
    binding_current = (suggestion.get('scene_hash') == intent.get('scene_hash') and
                       suggestion.get('artifact_sha256') == render_review.get('artifact_sha256'))
    execution = scene_retake_batch_execution(project, suggestion_id)
    stored_approval = project.get('scene_retake_batch_approvals', {}).get(suggestion_id)
    approval_current = (isinstance(stored_approval, dict) and
                        stored_approval.get('revision') == project.get('revision') and
                        stored_approval.get('scene_hash') == suggestion.get('scene_hash') and
                        stored_approval.get('artifact_sha256') == suggestion.get('artifact_sha256'))
    if execution and isinstance(stored_approval, dict):
        # Each successful candidate advances the edit revision. The queue's
        # immutable approval receipt is the authority while it is executing.
        approval_current = approval_current or stored_approval.get('receipt_sha256') == execution.get('approval_receipt_sha256')
    approval_rows = {item.get('shot_id'): item for item in (stored_approval.get('shots', []) if approval_current else [])
                     if isinstance(item, dict)}
    jobs = [job for job in project.get('edit_retakes', {}).values()
            if isinstance(job, dict) and job.get('scene_retake_id') == suggestion_id]
    segments = suggestion.get('segments', []) if isinstance(suggestion.get('segments'), list) else []
    rows = []
    for segment in segments[:12]:
        if not isinstance(segment, dict):
            continue
        shot_id = str(segment.get('shot_id') or '')[:48]
        start, end = segment.get('start'), segment.get('end')
        matches = []
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            for job in jobs:
                clip = job.get('clip') if isinstance(job.get('clip'), dict) else {}
                if clip.get('source', 'primary') != 'primary':
                    continue
                clip_start, clip_end = clip.get('start'), clip.get('end')
                if (isinstance(clip_start, (int, float)) and isinstance(clip_end, (int, float)) and
                        clip_start <= start and clip_end >= end):
                    matches.append(job)
        latest = sorted(matches, key=lambda item: item.get('created_at', 0))[-1] if matches else None
        decision = approval_rows.get(shot_id, {}).get('decision', 'pending')
        if not approval_current:
            status = 'stale' if stored_approval else 'awaiting_approval'
        elif decision in ('blocked', 'changes_requested'):
            status = 'blocked'
        elif decision != 'approved':
            status = 'awaiting_approval'
        elif latest is None:
            status = 'awaiting_submission'
        else:
            state = latest.get('state')
            if state == 'completed' and latest.get('asset') and latest.get('candidate_sha256'):
                completed_revision = latest.get('completed_revision', latest.get('revision'))
                status = 'succeeded' if completed_revision == project.get('revision') else 'stale'
            elif state in ('submitting', 'generating', 'checking'):
                status = 'running'
            elif state in ('failed', 'cancelled', 'canceled'):
                status = 'failed'
            elif state == 'needs_review' or not state:
                status = 'unknown'
            else:
                status = 'awaiting_submission' if state == 'ready' else 'unknown'
        rows.append({
            'shot_id': shot_id,
            'name': str(segment.get('name') or '未命名镜头')[:80],
            'start': float(start) if isinstance(start, (int, float)) else 0,
            'end': float(end) if isinstance(end, (int, float)) else 0,
            'decision': decision,
            'status': status,
            'candidate_id': latest.get('id') if latest else None,
            'candidate_state': latest.get('state') if latest else None,
            'training_eligible': False,
        })
    counts = {status: sum(row['status'] == status for row in rows) for status in
              ('succeeded', 'failed', 'unknown', 'running', 'awaiting_submission', 'awaiting_approval', 'blocked', 'stale')}
    finished = counts['succeeded'] + counts['failed']
    pending_like = (counts['awaiting_approval'] + counts['awaiting_submission'] +
                    counts['running'] + counts['unknown'])
    adverse = counts['failed'] + counts['blocked'] + counts['stale']
    if counts['succeeded'] and (pending_like or adverse):
        overall = 'partial_success'
    elif not rows or pending_like:
        overall = 'pending'
    elif counts['failed'] and counts['succeeded']:
        overall = 'partial_success'
    elif counts['failed']:
        overall = 'failed'
    elif counts['blocked']:
        overall = 'blocked'
    elif counts['succeeded'] == len(rows):
        overall = 'succeeded'
    else:
        overall = 'needs_reconciliation'
    return {
        'project_id': pid,
        'revision': project.get('revision'),
        'scene_retake_id': suggestion_id,
        'overall': overall,
        'segments': rows,
        'counts': counts,
        'finished_segment_count': finished,
        'approval_recorded': approval_current,
        'approval_receipt_sha256': stored_approval.get('receipt_sha256') if approval_current else None,
        'requires_manual_reconciliation': bool(counts['failed'] or counts['unknown'] or counts['stale']),
        'can_apply': False,
        'execution': execution,
        'training_eligible': False,
        'note': '只读投影；部分成功、失败或未知状态仍需逐镜头人工处理，不会自动重试或替换原片。',
    }


def scene_candidate_batch_apply_draft(project, pid, suggestion_id):
    """Build a reversible apply proposal without changing the edit document."""
    suggestion = project.get('scene_retake_suggestions', {}).get(suggestion_id)
    if not isinstance(suggestion, dict):
        return None
    receipt = scene_candidate_batch_receipt(project, pid, suggestion_id)
    if receipt is None:
        return None
    jobs = {job.get('id'): job for job in project.get('edit_retakes', {}).values()
            if isinstance(job, dict) and job.get('scene_retake_id') == suggestion_id}
    clips = (project.get('edit') or {}).get('clips', [])
    rows = []
    for item in receipt['segments']:
        job = jobs.get(item.get('candidate_id'))
        review = job.get('candidate_review') if isinstance(job, dict) else None
        checks = review.get('checks', {}) if isinstance(review, dict) else {}
        target_index = None
        for index, clip in enumerate(clips if isinstance(clips, list) else []):
            if (isinstance(clip, dict) and clip.get('source') == 'primary' and
                    isinstance(clip.get('start'), (int, float)) and isinstance(clip.get('end'), (int, float)) and
                    clip.get('start') <= item['start'] and clip.get('end') >= item['end']):
                target_index = index
                break
        eligibility = 'not_ready'
        reason = '候选尚未完成'
        if item['status'] == 'succeeded' and not isinstance(review, dict):
            eligibility, reason = 'needs_review', '候选尚未完成三项人工核对'
        elif item['status'] == 'succeeded' and target_index is None:
            eligibility, reason = 'blocked', '当前时间轴没有完整覆盖该镜头窗口'
        elif item['status'] == 'succeeded' and any(checks.get(key) == 'not_reviewed' for key in ('product', 'motion', 'audio')):
            eligibility, reason = 'needs_review', '商品、动作或原声仍有核对项待决定'
        elif item['status'] == 'succeeded' and any(checks.get(key) in ('deviation', 'unavailable') for key in ('product', 'motion', 'audio')):
            eligibility, reason = 'needs_changes', '人工核对记录包含问题或无法判断'
        elif item['status'] == 'succeeded':
            eligibility, reason = 'ready', '候选完成且三项人工核对均为基本一致'
        rows.append({
            'shot_id': item['shot_id'], 'name': item['name'], 'start': item['start'], 'end': item['end'],
            'candidate_id': item.get('candidate_id'), 'asset': job.get('asset') if isinstance(job, dict) else None,
            'target_clip_index': target_index, 'checks': checks if isinstance(checks, dict) else {},
            'eligibility': eligibility, 'reason': reason, 'training_eligible': False,
        })
    ready = [row for row in rows if row['eligibility'] == 'ready']
    return {
        'project_id': pid, 'revision': project.get('revision'), 'scene_retake_id': suggestion_id,
        'state': 'ready' if ready else 'blocked', 'rows': rows, 'ready_count': len(ready),
        'excluded_count': len(rows) - len(ready), 'base_document_sha256': document_digest(project.get('edit') or {}),
        'candidate_ids': [row['candidate_id'] for row in ready if row.get('candidate_id')],
        'reversible': True, 'can_apply': False, 'requires_explicit_confirmation': True,
        'training_eligible': False,
        'note': '只读草稿；应用前必须重新核对版本并记录可撤销操作，当前不会改写时间轴。',
    }


def scene_candidate_batch_apply_check(project, pid, request):
    """Re-check a draft's immutable inputs without applying it."""
    draft = scene_candidate_batch_apply_draft(project, pid, request.scene_retake_id)
    if draft is None:
        return None
    conflicts = []
    if draft['base_document_sha256'] != request.base_document_sha256:
        conflicts.append('document_changed')
    if draft['candidate_ids'] != request.candidate_ids:
        conflicts.append('candidate_set_changed')
    suggestion = project.get('scene_retake_suggestions', {}).get(request.scene_retake_id, {})
    if (suggestion.get('scene_hash') != project.get('scene_render_intent', {}).get('scene_hash') or
            suggestion.get('artifact_sha256') != project.get('scene_render_review', {}).get('artifact_sha256')):
        conflicts.append('scene_or_artifact_changed')
    if draft['state'] != 'ready':
        conflicts.append('draft_not_ready')
    return {
        'project_id': pid, 'revision': project.get('revision'), 'scene_retake_id': request.scene_retake_id,
        'safe_to_apply': not conflicts, 'conflicts': conflicts,
        'current_document_sha256': draft['base_document_sha256'],
        'candidate_ids': draft['candidate_ids'], 'can_apply': False,
        'requires_explicit_confirmation': True, 'training_eligible': False,
        'note': '只读冲突检查；检查通过也不会应用、扣费或创建任务。',
    }


def scene_batch_clip_view(clip):
    """Return the small, path-free clip projection used by the diff preview."""
    if not isinstance(clip, dict):
        return None
    return {key: clip[key] for key in (
        'source', 'start', 'end', 'gain', 'transition', 'transition_duration')
            if key in clip}


def scene_batch_timeline_diff(record):
    """Compare bounded clip snapshots without exposing private edit payloads."""
    before = record.get('before_clips', [])
    after = record.get('after_clips', [])
    if not isinstance(before, list) or not isinstance(after, list):
        return []
    rows = []
    for index in range(max(len(before), len(after))):
        before_view = scene_batch_clip_view(before[index]) if index < len(before) else None
        after_view = scene_batch_clip_view(after[index]) if index < len(after) else None
        if before_view != after_view:
            rows.append({'index': index, 'before': before_view, 'after': after_view})
    return rows[:32]


def scene_batch_track_view(item, kind):
    """Return a bounded, readable subtitle/audio track item."""
    if not isinstance(item, dict):
        return None
    if kind == 'captions':
        return {key: item[key] for key in ('start', 'end', 'text', 'track') if key in item}
    return {key: item[key] for key in ('source', 'start', 'end', 'at', 'gain') if key in item}


def scene_batch_track_diff(record):
    result = {}
    for kind in ('captions', 'audio'):
        before = [scene_batch_track_view(item, kind) for item in record.get('before_' + kind, [])[:64]]
        after = [scene_batch_track_view(item, kind) for item in record.get('after_' + kind, [])[:64]]
        before = [item for item in before if item is not None]
        after = [item for item in after if item is not None]
        result[kind] = {'changed': before != after, 'before': before, 'after': after}
    return result


def scene_batch_application_view(record):
    """Expose only the bounded identity, state and timeline diff of an application."""
    view = {key: record.get(key) for key in (
        'id', 'scene_retake_id', 'revision_before', 'revision_after',
        'candidate_ids', 'before_document_sha256', 'after_document_sha256',
        'state', 'reversible', 'training_eligible', 'undo_revision')
            if key in record}
    view['timeline_diff'] = scene_batch_timeline_diff(record)
    view['track_diff'] = scene_batch_track_diff(record)
    return view


def scene_timeline_application_view(record):
    """Expose a bounded undo receipt for a scene-to-edit timeline handoff.

    The reversible before document is intentionally kept owner-scoped in the
    project record.  The browser only needs identities, hashes and the small
    track projection to decide whether undo is still safe.
    """
    view = {key: record.get(key) for key in (
        'id', 'revision_before', 'revision_after', 'before_document_sha256',
        'after_document_sha256', 'scene_hash', 'state', 'reversible',
        'training_eligible', 'undo_revision') if key in record}
    view['shot_count'] = len(record.get('shots', []))
    view['shots'] = [dict(item) for item in record.get('shots', [])[:12]
                     if isinstance(item, dict)]
    return view


def scene_handoff_view(project):
    """Project the saved 3D-BOX handoff into the editor contract.

    This is a bounded review summary. It does not expose camera coordinates,
    provider payloads, media URLs, or any generation task handle.
    """
    scene = project.get('scene3d') if isinstance(project.get('scene3d'), dict) else None
    intent = project.get('scene_render_intent') if isinstance(project.get('scene_render_intent'), dict) else {}
    review = project.get('scene_render_review') if isinstance(project.get('scene_render_review'), dict) else {}
    applications = [item for item in (project.get('scene_timeline_applications') or {}).values()
                    if isinstance(item, dict)]
    current = [item for item in applications
               if item.get('revision_after') == project.get('revision')
               and item.get('scene_hash') == intent.get('scene_hash')]
    if not scene:
        state = 'not_connected'
    elif current:
        state = 'timeline_applied'
    elif intent:
        state = 'scene_ready'
    else:
        state = 'scene_saved'
    def shot_role(name):
        value = str(name or '')[:160]
        patterns = (
            ('product', r'商品|产品|瓶身|服装|外观|材质|细节|product|detail'),
            ('person', r'人物|模特|角色|演员|人像|person|model|talent'),
            ('scene', r'场景|环境|空间|地点|室内|街景|scene|location|environment'),
            ('style', r'风格|色调|光线|氛围|style|lighting|mood'),
        )
        return next((role for role, pattern in patterns if re.search(pattern, value, re.I)), None)

    shot_windows = []
    trajectory_shots = []
    station_keyframes = []
    role_objects = []
    for obj in (scene.get('objects', []) if scene else [])[:24]:
        role = shot_role(obj.get('name'))
        if role:
            role_objects.append({'object_id': str(obj.get('id') or '')[:48],
                                 'name': str(obj.get('name') or '')[:80], 'role': role})
    current_scene_hash = scene_document_hash(scene) if scene else None
    station = station_manifest(scene) if scene else {'sha256': None, 'objects': []}
    station_observation = layout_observation(scene, project.get('scene_assets', {})) if scene else {
        'version': 1,
        'status': 'unavailable',
        'collisions': [],
        'unknown_bounds': [],
        'training_eligible': False,
    }
    keyframe_observation = station_keyframe_observation(scene, project.get('scene_assets', {})) if scene else {
        'version': 1, 'shots': [], 'training_eligible': False,
    }
    keyframe_tracks = station_keyframe_tracks(scene) if scene else {
        'version': 1, 'shots': [], 'training_eligible': False,
    }
    binding_record = project.get('scene_role_bindings') if isinstance(project.get('scene_role_bindings'), dict) else {}
    role_bindings = [{key: str(item.get(key) or '')[:48] for key in ('shot_id', 'object_id', 'role')}
                     for item in binding_record.get('bindings', [])[:12] if isinstance(item, dict)]
    cursor = 0.0
    for shot in (scene.get('shots', []) if scene else [])[:12]:
        try:
            duration = max(0.0, float(shot.get('duration')))
        except (AttributeError, TypeError, ValueError):
            continue
        shot_windows.append({
            'shot_id': str(shot.get('id') or '')[:48],
            'name': str(shot.get('name') or '')[:80],
            'role': shot_role(shot.get('name')),
            'start': round(cursor, 3),
            'end': round(cursor + duration, 3),
            'duration': round(duration, 3),
        })
        camera = shot.get('camera') if isinstance(shot.get('camera'), dict) else {}
        points = camera.get('points') if isinstance(camera.get('points'), list) else []
        trajectory_shots.append({
            'shot_id': str(shot.get('id') or '')[:48],
            'path_points': min(64, len(points)),
            'path_closed': bool(camera.get('closed')),
            'path_easing': str(camera.get('easing') or 'linear')[:16],
        })
        keyframes = shot.get('station_keyframes') if isinstance(shot.get('station_keyframes'), list) else []
        station_keyframes.append({
            'shot_id': str(shot.get('id') or '')[:48],
            'keyframe_count': min(24, len(keyframes)),
            'object_ids': [str(item.get('object_id') or '')[:48] for item in keyframes[:12] if isinstance(item, dict)],
            'times': [round(max(0.0, min(duration, float(item.get('at', 0)))), 3)
                      for item in keyframes[:24]
                      if isinstance(item, dict) and isinstance(item.get('at'), (int, float))],
        })
        cursor += duration
    trajectory_stale = bool(intent and current_scene_hash and intent.get('scene_hash') != current_scene_hash)
    station_stale = bool(intent.get('station_sha256') and station.get('sha256') != intent.get('station_sha256'))
    station_objects = []
    role_by_id = {item['object_id']: item['role'] for item in role_objects if item.get('object_id')}
    for item in station.get('objects', [])[:24]:
        station_objects.append({
            'object_id': str(item.get('object_id') or '')[:48],
            'role': role_by_id.get(item.get('object_id')),
            'placement_sha256': str(item.get('placement_sha256') or '')[:12],
        })
    return {
        'version': 1,
        'state': state,
        'shot_count': min(12, len(scene.get('shots', []))) if scene else 0,
        'shot_windows': shot_windows,
        'trajectory_shots': trajectory_shots,
        'station_keyframes': station_keyframes,
        'station_keyframe_observation': keyframe_observation,
        'station_keyframe_tracks': keyframe_tracks,
        'trajectory_stale': trajectory_stale,
        'station_stale': station_stale,
        'station_sha256_prefix': str(station.get('sha256') or '')[:12] or None,
        'station_objects': station_objects,
        'layout_observation': station_observation,
        'role_objects': role_objects,
        'role_bindings': role_bindings,
        'role_bindings_stale': bool(role_bindings) and binding_record.get('scene_hash') != current_scene_hash,
        'duration': round(cursor, 3) if shot_windows else None,
        'timeline_application_count': len(applications[-20:]),
        'current_application_count': len(current),
        'trajectory': 'locked' if intent.get('trajectory_sha256') else 'needs_review',
        'render_review': str(review.get('decision') or 'pending')[:32],
        'scene_revision': intent.get('scene_revision'),
        'scene_hash_prefix': str(intent.get('scene_hash') or '')[:12] or None,
        'training_eligible': False,
    }


def creative_review_summary(scene_handoff, track_plan, material_bindings):
    """Aggregate existing observations into a pre-submit review checklist."""
    items = []
    handoff = scene_handoff if isinstance(scene_handoff, dict) else {}
    if handoff.get('state') in ('scene_ready', 'scene_saved'):
        items.append({'kind': '3d', 'target': 'scene_handoff', 'severity': 'review', 'message': '3D-BOX 场景尚未接入当前剪辑时间轴'})
    elif handoff.get('state') == 'timeline_applied':
        items.append({'kind': '3d', 'target': 'scene_handoff', 'severity': 'review', 'message': '3D-BOX 镜头轨已接入，仍需回放核对'})
    if handoff.get('trajectory') != 'locked' and handoff.get('state') != 'not_connected':
        items.append({'kind': 'trajectory', 'target': 'scene_handoff', 'severity': 'review', 'message': '镜头轨迹尚未形成锁定摘要'})
    if handoff.get('trajectory_stale'):
        items.append({'kind': 'trajectory', 'target': 'scene_handoff', 'severity': 'review', 'message': '关键帧路径在上次渲染确认后发生变化，请重新核对并锁定'})
    if handoff.get('station_stale'):
        items.append({'kind': 'station', 'target': 'scene_handoff', 'severity': 'review', 'message': '对象站位在上次渲染确认后发生变化，请重新核对并锁定'})
    layout = handoff.get('layout_observation') if isinstance(handoff.get('layout_observation'), dict) else {}
    if layout.get('status') == 'needs_check':
        collision_count = len(layout.get('collisions') or [])
        unknown_count = len(layout.get('unknown_bounds') or [])
        items.append({
            'kind': 'station',
            'target': 'scene_handoff',
            'severity': 'review',
            'message': f'3D 站位需要核对：重叠 {collision_count} 组，GLB 边界未知 {unknown_count} 个',
        })
    keyframe_observation = handoff.get('station_keyframe_observation') if isinstance(handoff.get('station_keyframe_observation'), dict) else {}
    keyframe_risks = [item for item in keyframe_observation.get('shots', [])
                      if isinstance(item, dict) and item.get('status') == 'needs_check']
    if keyframe_risks:
        collisions = sum(int(item.get('collision_count') or 0) for item in keyframe_risks)
        unknown = sum(int(item.get('unknown_bounds_count') or 0) for item in keyframe_risks)
        items.append({'kind': 'station', 'target': 'scene_handoff', 'severity': 'review',
                      'message': f'对象关键帧需要核对：{len(keyframe_risks)} 个镜头，重叠 {collisions} 组，GLB 边界未知 {unknown} 个'})
    if handoff.get('render_review') == 'changes_requested':
        items.append({'kind': 'trajectory', 'target': 'scene_handoff', 'severity': 'block', 'message': '3D 成片回放记录存在镜头偏差，请回到场景复核'})
    constraints = (track_plan or {}).get('constraints') or {}
    collision_count = len(constraints.get('caption_collisions') or [])
    if collision_count:
        items.append({'kind': 'caption', 'target': 'track_plan', 'severity': 'block', 'message': f'同轨字幕重叠 {collision_count} 处'})
    scene_windows = [item for item in handoff.get('shot_windows') or [] if isinstance(item, dict)]
    beats = [item for item in (track_plan or {}).get('beats') or [] if isinstance(item, dict)]
    if scene_windows and beats:
        timing_gaps = abs(len(scene_windows) - len(beats))
        timing_gaps += sum(
            abs(float(shot.get('duration')) - (float(beat.get('end')) - float(beat.get('start')))) > .05
            for shot, beat in zip(scene_windows, beats)
            if isinstance(shot.get('duration'), (int, float))
        )
        if timing_gaps:
            items.append({'kind': 'timing', 'target': 'track_plan', 'severity': 'review', 'message': f'3D 镜头与 Skill 节拍有 {timing_gaps} 处时长或数量偏差'})
    explicit_roles = {} if handoff.get('role_bindings_stale') else {
        str(item.get('shot_id')): item.get('role')
        for item in handoff.get('role_bindings') or [] if isinstance(item, dict) and item.get('shot_id') and item.get('role')
    }
    role_gaps = 0
    first_role_gap = None
    for shot, beat in zip(scene_windows, (material_bindings or {}).get('shot_bindings') or []):
        scene_role, skill_role = explicit_roles.get(shot.get('shot_id')) or shot.get('role'), beat.get('role')
        if scene_role and skill_role and scene_role != skill_role:
            role_gaps += 1
            first_role_gap = first_role_gap or {'shot_id': shot.get('shot_id'), 'scene_role': scene_role, 'skill_role': skill_role}
    if role_gaps:
        item = {'kind': 'role', 'target': 'scene_handoff', 'severity': 'review', 'message': f'3D 镜头与 Skill 节拍有 {role_gaps} 处角色不一致'}
        if first_role_gap and first_role_gap.get('shot_id'):
            item.update(first_role_gap)
        items.append(item)
    missing = sum(item.get('status') == 'missing' for item in (material_bindings or {}).get('shot_bindings', []))
    if missing:
        items.append({'kind': 'material', 'target': 'material_bindings', 'severity': 'review', 'message': f'{missing} 个节拍缺少角色素材候选'})
    return {
        'version': 1,
        'status': 'needs_review' if items else 'clear',
        'items': items[:12],
        'training_eligible': False,
    }


def scene_timeline_draft(project, sources, expected_scene_hash):
    """Build a read-only 3D shot plan for the ordinary edit timeline.

    This function deliberately only cuts an already-owned video source into
    the saved shot durations.  It never invokes a provider, reserves credits,
    or treats a 3D preview as a generated video asset.
    """
    if not project.get('scene3d'):
        raise ValueError('请先保存 3D 场景，再生成剪辑轨道草稿')
    try:
        scene = validate_scene(project['scene3d'], project.get('scene_assets', {}))
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('场景无效：' + str(exc)[:300]) from exc
    current_scene_hash = scene_document_hash(scene)
    if current_scene_hash != expected_scene_hash:
        raise ValueError('3D 场景已变化，请重新生成剪辑轨道草稿')

    raw_spec = project.get('edit') or initial_edit(project, catalog=sources)
    base_document_sha256 = document_digest(raw_spec)
    try:
        base_spec = validate_edit(raw_spec, catalog=sources) if raw_spec.get('clips') else raw_spec
    except (ValueError, TypeError, KeyError) as exc:
        return ({
            'state': 'unavailable',
            'reason': '当前剪辑草稿需要先修复：' + str(exc)[:240],
            'project_id': project['id'],
            'revision': project['revision'],
            'scene_hash': current_scene_hash,
            'base_document_sha256': base_document_sha256,
            'draft_sha256': None,
            'source': None,
            'rows': [],
            'conflicts': ['current_edit_invalid'],
            'preserves': {'captions': 0, 'audio': 0},
            'requires_explicit_confirmation': True,
            'training_eligible': False,
        }, None, None)

    video_sources = [(sid, meta) for sid, meta in sources.items()
                     if isinstance(meta, dict) and meta.get('kind') == 'video']
    video_sources.sort(key=lambda item: (0 if item[0] == 'primary' else 1, item[0]))
    shots = scene.get('shots', [])[:12]
    rows = []
    cursor = 0.0
    for index, shot in enumerate(shots):
        duration = round(float(shot['duration']), 3)
        rows.append({
            'index': index,
            'shot_id': shot['id'],
            'name': shot['name'],
            'start': round(cursor, 3),
            'end': round(cursor + duration, 3),
            'duration': duration,
            'source_start': round(cursor, 3),
            'source_end': round(cursor + duration, 3),
        })
        cursor += duration

    source_id, source_meta = video_sources[0] if video_sources else (None, None)
    total_duration = round(float(scene['duration']), 3)
    conflicts = []
    if source_meta is None:
        conflicts.append('no_video_source')
    elif float(source_meta['duration']) + .01 < total_duration:
        conflicts.append('source_too_short')

    # Keep existing editorial tracks intact when they fit.  If a track would
    # be cut by the shot plan, require a human adjustment instead of silently
    # trimming a caption or audio cue.
    captions = base_spec.get('captions', []) if isinstance(base_spec, dict) else []
    audio = base_spec.get('audio', []) if isinstance(base_spec, dict) else []
    for item in captions:
        if not isinstance(item, dict) or item.get('end', 0) > total_duration + .01:
            conflicts.append('caption_outside_duration')
            break
    for item in audio:
        if not isinstance(item, dict):
            conflicts.append('audio_invalid')
            break
        try:
            if float(item.get('at', 0)) + float(item.get('end', 0)) - float(item.get('start', 0)) > total_duration + .01:
                conflicts.append('audio_outside_duration')
                break
        except (TypeError, ValueError):
            conflicts.append('audio_invalid')
            break

    after_spec = None
    if not conflicts and source_meta is not None:
        candidate = deepcopy(base_spec)
        candidate['sources'] = dict(candidate.get('sources') or {})
        candidate['sources'][source_id] = source_meta['sha256']
        candidate['clips'] = [{
            'source': source_id,
            'start': row['source_start'],
            'end': row['source_end'],
            'gain': 1,
            'transition': {'kind': 'cut', 'duration': 0},
        } for row in rows]
        try:
            after_spec = validate_edit(candidate, catalog=sources)
        except (ValueError, TypeError, KeyError) as exc:
            conflicts.append('draft_invalid:' + str(exc)[:120])

    state = ('ready' if after_spec is not None else
             'unavailable' if source_meta is None else
             'needs_review' if conflicts else 'unavailable')
    reason = {
        'ready': '只读轨道草稿已生成，确认后才会写入剪辑文档。',
        'needs_review': '当前素材或字幕、音频与镜头时长不一致，请先处理冲突。',
        'unavailable': '尚无可用视频素材；先在剪辑工作室加入素材。',
    }[state]
    return ({
        'state': state,
        'reason': reason,
        'project_id': project['id'],
        'revision': project['revision'],
        'scene_hash': current_scene_hash,
        'base_document_sha256': base_document_sha256,
        'draft_sha256': document_digest(after_spec) if after_spec is not None else None,
        'source': ({
            'id': source_id,
            'title': str(source_meta.get('title') or source_id)[:80],
            'duration': round(float(source_meta['duration']), 3),
            'has_audio': bool(source_meta.get('has_audio')),
        } if source_meta is not None else None),
        'rows': rows,
        'conflicts': conflicts[:8],
        'preserves': {'captions': len(captions), 'audio': len(audio)},
        'requires_explicit_confirmation': True,
        'training_eligible': False,
    }, base_spec, after_spec)


def install(gateway):
    app = gateway.app
    analysis_slots = asyncio.Semaphore(2)
    speech_slots = asyncio.Semaphore(1)
    def owner(auth): return gateway.require_session(auth)['id']
    def writable(p, revision):
        if p['revision'] != revision or p['id'] in store.RUNNING or p['state'] in ('planning', 'running', 'rendering'):
            raise HTTPException(409, '项目已更新或正在处理，请重新打开剪辑')
    async def catalog(p):
        try: return await asyncio.to_thread(source_catalog, p)
        except (ValueError, OSError): raise HTTPException(409, '项目素材暂不可读取，请检查源文件')
    def validated(spec, sources):
        try: return validate_edit(spec, catalog=sources)
        except (ValueError, TypeError, KeyError, AttributeError) as exc: raise HTTPException(422, str(exc)) from exc

    def suggestion_view(p, job):
        if not job: return None
        result = dict(job, stale=p['revision'] != job['revision'])
        if job['state']=='running' and p['id'] not in store.RUNNING:
            result.update(state='interrupted',error='分析曾中断，原草稿保留；没有重新调用模型。')
        return result

    @app.get('/creative/editor', include_in_schema=False)
    def editor(): return FileResponse(store.ROOT/'tools/agent_studio/editor.html', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/editor-timing.js', include_in_schema=False)
    def editor_timing(): return FileResponse(store.ROOT/'tools/agent_studio/editor-timing.js', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/editor-captions.js', include_in_schema=False)
    def editor_captions(): return FileResponse(store.ROOT/'tools/agent_studio/editor-captions.js', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/editor-review.js', include_in_schema=False)
    def editor_review(): return FileResponse(store.ROOT/'tools/agent_studio/editor-review.js', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/editor.{ext}', include_in_schema=False)
    def editor_asset(ext: str):
        if ext not in ('js', 'css'): raise HTTPException(404)
        return FileResponse(store.ROOT/f'tools/agent_studio/editor.{ext}', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/api/projects/{pid}/edit')
    async def document(pid: str, scene_retake: str | None = None, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization)); sources = await catalog(p)
        skill = p.get('skill') or {}
        creative_context = {
            'skill_id': p.get('skill_id', 'ad-video'),
            'skill_title': p.get('skill_title') or skill.get('title') or '商品广告导演',
            'skill_version': skill.get('version'),
            'model': p.get('model'),
            'model_label': (p.get('quote') or {}).get('label'),
            'approval_mode': p.get('approval_mode', 'manual'),
            'aspect': p.get('aspect'),
            'contract': {key: list(skill.get(key) or []) for key in ('inputs', 'references', 'steps', 'checks')},
            'scene_handoff': scene_handoff_view(p),
            'material_bindings': skill_material_bindings(p),
        }
        spec = p.get('edit') or initial_edit(p, catalog=sources)
        warning = None
        if spec.get('clips'):
            try: spec = validate_edit(spec, catalog=sources)
            except (ValueError, TypeError, KeyError): warning = '草稿引用的素材发生变化，已保留草稿；请删除失效片段并重新加入素材。'
        rhythm_project = {'skill': skill, 'duration': spec.get('duration') or p.get('duration')}
        creative_context['rhythm'] = list(spec.get('rhythm') or skill_rhythm(rhythm_project))
        creative_context['track_plan'] = skill_track_plan(rhythm_project, spec, duration=spec.get('duration') or p.get('duration'))
        creative_context['review_summary'] = creative_review_summary(
            creative_context['scene_handoff'], creative_context['track_plan'], creative_context['material_bindings'])
        # A newer Skill is shown as a bounded, read-only impact preview.  The
        # project stays pinned to its saved version until a later explicit
        # confirmation flow updates it.
        creative_context['skill_impact'] = None
        try:
            from harness.studio.templates import find_skill
            selected_id = str(p.get('skill_id') or '')
            if selected_id:
                latest_skill = find_skill(selected_id, owner(authorization))
                current_version = int(skill.get('version') or 1)
                if int(latest_skill.get('version') or current_version) != current_version:
                    creative_context['skill_impact'] = skill_version_impact(rhythm_project, spec, latest_skill)
        except (HTTPException, TypeError, ValueError, KeyError):
            # A removed or malformed catalog entry must not block editing the
            # already saved project.  The pinned contract remains authoritative.
            creative_context['skill_impact'] = None
        export = p.get('edit_export')
        if export and export['state'] == 'running' and pid not in store.RUNNING: export = dict(export, state='interrupted')
        review_packet = None; review_error = None
        if spec.get('clips'):
            try: review_packet = build_review(spec, sources, p['aspect'])
            except (ValueError, TypeError, KeyError): review_error = '当前素材或草稿需要先修复，暂不能生成审阅清单。'
        saved_review = p.get('edit_review')
        if saved_review and review_packet and (saved_review.get('revision') != p['revision'] or saved_review.get('document_sha256') != review_packet['document_sha256']):
            saved_review = None
        scene_retake_context = None
        if scene_retake:
            candidate = p.get('scene_retake_suggestions', {}).get(scene_retake)
            if candidate:
                current_review = p.get('scene_render_review', {})
                intent = p.get('scene_render_intent', {})
                scene_retake_context = {key: candidate.get(key) for key in
                                        ('id', 'state', 'model', 'model_label', 'approval_mode', 'aspect', 'intent',
                                         'segments', 'credits', 'quote_digest', 'scene_revision', 'scene_hash',
                                         'trajectory_sha256', 'artifact_sha256', 'requires_explicit_approval', 'training_eligible')}
                scene_retake_context.update(
                    stale=(candidate.get('scene_hash') != intent.get('scene_hash') or
                           (candidate.get('trajectory_sha256') and candidate.get('trajectory_sha256') != intent.get('trajectory_sha256')) or
                           candidate.get('artifact_sha256') != current_review.get('artifact_sha256')),
                    editor_url=f'/creative/editor?project={pid}&scene_retake={candidate["id"]}')
                linked = [job for job in p.get('edit_retakes', {}).values()
                          if job.get('scene_retake_id') == candidate['id']]
                if linked:
                    job = sorted(linked, key=lambda item: item.get('created_at', 0))[-1]
                    scene_retake_context['candidate'] = scene_candidate_view(p, pid, job)
                scene_retake_context['references'] = scene_reference_views(p, candidate)
        return {'id': pid, 'revision': p['revision'], 'title': p.get('brief', {}).get('product', '剪辑'),
                'source_duration': sources.get('primary', {}).get('duration', 0), 'sources': sources,
                'creative_context': creative_context,
                'edit_versions':p.get('edit_versions',[]),
                'batch_applications': [scene_batch_application_view(item) for item in
                                      list(p.get('edit_batch_applications', {}).values())[-20:]],
                'scene_timeline_applications': [scene_timeline_application_view(item) for item in
                                      list(p.get('scene_timeline_applications', {}).values())[-20:]],
                'aspect': p['aspect'], 'spec': spec, 'export': export, 'warning': warning,
                'edit_capabilities': {'track_mute': True},
                'speech_capability':{k:v for k,v in speech_settings().items() if k!='root'},
                'transcriptions':[transcription_view(p,j,sources) for j in p.get('edit_transcriptions',{}).values()],
                'review': {'packet': review_packet, 'saved': saved_review, 'error': review_error},
                'independent_reviews': p.get('edit_review_requests', {}), 'scene_retake': scene_retake_context,
                'suggestion': suggestion_view(p, p.get('edit_suggestions',{}).get(p.get('edit_suggestion_id')))}

    @app.post('/creative/api/projects/{pid}/edit/scene-timeline-draft')
    async def scene_timeline_draft_route(pid: str, body: SceneTimelineDraftRequest,
                                         authorization: str | None = Header(None)):
        """Return a read-only 3D shot-to-edit plan; no timeline mutation."""
        p = store.load(pid, owner(authorization))
        if p['revision'] != body.revision:
            raise HTTPException(409, '项目版本已变化，请重新生成剪辑轨道草稿')
        sources = await catalog(p)
        try:
            draft, _before, _after = scene_timeline_draft(p, sources, body.scene_hash)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'draft': draft}

    @app.post('/creative/api/projects/{pid}/edit/scene-timeline-apply')
    async def scene_timeline_apply(pid: str, body: SceneTimelineApplyRequest,
                                   authorization: str | None = Header(None)):
        """Apply one confirmed, version-bound 3D timeline draft atomically."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            sources = await catalog(p)
            try:
                draft, before_spec, after_spec = scene_timeline_draft(p, sources, body.scene_hash)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            if draft.get('state') != 'ready' or before_spec is None or after_spec is None:
                raise HTTPException(409, draft.get('reason', '当前剪辑轨道草稿不可应用'))
            if draft.get('base_document_sha256') != body.base_document_sha256:
                raise HTTPException(409, '当前剪辑文档已变化，请重新生成轨道草稿')
            if draft.get('draft_sha256') != body.draft_sha256:
                raise HTTPException(409, '轨道草稿已变化，请重新生成并核对')
            application_id = secrets.token_hex(16)
            revision_before = p['revision']
            p['edit'] = after_spec
            p['revision'] += 1
            record = {
                'id': application_id,
                'revision_before': revision_before,
                'revision_after': p['revision'],
                'scene_hash': draft['scene_hash'],
                'before_document_sha256': document_digest(before_spec),
                'after_document_sha256': document_digest(after_spec),
                'before_spec': deepcopy(before_spec),
                'after_clips': deepcopy(after_spec.get('clips', []))[:32],
                'after_captions': deepcopy(after_spec.get('captions', []))[:64],
                'after_audio': deepcopy(after_spec.get('audio', []))[:64],
                'shots': deepcopy(draft.get('rows', []))[:12],
                'state': 'applied',
                'reversible': True,
                'training_eligible': False,
                'created_at': round(time.time(), 3),
            }
            applications = p.setdefault('scene_timeline_applications', {})
            applications[application_id] = record
            for old_id in list(applications)[:-20]:
                applications.pop(old_id, None)
            store.save(p, uid)
            store.event(p, 'tool', 'edit_scene_timeline_applied')
            return {'revision': p['revision'], 'spec': after_spec,
                    'application': scene_timeline_application_view(record)}

    @app.post('/creative/api/projects/{pid}/edit/scene-timeline-undo')
    async def scene_timeline_undo(pid: str, body: SceneTimelineUndoRequest,
                                  authorization: str | None = Header(None)):
        """Undo only the latest unchanged scene timeline application."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            record = p.get('scene_timeline_applications', {}).get(body.application_id)
            if not isinstance(record, dict) or record.get('state') != 'applied':
                raise HTTPException(404, '找不到可撤销的剪辑轨道应用记录')
            if record.get('revision_after') != body.revision:
                raise HTTPException(409, '项目已继续编辑，暂不能安全撤销这次应用')
            if document_digest(p.get('edit') or {}) != record.get('after_document_sha256'):
                raise HTTPException(409, '当前剪辑文档已变化，暂不能安全撤销')
            sources = await catalog(p)
            try:
                restored = validate_edit(record.get('before_spec'), catalog=sources)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(409, '撤销所需的原素材已变化，请保留当前版本') from exc
            p['edit'] = restored
            p['revision'] += 1
            record['state'] = 'undone'
            record['reversible'] = False
            record['undo_revision'] = p['revision']
            store.save(p, uid)
            store.event(p, 'tool', 'edit_scene_timeline_undone')
            return {'revision': p['revision'], 'spec': restored,
                    'application': scene_timeline_application_view(record)}

    @app.get('/creative/api/projects/{pid}/edit/source')
    @app.get('/creative/api/projects/{pid}/edit/sources/{sid}')
    def edit_source(pid: str, sid: str = 'primary', authorization: str | None = Header(None)):
        try: path = source_path(store.load(pid, owner(authorization)), sid)
        except ValueError as exc: raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, media_type='audio/mp4' if path.suffix == '.m4a' else 'video/mp4')

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-review')
    async def save_scene_candidate_review(pid: str, body: SceneCandidateReviewRequest,
                                          authorization: str | None = Header(None)):
        """Save a human seam review for one completed 3D-bound retake candidate.

        This is an evaluator observation only: it never applies the candidate,
        starts a runner, changes the edit document, or grants training status.
        """
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            job = p.get('edit_retakes', {}).get(body.candidate_id)
            if not job or not job.get('scene_retake_id'):
                raise HTTPException(404, '找不到绑定 3D 建议的候选')
            if job.get('state') != 'completed' or not job.get('asset') or not job.get('candidate_sha256'):
                raise HTTPException(409, '候选尚未完成，暂不能记录接缝核对')
            candidate_revision = job.get('completed_revision', job.get('revision'))
            if candidate_revision != body.revision:
                raise HTTPException(409, '剪辑版本已变化，请重新打开候选核对')
            checks = body.checks.model_dump()
            review = {
                'candidate_id': body.candidate_id,
                'scene_retake_id': job['scene_retake_id'],
                'revision': candidate_revision,
                'candidate_sha256': job['candidate_sha256'],
                'checks': checks,
                'note': body.note.strip(),
                'created_at': round(time.time(), 3),
                'training_eligible': False,
            }
            stable = {key: review[key] for key in review if key != 'created_at'}
            review['receipt_sha256'] = hashlib.sha256(
                json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            ).hexdigest()
            current = job.get('candidate_review')
            stable_keys = ('candidate_id', 'scene_retake_id', 'revision', 'candidate_sha256', 'checks', 'note', 'training_eligible', 'receipt_sha256')
            if isinstance(current, dict) and all(current.get(key) == review.get(key) for key in stable_keys):
                return {'review': current, 'candidate': scene_candidate_view(p, pid, job)}
            job['candidate_review'] = review
            store.save(p, uid)
            store.event(p, 'evaluator', 'edit_scene_candidate_review_recorded')
            return {'review': review, 'candidate': scene_candidate_view(p, pid, job)}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-plan')
    def scene_retake_batch_plan(pid: str, body: SceneCandidateBatchPlanRequest,
                                authorization: str | None = Header(None)):
        """Build a read-only per-shot plan; it never reserves credits or submits work."""
        p = store.load(pid, owner(authorization))
        if p['revision'] != body.revision:
            raise HTTPException(409, '项目版本已变化，请重新打开批量候选计划')
        plan = scene_candidate_batch_plan(p, pid, body.scene_retake_id)
        if plan is None:
            raise HTTPException(404, '找不到 3D 重拍建议')
        return {'plan': plan}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-receipt')
    def scene_retake_batch_receipt(pid: str, body: SceneCandidateBatchReceiptRequest,
                                   authorization: str | None = Header(None)):
        """Read existing per-shot states without creating or retrying work."""
        p = store.load(pid, owner(authorization))
        if p['revision'] != body.revision:
            raise HTTPException(409, '项目版本已变化，请重新打开批量执行回执')
        receipt = scene_candidate_batch_receipt(p, pid, body.scene_retake_id)
        if receipt is None:
            raise HTTPException(404, '找不到 3D 重拍建议')
        return {'receipt': receipt}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-apply-draft')
    def scene_retake_batch_apply_draft(pid: str, body: SceneCandidateBatchApplyDraftRequest,
                                       authorization: str | None = Header(None)):
        """Build a reversible apply proposal; never mutates the timeline."""
        p = store.load(pid, owner(authorization))
        if p['revision'] != body.revision:
            raise HTTPException(409, '项目版本已变化，请重新打开批量应用草稿')
        draft = scene_candidate_batch_apply_draft(p, pid, body.scene_retake_id)
        if draft is None:
            raise HTTPException(404, '找不到 3D 重拍建议')
        return {'draft': draft}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-apply-check')
    def scene_retake_batch_apply_check(pid: str, body: SceneCandidateBatchApplyCheckRequest,
                                       authorization: str | None = Header(None)):
        """Re-check draft inputs; even a clean check cannot apply the draft."""
        p = store.load(pid, owner(authorization))
        if p['revision'] != body.revision:
            raise HTTPException(409, '项目版本已变化，请重新生成应用草稿')
        result = scene_candidate_batch_apply_check(p, pid, body)
        if result is None:
            raise HTTPException(404, '找不到 3D 重拍建议')
        return {'check': result}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-apply')
    async def scene_retake_batch_apply(pid: str, body: SceneCandidateBatchApplyRequest,
                                       authorization: str | None = Header(None)):
        """Atomically apply a reviewed batch draft and retain one undo record."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            check = scene_candidate_batch_apply_check(p, pid, body)
            if check is None:
                raise HTTPException(404, '找不到 3D 重拍建议')
            if not check['safe_to_apply']:
                raise HTTPException(409, {'message': '批量应用草稿已变化，请重新生成并核对',
                                          'conflicts': check['conflicts']})
            draft = scene_candidate_batch_apply_draft(p, pid, body.scene_retake_id)
            if not draft or draft['state'] != 'ready':
                raise HTTPException(409, '没有可应用的候选镜头')
            before_digest = document_digest(p.get('edit') or {})
            if before_digest != body.base_document_sha256:
                raise HTTPException(409, '当前剪辑文档已变化，请重新生成应用草稿')
            try:
                sources = await catalog(p)
                spec = validated(p.get('edit') or {}, sources)
            except HTTPException:
                raise
            before_spec = deepcopy(spec)
            jobs = {job.get('id'): job for job in p.get('edit_retakes', {}).values()
                    if isinstance(job, dict) and job.get('scene_retake_id') == body.scene_retake_id}
            for row in draft['rows']:
                if row['eligibility'] != 'ready':
                    continue
                job = jobs.get(row.get('candidate_id'))
                asset_id = job.get('asset') if isinstance(job, dict) else None
                if not isinstance(job, dict) or not asset_id or asset_id not in sources:
                    raise HTTPException(409, '候选素材已变化，请重新生成应用草稿')
                index = row.get('target_clip_index')
                if not isinstance(index, int) or index < 0 or index >= len(spec.get('clips', [])):
                    raise HTTPException(409, '目标片段已变化，请重新生成应用草稿')
                clip = job.get('clip') if isinstance(job.get('clip'), dict) else {}
                duration = job.get('duration')
                if not isinstance(duration, (int, float)) or duration <= 0:
                    start, end = clip.get('start'), clip.get('end')
                    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                        duration = end - start
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise HTTPException(409, '候选素材缺少有效时长，请重新生成应用草稿')
                spec['sources'][asset_id] = sources[asset_id]['sha256']
                spec['clips'][index] = dict(clip, source=asset_id, start=0, end=duration)
            try:
                after_spec = validated(spec, sources)
            except HTTPException:
                raise
            application_id = secrets.token_hex(16)
            revision_before = p['revision']
            p['edit'] = after_spec
            p['revision'] += 1
            record = {
                'id': application_id,
                'scene_retake_id': body.scene_retake_id,
                'revision_before': revision_before,
                'revision_after': p['revision'],
                'candidate_ids': list(body.candidate_ids),
                'before_document_sha256': before_digest,
                'after_document_sha256': document_digest(after_spec),
                'before_spec': before_spec,
                'before_clips': deepcopy(before_spec.get('clips', []))[:32],
                'after_clips': deepcopy(after_spec.get('clips', []))[:32],
                'before_captions': deepcopy(before_spec.get('captions', []))[:64],
                'after_captions': deepcopy(after_spec.get('captions', []))[:64],
                'before_audio': deepcopy(before_spec.get('audio', []))[:64],
                'after_audio': deepcopy(after_spec.get('audio', []))[:64],
                'state': 'applied',
                'reversible': True,
                'training_eligible': False,
                'created_at': round(time.time(), 3),
            }
            # The source clip snapshot is restored through before_spec only; no
            # provider payload, capability or private path is stored in the receipt.
            p.setdefault('edit_batch_applications', {})[application_id] = record
            store.save(p, uid)
            store.event(p, 'tool', 'edit_scene_batch_applied')
            return {'revision': p['revision'], 'spec': after_spec,
                    'application': scene_batch_application_view(record)}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-undo')
    async def scene_retake_batch_undo(pid: str, body: SceneCandidateBatchUndoRequest,
                                      authorization: str | None = Header(None)):
        """Undo one applied batch only when the current document is unchanged."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            record = p.get('edit_batch_applications', {}).get(body.application_id)
            if not isinstance(record, dict) or record.get('state') != 'applied':
                raise HTTPException(404, '找不到可撤销的批量应用')
            if record.get('revision_after') != body.revision:
                raise HTTPException(409, '项目版本已变化，请重新打开批量应用记录')
            if document_digest(p.get('edit') or {}) != record.get('after_document_sha256'):
                raise HTTPException(409, '当前剪辑已被修改，不能覆盖现有更改；请保留原草稿手动处理')
            try:
                restored = validated(record.get('before_spec') or {}, await catalog(p))
            except HTTPException:
                raise
            p['edit'] = restored
            p['revision'] += 1
            record['state'] = 'undone'
            record['undo_revision'] = p['revision']
            store.save(p, uid)
            store.event(p, 'tool', 'edit_scene_batch_undone')
            return {'revision': p['revision'], 'spec': restored,
                    'application': scene_batch_application_view(record)}

    @app.post('/creative/api/projects/{pid}/edit/scene-retake-batch-approval')
    async def save_scene_batch_approval(pid: str, body: SceneBatchApprovalRequest,
                                        authorization: str | None = Header(None)):
        """Save a version-bound per-shot approval packet without submitting generation."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, body.revision)
            suggestion = p.get('scene_retake_suggestions', {}).get(body.scene_retake_id)
            if not isinstance(suggestion, dict) or suggestion.get('state') != 'approved_for_generation':
                raise HTTPException(409, '3D 重拍建议尚未确认费用，请先回放核对')
            intent = p.get('scene_render_intent', {})
            render_review = p.get('scene_render_review', {})
            if suggestion.get('scene_hash') != intent.get('scene_hash') or suggestion.get('artifact_sha256') != render_review.get('artifact_sha256'):
                raise HTTPException(409, '3D 场景或成片已变化，请重新准备批量计划')
            expected = [str(segment.get('shot_id') or '') for segment in suggestion.get('segments', [])[:12]
                        if isinstance(segment, dict)]
            submitted = [shot.shot_id for shot in body.shots]
            if len(set(submitted)) != len(submitted) or set(submitted) != set(expected):
                raise HTTPException(422, '请为批量计划中的每个镜头提交一次审批决定')
            shots = [next(shot.model_dump() for shot in body.shots if shot.shot_id == shot_id)
                     for shot_id in expected]
            approval = {
                'scene_retake_id': body.scene_retake_id,
                'revision': body.revision,
                'scene_hash': suggestion.get('scene_hash'),
                'artifact_sha256': suggestion.get('artifact_sha256'),
                'shots': shots,
                'training_eligible': False,
            }
            stable = dict(approval)
            approval['receipt_sha256'] = hashlib.sha256(
                json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            ).hexdigest()
            current = p.get('scene_retake_batch_approvals', {}).get(body.scene_retake_id)
            stable_keys = ('scene_retake_id', 'revision', 'scene_hash', 'artifact_sha256', 'shots', 'training_eligible', 'receipt_sha256')
            if isinstance(current, dict) and all(current.get(key) == approval.get(key) for key in stable_keys):
                return {'approval': current, 'plan': scene_candidate_batch_plan(p, pid, body.scene_retake_id)}
            p.setdefault('scene_retake_batch_approvals', {})[body.scene_retake_id] = approval
            store.save(p, uid)
            store.event(p, 'evaluator', 'edit_scene_batch_approval_recorded')
            return {'approval': approval, 'plan': scene_candidate_batch_plan(p, pid, body.scene_retake_id)}

    @app.get('/creative/api/projects/{pid}/edit/sources/{sid}/waveform')
    async def source_waveform(pid: str, sid: str, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization))
        async with analysis_slots:
            try: return await asyncio.to_thread(waveform, p, sid)
            except ValueError as exc: raise HTTPException(404, str(exc)) from exc
            except Exception: raise HTTPException(422, '暂不能分析此素材音轨')

    @app.get('/creative/api/projects/{pid}/edit/assets/lookup')
    def lookup_upload(pid: str, upload_digest: str, authorization: str | None = Header(None)):
        """Recover an import whose HTTP response was lost after the server saved it.

        The digest is a client supplied idempotency key, but is only used as a
        lookup key here; the upload endpoint verifies it against the received
        bytes before saving anything.
        """
        if not re.fullmatch(r'[a-f0-9]{64}', upload_digest):
            raise HTTPException(422, '素材校验标识无效')
        p = store.load(pid, owner(authorization))
        for aid, asset in p.get('edit_assets', {}).items():
            if asset.get('upload_sha256') == upload_digest:
                return {'revision': p['revision'],
                        'source': dict(asset, id='edit_' + aid, title=asset['label'])}
        raise HTTPException(404, '找不到这次导入记录')

    @app.post('/creative/api/projects/{pid}/edit/assets')
    async def upload(pid: str, request: Request, revision: int, kind: str, label: str = '',
                     upload_digest: str | None = Header(None, alias='X-Upload-Digest'),
                     authorization: str | None = Header(None)):
        uid = owner(authorization)
        if kind not in ('video', 'audio'): raise HTTPException(422, '请选择视频或音频')
        if upload_digest is not None and not re.fullmatch(r'[a-f0-9]{64}', upload_digest):
            raise HTTPException(422, '素材校验标识无效')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_EDIT_UPLOAD: raise HTTPException(413, '素材不可超过 60 MB')
        actual_digest = hashlib.sha256(raw).hexdigest()
        if upload_digest is not None and upload_digest != actual_digest:
            raise HTTPException(422, '素材传输校验失败，请重新选择文件')
        async with store.lock(pid):
            p = store.load(pid, uid)
            for aid, existing in p.get('edit_assets', {}).items():
                if upload_digest is not None and existing.get('upload_sha256') == upload_digest:
                    return {'revision': p['revision'],
                            'source': dict(existing, id='edit_' + aid, title=existing['label'])}
            writable(p, revision)
            if len(p.get('edit_assets', {})) >= 24: raise HTTPException(422, '每个项目最多导入 24 个剪辑素材')
            async with analysis_slots:
                try: asset = await asyncio.to_thread(save_upload, p, raw, kind, label)
                except ValueError as exc: raise HTTPException(422, str(exc)) from exc
            if upload_digest is not None: asset['upload_sha256'] = upload_digest
            p.setdefault('edit_assets', {})[asset['id']] = asset
            p['revision'] += 1; store.save(p, uid); store.event(p, 'tool', 'edit_asset_imported')
            return {'revision': p['revision'], 'source': dict(asset, id='edit_'+asset['id'], title=asset['label'])}

    @app.put('/creative/api/projects/{pid}/edit')
    async def save_document(pid: str, body: EditDocument, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, body.revision)
            p['edit'] = validated(body.spec, await catalog(p))
            p['revision'] += 1; store.save(p, uid); store.event(p, 'tool', 'edit_saved')
            return {'revision': p['revision'], 'spec': p['edit']}

    @app.post('/creative/api/projects/{pid}/edit/suggestions')
    async def suggest(pid: str, body: SuggestionRequest, authorization: str | None = Header(None)):
        uid=owner(authorization)
        fingerprint=hashlib.sha256(json.dumps([body.revision,body.intent],ensure_ascii=False).encode()).hexdigest()
        async with store.lock(pid):
            p=store.load(pid,uid);jobs=p.setdefault('edit_suggestions',{})
            if body.request_id in jobs:
                job=jobs[body.request_id]
                if job['request_digest']!=fingerprint: raise HTTPException(409,'同一个请求标识不能更改参数')
                return suggestion_view(p,job)
            writable(p,body.revision)
            if not p.get('edit'): raise HTTPException(409,'请先保存当前剪辑')
            if not body.intent.strip(): raise HTTPException(422,'请写明剪辑目标')
            original=validated(p['edit'],await catalog(p))
            if len({c['source'] for c in original['clips']})>MAX_SOURCES: raise HTTPException(422,'一次建议最多分析 6 个视频来源')
            if len(jobs)>=100: raise HTTPException(422,'此项目已达到 100 次剪辑建议上限')
            job={'id':body.request_id,'revision':p['revision'],'request_digest':fingerprint,'state':'running',
                 'base_digest':hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()}
            jobs[job['id']]=job;p['edit_suggestion_id']=job['id'];store.save(p,uid)
            store.event(p,'agent','edit_suggestion_requested')
            store.RUNNING[pid]=asyncio.create_task(run_suggestion(pid,uid,job['id'],dict(p,edit=original),body.intent,analysis_slots))
            return suggestion_view(p,job)

    @app.get('/creative/api/projects/{pid}/edit/suggestions/{job_id}')
    def suggestion(pid: str, job_id: str, authorization: str | None = Header(None)):
        p=store.load(pid,owner(authorization));job=p.get('edit_suggestions',{}).get(job_id)
        if not job: raise HTTPException(404,'找不到剪辑建议')
        return suggestion_view(p,job)

    def transcription_view(p,job,sources):
        result=dict(job,stale=sources.get(job['source'],{}).get('sha256')!=job['source_sha256'])
        if job['state']=='running' and p['id'] not in store.RUNNING:
            result.update(state='interrupted',error='识别曾中断，请明确重新请求。')
        return result

    @app.post('/creative/api/projects/{pid}/edit/transcriptions')
    async def transcribe(pid: str,body: TranscriptionRequest,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid);sources=await catalog(p);jobs=p.setdefault('edit_transcriptions',{})
            if body.request_id in jobs:
                job=jobs[body.request_id]
                if (job['revision'],job['source'],job['language'])!=(body.revision,body.source,body.language):raise HTTPException(409,'同一个识别请求不能改变参数')
                return transcription_view(p,job,sources)
            writable(p,body.revision)
            if not speech_settings()['available']:raise HTTPException(503,'口播识别尚未配置')
            if body.language not in LANGUAGES:raise HTTPException(422,'不支持此识别语言')
            source=sources.get(body.source)
            if not source:raise HTTPException(404,'找不到项目素材')
            if not source['has_audio']:raise HTTPException(422,'素材没有音轨')
            if len(jobs)>=100:raise HTTPException(422,'本项目最多保留 100 次识别记录')
            job={'id':body.request_id,'revision':p['revision'],'source':body.source,'source_sha256':source['sha256'],
                 'language':body.language,'model':speech_settings()['model'],'state':'running'}
            jobs[job['id']]=job;store.save(p,uid);store.event(p,'tool','edit_speech_requested')
            store.RUNNING[pid]=asyncio.create_task(run_transcription(pid,uid,job['id'],p,speech_slots))
            return transcription_view(p,job,sources)

    @app.get('/creative/api/projects/{pid}/edit/transcriptions/{job_id}')
    async def transcription(pid:str,job_id:str,authorization:str|None=Header(None)):
        p=store.load(pid,owner(authorization));job=p.get('edit_transcriptions',{}).get(job_id)
        if not job:raise HTTPException(404,'找不到识别记录')
        return transcription_view(p,job,await catalog(p))

    @app.post('/creative/api/projects/{pid}/edit/caption-plan')
    async def captions_from_speech(pid:str,body:EditDocument,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid);writable(p,body.revision)
            try:return caption_plan(p,body.spec,await catalog(p))
            except (ValueError,TypeError,KeyError) as exc:raise HTTPException(422,str(exc)) from exc

    @app.get('/creative/api/projects/{pid}/edit/review')
    async def review_document(pid: str, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization)); sources = await catalog(p)
        spec = p.get('edit') or initial_edit(p, catalog=sources)
        if not spec.get('clips'): raise HTTPException(409, '请先保存至少一段画面')
        try: packet = await asyncio.to_thread(build_review, spec, sources, p['aspect'])
        except (ValueError, TypeError, KeyError) as exc: raise HTTPException(422, str(exc)) from exc
        saved = p.get('edit_review')
        if saved and (saved.get('revision') != p['revision'] or saved.get('document_sha256') != packet['document_sha256']): saved = None
        return {'packet': packet, 'saved': saved}

    @app.post('/creative/api/projects/{pid}/edit/review')
    async def save_review(pid: str, body: ReviewRequest, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, body.revision); sources = await catalog(p)
            if not p.get('edit') or not p['edit'].get('clips'): raise HTTPException(409, '请先保存至少一段画面')
            try: packet = await asyncio.to_thread(build_review, p['edit'], sources, p['aspect'])
            except (ValueError, TypeError, KeyError) as exc: raise HTTPException(422, str(exc)) from exc
            technical_ok = all(v['status'] == 'passed' for v in packet['technical'].values())
            checks = body.checks.model_dump()
            if body.decision == 'approved' and (not technical_ok or not all(checks.values())):
                raise HTTPException(422, '标记为已核对前，请通过技术检查并勾选完整观看、听音和商品事实核对')
            record = dict(packet, revision=p['revision'], decision=body.decision, human=checks,
                          note=body.note.strip(), reviewed_at=round(time.time(), 3))
            record['receipt_sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            p['edit_review'] = record
            p.setdefault('edit_review_history', []).append(record); p['edit_review_history'] = p['edit_review_history'][-50:]
            store.save(p, uid); store.event(p, 'evaluator', 'edit_review_recorded')
            return {'packet': packet, 'saved': record}

    @app.post('/creative/api/projects/{pid}/edit/review/request')
    async def request_independent_review(pid: str, body: IndependentReviewRequest,
                                         authorization: str | None = Header(None)):
        """Hand one immutable export to a different reviewer.

        The owner-facing review is a prerequisite, but it never becomes an
        independent quality label.  The request stores only bounded packet
        metadata and the export digest; the reviewer must fetch the media from
        the admin-scoped endpoint and submit a separate receipt.
        """
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            if p['revision'] != body.revision:
                raise HTTPException(409, '项目已更新，请重新打开剪辑')
            export = edit_review.export_record(p, body.export_id)
            if not export:
                raise HTTPException(404, '找不到已完成的剪辑版本')
            try:
                _path, artifact = edit_review.export_path(p, export)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            owner_review = p.get('edit_review') or {}
            checks = owner_review.get('human') or {}
            if (owner_review.get('revision') != p['revision'] or
                    owner_review.get('decision') != 'approved' or
                    not all(checks.get(k) is True for k in ('full_video_watched', 'audio_listened', 'product_facts_checked'))):
                raise HTTPException(422, '请先完成当前剪辑的全片人工核对，再申请独立审阅')
            previous = p.setdefault('edit_review_requests', {}).get(body.export_id)
            if previous and previous.get('artifact_sha256') == artifact:
                return {'request': previous, 'training_eligible': False}
            request = {
                'export_id': export['id'], 'revision': export.get('revision'),
                'requested_revision': p['revision'], 'artifact_sha256': artifact,
                'document_sha256': export.get('document_sha256'),
                'status': 'pending_independent_review',
                'content_tasks': owner_review.get('content_tasks', []),
                'requested_at': round(time.time(), 3), 'training_eligible': False,
            }
            p['edit_review_requests'][body.export_id] = request
            store.save(p, uid); store.event(p, 'evaluator', 'edit_independent_review_requested')
            return {'request': request, 'training_eligible': False}

    async def render_job(pid, uid, job):
        try:
            p = store.load(pid, uid); directory = store.DATA/'edits'/pid/job['id']
            qa = await asyncio.to_thread(render_edit, p, p['edit'], directory)
            async with store.lock(pid):
                p = store.load(pid, uid); p['edit_export'].update(state='completed', qa=qa, artifact_sha256=digest(directory/'final.mp4'))
                if (directory/'edit.json').is_file():p['edit_export']['document_sha256']=digest(directory/'edit.json')
                p.setdefault('edit_versions', []).append(dict(p['edit_export']))
                store.save(p, uid); store.event(p, 'evaluator', 'edit_export_passed')
        except Exception:
            async with store.lock(pid):
                p = store.load(pid, uid); p['edit_export'].update(state='failed', error='导出未通过检查，源素材与草稿保留，可明确重新导出。')
                store.save(p, uid); store.event(p, 'tool', 'edit_export_failed')
        finally: store.RUNNING.pop(pid, None)

    @app.post('/creative/api/projects/{pid}/edit/export')
    async def export(pid: str, body: Export, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, body.revision)
            if not p.get('edit'): raise HTTPException(409, '请先保存剪辑')
            validated(p['edit'], await catalog(p))
            job = {'id': secrets.token_hex(16), 'revision': p['revision'], 'state': 'running'}
            p['edit_export'] = job; store.save(p, uid); store.event(p, 'tool', 'edit_export_started')
            store.RUNNING[pid] = asyncio.create_task(render_job(pid, uid, job))
            return job

    @app.post('/creative/api/projects/{pid}/edit/exports/{job_id}/canvas')
    async def export_to_canvas(pid:str,job_id:str,body:Export,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid);writable(p,body.revision)
            job=next((j for j in p.get('edit_versions',[]) if j['id']==job_id),None)
            if not job:raise HTTPException(404,'找不到已完成的剪辑版本')
            try:updated,aid,changed=await asyncio.to_thread(publish_export,p,job)
            except (ValueError,OSError,KeyError) as exc:raise HTTPException(422,'暂不能回到画布：'+str(exc) if isinstance(exc,ValueError) else '导出版本或来源文件不完整') from exc
            if changed:
                updated['revision']+=1;store.save(updated,uid);store.event(updated,'tool','edit_export_added_to_canvas')
            return {'revision':updated['revision'],'asset':aid,'url':'/creative?project='+pid+'&view=canvas'}

    @app.get('/creative/api/projects/{pid}/edit/media')
    def exported(pid: str, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization)); job = p.get('edit_export', {})
        if job.get('state') != 'completed': raise HTTPException(404, '剪辑导出尚未完成')
        return FileResponse(store.DATA/'edits'/pid/job['id']/'final.mp4', media_type='video/mp4', filename='VisualAgent-edit.mp4')
