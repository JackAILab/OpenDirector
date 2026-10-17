"""One approved retake submission; only status/download may resume after restart."""
import asyncio
import os
import time
from harness.studio import store
from harness.tools.creative_retake import CreativeRetakeTool, directory, finish_candidate
from harness.tools.creative_video import provider_trajectory_observation, provider_status_projection


async def run_retake(pid, uid, jid, app, authorization, submit=False, keep_running=False):
    tool = CreativeRetakeTool(app, authorization)

    async def update(stage=None, **values):
        async with store.lock(pid):
            p = store.load(pid, uid); job = p['edit_retakes'][jid]
            job.update(values); store.save(p, uid)
            if stage:
                store.event(p, stage, 'edit_retake_' + values.get('state', job.get('state', 'unknown')))
            return p, dict(job)

    try:
        p = store.load(pid, uid); job = p['edit_retakes'][jid]
        if submit:
            # State was persisted by the API before this background task started.
            # A missing provider handle after interruption never authorizes resubmit.
            result = await tool.submit_retake(p, job)
            handle = result.get('id')
            if not isinstance(handle, str) or not handle or len(handle) > 128:
                raise RuntimeError('Submission handle missing')
            p, job = await update('tool', state='generating', provider_job_id=handle)
        if not job.get('provider_job_id'):
            await update('observation', state='needs_review', error='提交结果待核对，未重新生成；原片和草稿保留。')
            return
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            result = await tool.status(job['provider_job_id'])
            status_projection = provider_status_projection(result)
            if status_projection and status_projection != job.get('provider_poll'):
                await update('observation', provider_poll=status_projection, provider_resolution='polling')
            provider_trajectory = provider_trajectory_observation(result)
            if provider_trajectory and provider_trajectory != job.get('provider_trajectory'):
                await update('observation', provider_trajectory=provider_trajectory)
            state = result.get('status')
            if state == 'completed':
                await update('tool', state='checking', provider_resolution='provider_terminal_confirmed')
                raw = directory(pid, jid) / 'generated.mp4'
                if not raw.exists():
                    await tool.download(job['provider_job_id'], raw)
                    raw.chmod(0o600)
                try:
                    asset = await asyncio.to_thread(finish_candidate, p, job, raw)
                except Exception as exc:
                    safe = str(exc) if isinstance(exc, ValueError) else '候选技术检查未通过，原始结果已保留供核对。'
                    await update('evaluator', state='needs_review', error=safe)
                    return
                async with store.lock(pid):
                    current = store.load(pid, uid)
                    current.setdefault('edit_assets', {})[asset['id']] = asset
                    current['revision'] += 1
                    current['edit_retakes'][jid].update(state='completed', provider_resolution='source_verified', asset='edit_' + asset['id'],
                        candidate_sha256=asset['sha256'], completed_revision=current['revision'],
                        qa={'technical': 'passed', 'semantic': 'pending', 'human': 'pending'}, training_eligible=False)
                    store.save(current, uid); store.event(current, 'evaluator', 'edit_retake_completed')
                return
            if state in ('failed', 'cancelled', 'canceled', 'uncertain'):
                await update('observation', state='failed' if state != 'uncertain' else 'needs_review',
                    provider_resolution='provider_terminal_failed' if state != 'uncertain' else 'provider_terminal_uncertain',
                    error='生成未完成，原片保留；没有重复提交或更换模型。')
                return
            await asyncio.sleep(float(os.getenv('CREATIVE_RETAKE_POLL_SECONDS', '4')))
        await update(state='generating', error='生成仍在处理中，重新打开可继续查询原任务。')
    except Exception:
        current = store.load(pid, uid)['edit_retakes'][jid]
        await update('observation', state='generating' if current.get('provider_job_id') else 'needs_review',
            error='查询暂时中断，可继续查询原任务。' if current.get('provider_job_id') else '提交结果待核对；没有重新生成。')
    finally:
        # A batch runner owns the project lock across several one-shot jobs.
        # Keep its task marker so another request cannot start a parallel paid
        # submission between two shots.  The ordinary single-retake path keeps
        # the historic cleanup behaviour.
        if not keep_running:
            store.RUNNING.pop(pid, None)
