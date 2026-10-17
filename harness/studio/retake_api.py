"""Owner-scoped preview → explicit budget approval → candidate → draft."""
import asyncio
import json
import re
import secrets
import shutil
import time
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from harness.studio import store
from harness.core.creative_retake_runner import run_retake
from harness.tools.creative_retake import prepare, document_digest, candidate_plan, directory, payload
from harness.models.video_catalog import quote
from harness.models.kling_retake import MODEL, spool_root
import math
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_media import source_catalog, digest
from harness.models.kling_retake import input_path


class Prepare(BaseModel):
    revision: int
    clip_index: int = Field(ge=0, le=31)
    intent: str = Field(min_length=1, max_length=1600)
    scene_retake_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class Approve(BaseModel):
    revision: int
    quote_digest: str = Field(pattern='^[a-f0-9]{64}$')
    approved_credits: int = Field(ge=1, le=8)


class Adopt(BaseModel):
    revision: int


class BatchSubmit(BaseModel):
    revision: int
    scene_retake_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    approval_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    shot_ids: list[str] = Field(min_length=1, max_length=12)
    approved_credits: int = Field(ge=1, le=96)
    confirm: str = Field(pattern=r'^submit$')


def install(gateway):
    app = gateway.app
    slots = asyncio.Semaphore(2)
    def owner(auth): return gateway.require_session(auth)['id']
    def find(pid, uid, jid):
        p = store.load(pid, uid); job = p.get('edit_retakes', {}).get(jid)
        if not job: raise HTTPException(404, '找不到重拍任务')
        return p, job
    def writable(p, revision):
        if p['revision'] != revision or p['id'] in store.RUNNING or p['state'] in ('planning', 'running', 'rendering'):
            raise HTTPException(409, '项目已更新或正在处理，请重新打开剪辑')
    def view(p, job):
        result = {k: v for k, v in job.items() if k != 'provider_job_id'}
        # This public view contains no capability, original path, credentials or provider payload.
        result['project_revision'] = p['revision']
        result['stale'] = document_digest(p.get('edit', {})) != job['base_digest']
        if job['state'] == 'submitting' and p['id'] not in store.RUNNING:
            result.update(state='needs_review', error='提交曾中断，结果待核对；没有重复生成。')
        return result

    def batch_view(p, queue):
        """Bounded execution receipt; never exposes provider or filesystem data."""
        jobs = p.get('edit_retakes', {})
        rows = []
        for jid in queue.get('job_ids', [])[:12]:
            job = jobs.get(jid)
            if not isinstance(job, dict):
                continue
            rows.append({key: job.get(key) for key in (
                'id', 'scene_shot_id', 'state', 'credits', 'approved_credits',
                'asset', 'candidate_sha256', 'completed_revision', 'qa',
                'training_eligible', 'error')})
        result = {key: queue.get(key) for key in (
            'id', 'scene_retake_id', 'state', 'revision', 'base_document_sha256',
            'approval_receipt_sha256', 'shot_ids', 'job_ids', 'total_credits',
            'approved_credits', 'current_index', 'completed_count', 'error',
            'training_eligible', 'created_at')}
        result['jobs'] = rows
        result['project_revision'] = p['revision']
        if result.get('state') in ('queued', 'running') and p['id'] not in store.RUNNING:
            result['state'] = 'needs_review'
            result['error'] = '批量队列曾中断；已提交镜头和未提交镜头均保留，没有自动重试。'
        return result

    def _cleanup_prepared(pid, jid):
        """Remove an unpersisted preparation, including its private spool file."""
        folder = directory(pid, jid)
        try:
            private = json.loads((folder / 'input.json').read_text())
            reference = private.get('reference')
        except Exception:
            reference = None
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(reference, str) and re.fullmatch(r'[a-f0-9]{64}', reference):
            shutil.rmtree(spool_root() / reference, ignore_errors=True)

    def _batch_context(p, body):
        """Validate the immutable scene approval and return selected segments."""
        suggestion = p.get('scene_retake_suggestions', {}).get(body.scene_retake_id)
        if not isinstance(suggestion, dict) or suggestion.get('state') != 'approved_for_generation':
            raise HTTPException(409, '3D 重拍建议尚未确认费用，请先回放核对页确认')
        if suggestion.get('model') != MODEL:
            raise HTTPException(409, '当前批量重拍需要已接入的 Kling O3；请在创作入口选择 Kling O3 后重新生成报价')
        if (suggestion.get('scene_hash') != p.get('scene_render_intent', {}).get('scene_hash') or
                (suggestion.get('trajectory_sha256') and suggestion.get('trajectory_sha256') != p.get('scene_render_intent', {}).get('trajectory_sha256')) or
                suggestion.get('artifact_sha256') != p.get('scene_render_review', {}).get('artifact_sha256')):
            raise HTTPException(409, '3D 场景或成片已变化，请重新准备批量计划')
        approval = p.get('scene_retake_batch_approvals', {}).get(body.scene_retake_id)
        if not isinstance(approval, dict) or approval.get('revision') != body.revision:
            raise HTTPException(409, '逐镜头审批已过期，请重新保存批量审批')
        if approval.get('scene_hash') != suggestion.get('scene_hash') or approval.get('artifact_sha256') != suggestion.get('artifact_sha256'):
            raise HTTPException(409, '批量审批对应的场景或成片已变化，请重新保存')
        if approval.get('receipt_sha256') != body.approval_receipt_sha256:
            raise HTTPException(409, '审批回执已变化，请重新核对每个镜头')
        requested = list(body.shot_ids)
        if len(set(requested)) != len(requested):
            raise HTTPException(422, '同一镜头只能提交一次')
        approval_rows = {str(item.get('shot_id')): item for item in approval.get('shots', [])
                         if isinstance(item, dict)}
        segments = {str(item.get('shot_id')): item for item in suggestion.get('segments', [])[:12]
                    if isinstance(item, dict) and item.get('shot_id')}
        if any(shot_id not in segments for shot_id in requested):
            raise HTTPException(422, '提交的镜头不属于当前 3D 批量计划')
        if any(approval_rows.get(shot_id, {}).get('decision') != 'approved' for shot_id in requested):
            raise HTTPException(409, '只能提交已明确批准的镜头；待核对或阻断镜头不会自动生成')
        selected = [segments[shot_id] for shot_id in requested]
        if any(not isinstance(item.get('credits'), int) or item.get('credits') < 1 for item in selected):
            raise HTTPException(409, '批量报价缺少有效积分，请重新生成建议')
        if sum(item['credits'] for item in selected) != body.approved_credits:
            raise HTTPException(409, '确认积分与逐镜头报价不一致，请重新核对')
        return suggestion, approval, selected

    async def run_batch(pid, uid, queue_id, app, authorization):
        task = asyncio.current_task()
        try:
            queue = None
            while True:
                async with store.lock(pid):
                    p = store.load(pid, uid)
                    queue = p.get('edit_retake_batches', {}).get(queue_id)
                    if not isinstance(queue, dict):
                        return
                    index = int(queue.get('current_index', 0))
                    job_ids = queue.get('job_ids', [])
                    if index >= len(job_ids):
                        queue['state'] = 'completed'; queue['current_job_id'] = None
                        store.save(p, uid); store.event(p, 'evaluator', 'edit_retake_batch_completed')
                        return
                    jid = job_ids[index]
                    job = p.get('edit_retakes', {}).get(jid)
                    if not isinstance(job, dict):
                        queue.update(state='needs_review', error='批量任务缺少已冻结的镜头输入。')
                        store.save(p, uid); store.event(p, 'evaluator', 'edit_retake_batch_needs_review')
                        return
                    if job.get('state') == 'completed':
                        queue.update(current_index=index + 1, completed_count=index + 1)
                        store.save(p, uid)
                        continue
                    if job.get('state') != 'ready':
                        queue.update(state='needs_review', current_job_id=jid,
                                     error='镜头提交状态无法确认，未自动重试。')
                        store.save(p, uid); store.event(p, 'evaluator', 'edit_retake_batch_needs_review')
                        return
                    job.update(state='submitting', approved_credits=job['credits'])
                    queue.update(state='running', current_job_id=jid)
                    store.save(p, uid); store.event(p, 'runner', 'edit_retake_batch_shot_submitting', job.get('scene_shot_id', ''))
                await run_retake(pid, uid, jid, app, authorization, submit=True, keep_running=True)
                async with store.lock(pid):
                    p = store.load(pid, uid)
                    queue = p.get('edit_retake_batches', {}).get(queue_id)
                    job = p.get('edit_retakes', {}).get(jid)
                    if not isinstance(queue, dict) or not isinstance(job, dict):
                        return
                    if job.get('state') != 'completed':
                        failed_state = 'failed' if job.get('state') == 'failed' else 'needs_review'
                        queue.update(state=failed_state, error=job.get('error') or '镜头结果待核对，队列已停止；没有自动重试。')
                        store.save(p, uid); store.event(p, 'evaluator', 'edit_retake_batch_' + failed_state)
                        return
                    queue.update(current_index=index + 1, completed_count=index + 1)
                    store.save(p, uid)
                    if index + 1 >= len(queue.get('job_ids', [])):
                        queue.update(state='completed', current_job_id=None)
                        store.save(p, uid); store.event(p, 'evaluator', 'edit_retake_batch_completed')
                        return
        except Exception:
            try:
                async with store.lock(pid):
                    p = store.load(pid, uid); queue = p.get('edit_retake_batches', {}).get(queue_id)
                    if isinstance(queue, dict):
                        queue.update(state='needs_review', error='批量查询暂时中断，已保留已提交镜头；没有自动重试。')
                        store.save(p, uid); store.event(p, 'observation', 'edit_retake_batch_needs_review')
            except Exception:
                pass
        finally:
            if store.RUNNING.get(pid) is task:
                store.RUNNING.pop(pid, None)

    def approved_scene_retake(p, suggestion_id):
        if not suggestion_id:
            return None
        suggestion = p.get('scene_retake_suggestions', {}).get(suggestion_id)
        if not suggestion or suggestion.get('state') != 'approved_for_generation':
            raise HTTPException(409, '3D 重拍建议尚未确认费用，请先回放核对页确认')
        intent = p.get('scene_render_intent', {})
        review = p.get('scene_render_review', {})
        if (suggestion.get('scene_hash') != intent.get('scene_hash') or
                (suggestion.get('trajectory_sha256') and suggestion.get('trajectory_sha256') != intent.get('trajectory_sha256')) or
                suggestion.get('artifact_sha256') != review.get('artifact_sha256')):
            raise HTTPException(409, '3D 场景或成片已变化，请重新准备重拍建议')
        return suggestion

    @app.get('/creative/editor-retake.js', include_in_schema=False)
    def script():
        return FileResponse(store.ROOT / 'tools/agent_studio/editor-retake.js', headers={'Cache-Control': 'no-store'})

    @app.post('/creative/api/projects/{pid}/edit/retakes/preview')
    async def preview(pid: str, body: Prepare, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, body.revision)
            suggestion = approved_scene_retake(p, body.scene_retake_id)
            if suggestion:
                try:
                    spec = validate_edit(p.get('edit', {}), catalog=source_catalog(p))
                    clip = spec['clips'][body.clip_index]
                    if not any(clip.get('source') == 'primary' and clip['start'] <= segment['start'] and clip['end'] >= segment['end']
                               for segment in suggestion.get('segments', [])):
                        raise HTTPException(409, '当前片段没有覆盖 3D 重拍建议的镜头时间窗，请先定位或调整剪辑')
                except HTTPException:
                    raise
                except (KeyError, TypeError, ValueError) as exc:
                    raise HTTPException(409, '当前剪辑无法绑定 3D 重拍建议，请先保存有效的画面片段') from exc
            if len(p.get('edit_retakes', {})) >= 20:
                raise HTTPException(422, '此项目最多保留 20 次重拍准备与候选')
            async with slots:
                try: job = await asyncio.to_thread(prepare, p, body.clip_index, body.intent)
                except ValueError as exc: raise HTTPException(422, str(exc)) from exc
                except Exception: raise HTTPException(422, '暂不能准备原片段，未提交生成')
            if suggestion:
                job['scene_retake_id'] = suggestion['id']
            p.setdefault('edit_retakes', {})[job['id']] = job
            store.save(p, uid); store.event(p, 'tool', 'edit_retake_prepared')
            return view(p, job)

    @app.get('/creative/api/projects/{pid}/edit/retakes')
    def listing(pid: str, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization))
        return {'jobs': [view(p, j) for j in p.get('edit_retakes', {}).values()]}

    @app.post('/creative/api/projects/{pid}/edit/retakes/{jid}/generate')
    async def generate(pid: str, jid: str, body: Approve, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p, job = find(pid, uid, jid)
            if (body.quote_digest, body.approved_credits, body.revision) != (job['quote_digest'], job['credits'], job['revision']):
                raise HTTPException(409, '费用或版本已变化，请重新核对本次重拍')
            if job['state'] != 'ready':
                return view(p, job)  # Exact replay never launches a second submission.
            writable(p, body.revision)
            if job['credits'] != quote('kling', MODEL, math.ceil(job['duration'])):
                raise HTTPException(409, '重拍计价已更新，请重新准备并核对费用')
            try:
                sources = await asyncio.to_thread(source_catalog, p)
                spec = validate_edit(p['edit'], catalog=sources)
                if document_digest(spec) != job['base_digest'] or sources[job['clip']['source']]['sha256'] != job['source_sha256']:
                    raise ValueError('原时间轴或素材已改变，请重新准备重拍')
                payload(p, job)
                if digest(directory(pid, jid) / 'original.mp4') != job['source_sha256']:
                    raise ValueError('冻结原片段发生变化')
            except ValueError as exc: raise HTTPException(409, str(exc)) from exc
            except Exception: raise HTTPException(409, '重拍输入暂不可用，未提交生成')
            job.update(state='submitting', approved_credits=body.approved_credits)
            store.save(p, uid); store.event(p, 'runner', 'edit_retake_approved')
            store.RUNNING[pid] = asyncio.create_task(run_retake(pid, uid, jid, app, authorization, submit=True))
            return view(p, job)

    @app.post('/creative/api/projects/{pid}/edit/retakes/batch')
    async def batch_generate(pid: str, body: BatchSubmit, authorization: str | None = Header(None)):
        """Explicitly submit a reviewed set of scene shots, one paid call at a time."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            existing = next((item for item in p.get('edit_retake_batches', {}).values()
                             if isinstance(item, dict) and item.get('revision') == body.revision
                             and item.get('scene_retake_id') == body.scene_retake_id
                             and item.get('approval_receipt_sha256') == body.approval_receipt_sha256
                             and item.get('shot_ids') == body.shot_ids
                             and item.get('approved_credits') == body.approved_credits), None)
            if existing:
                return batch_view(p, existing)
            writable(p, body.revision)
            try:
                suggestion, _approval, segments = _batch_context(p, body)
                sources = await asyncio.to_thread(source_catalog, p)
                spec = validate_edit(p.get('edit', {}), catalog=sources)
            except HTTPException:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(409, '当前时间轴无法绑定这些 3D 镜头，请先定位或分割画面') from exc
            if len(p.get('edit_retakes', {})) + len(segments) > 20:
                raise HTTPException(422, '此项目最多保留 20 次重拍准备与候选')
            if len(p.get('edit_retake_batches', {})) >= 20:
                raise HTTPException(422, '此项目最多保留 20 个批量生成队列')
            selected = []
            for segment in segments:
                start, end = segment.get('start'), segment.get('end')
                index = next((i for i, clip in enumerate(spec.get('clips', []))
                              if clip.get('source') == 'primary' and clip.get('start', 0) <= start
                              and clip.get('end', 0) >= end), None)
                if index is None:
                    raise HTTPException(409, '当前时间轴没有完整覆盖已批准镜头，请先调整片段范围')
                note = str(segment.get('note') or '').strip()
                intent = str(suggestion.get('intent') or '按 3D 回放核对结果修正镜头。').strip()
                if note:
                    intent += '\n镜头备注：' + note
                selected.append((segment, index, intent[:1600]))
            prepared = []
            try:
                for segment, index, intent in selected:
                    async with slots:
                        job = await asyncio.to_thread(prepare, p, index, intent)
                    job['scene_retake_id'] = body.scene_retake_id
                    job['scene_shot_id'] = str(segment.get('shot_id'))[:48]
                    job['batch_revision'] = body.revision
                    job['quote_digest'] = document_digest(job)
                    prepared.append(job)
            except HTTPException:
                for item in prepared: _cleanup_prepared(pid, item['id'])
                raise
            except Exception as exc:
                for item in prepared: _cleanup_prepared(pid, item['id'])
                raise HTTPException(422, '暂不能冻结某个镜头输入，未提交批量生成') from exc
            total = sum(item.get('credits', 0) for item in prepared)
            if total != body.approved_credits:
                for item in prepared: _cleanup_prepared(pid, item['id'])
                raise HTTPException(409, '当前接入模型的逐镜头报价与确认积分不一致，请重新生成并核对')
            queue_id = secrets.token_hex(16)
            for item in prepared:
                item['batch_id'] = queue_id
                p.setdefault('edit_retakes', {})[item['id']] = item
            queue = {
                'id': queue_id, 'scene_retake_id': body.scene_retake_id,
                'revision': body.revision, 'base_document_sha256': document_digest(spec),
                'approval_receipt_sha256': body.approval_receipt_sha256,
                'shot_ids': list(body.shot_ids), 'job_ids': [item['id'] for item in prepared],
                'total_credits': total, 'approved_credits': body.approved_credits,
                'state': 'queued', 'current_index': 0, 'completed_count': 0,
                'training_eligible': False, 'created_at': round(time.time(), 3),
            }
            p.setdefault('edit_retake_batches', {})[queue_id] = queue
            store.save(p, uid); store.event(p, 'runner', 'edit_retake_batch_approved')
            task = asyncio.create_task(run_batch(pid, uid, queue_id, app, authorization))
            store.RUNNING[pid] = task
            return batch_view(p, queue)

    @app.get('/creative/api/projects/{pid}/edit/retakes/batch/{batch_id}')
    def batch_status(pid: str, batch_id: str, authorization: str | None = Header(None)):
        p = store.load(pid, owner(authorization)); queue = p.get('edit_retake_batches', {}).get(batch_id)
        if not isinstance(queue, dict):
            raise HTTPException(404, '找不到批量生成队列')
        return batch_view(p, queue)

    @app.get('/creative/api/projects/{pid}/edit/retakes/{jid}')
    async def status(pid: str, jid: str, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p, job = find(pid, uid, jid)
            if job['state'] in ('generating', 'checking') and job.get('provider_job_id') and pid not in store.RUNNING and p['state'] not in ('planning', 'running', 'rendering'):
                store.RUNNING[pid] = asyncio.create_task(run_retake(pid, uid, jid, app, authorization))
            return view(p, job)

    @app.get('/creative/api/projects/{pid}/edit/retakes/{jid}/input')
    def input_media(pid: str, jid: str, authorization: str | None = Header(None)):
        p, job = find(pid, owner(authorization), jid)
        try:
            private = json.loads((directory(pid, jid) / 'input.json').read_text())
            path = input_path(private['reference'], job['input_sha256'])
        except Exception: raise HTTPException(404, '原片段暂不可读取')
        return FileResponse(path, media_type='video/mp4')

    @app.post('/creative/api/projects/{pid}/edit/retakes/{jid}/plan')
    async def plan(pid: str, jid: str, body: Adopt, authorization: str | None = Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p, job = find(pid, uid, jid); writable(p, body.revision)
            try:
                spec = await asyncio.to_thread(candidate_plan, p, job)
                sources = await asyncio.to_thread(source_catalog, p)
            except ValueError as exc: raise HTTPException(409, str(exc)) from exc
            return {'spec': spec, 'sources': sources, 'revision': p['revision']}
