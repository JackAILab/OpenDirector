"""Resume a bounded chapter task; credentials stay in the active process only."""
import asyncio
import fcntl
import secrets
from harness.studio import store
from harness.tools import creative_campaign as actions
from harness.tools.creative_video import CreativeVideoTool, progress_snapshot, provider_status_projection
from harness.tools.creative_render import verify_native_audio
from harness.tools.creative_edit import validate_edit, render_edit
from harness.tools.creative_edit_media import source_catalog

SLOTS = asyncio.Semaphore(2)


def timeline(project):
    catalog = source_catalog(project)
    chapters = project['campaign']['chapters']
    ids = ['canvas_'+c['asset'] for c in chapters]
    return validate_edit({'sources': {sid: catalog[sid]['sha256'] for sid in ids},
        'clips': [dict(source=sid, start=0, end=15, gain=1) for sid in ids],
        'captions': [dict(text=s['caption'], start=s['start'], end=s['start']+s['duration'], track=0)
                     for s in project['shots'] if s.get('caption', '').strip()],
        'audio': [], 'volume': 1}, catalog=catalog)


async def production_campaign(app, initial, owner, authorization):
    pid = initial['id']
    lease_dir = store.DATA/'execution-locks'; lease_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Cross-process exclusion on the shared project volume; never hold a DB transaction over model latency.
    with (lease_dir/(pid+'.lock')).open('a') as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if store.RUNNING.get(pid) is asyncio.current_task(): store.RUNNING.pop(pid, None)
            return
        try:
            async with SLOTS:
                await _run(app, pid, owner, authorization)
        finally:
            fcntl.flock(lease, fcntl.LOCK_UN)
            if store.RUNNING.get(pid) is asyncio.current_task(): store.RUNNING.pop(pid, None)


async def _run(app, pid, owner, authorization):
    p = store.load(pid, owner)
    campaign = p['campaign']
    tool = CreativeVideoTool(app, authorization)
    directory = store.DATA/'artifacts'/p['run_id']; directory.mkdir(parents=True, exist_ok=True)

    def persist():
        latest = store.load(pid, owner)
        p['stop_requested'] = latest.get('stop_requested', False)
        # These are independent UI metadata; generation owns the frozen campaign graph.
        for key in ('manual_nodes', 'director_project', 'manual_position'):
            if key in latest: p[key] = latest[key]
        callbacks = {c['id']: c for c in latest.get('campaign', {}).get('chapters', [])}
        for chapter in campaign['chapters']:
            current = callbacks.get(chapter['id'], {})
            if current.get('provider_callback'): chapter['provider_callback'] = current['provider_callback']
            for shot in p['shots'][chapter['index']*3:chapter['index']*3+3]:
                shot['state'] = chapter['state']
                if chapter.get('progress'): shot['progress'] = chapter['progress']
        store.save(p, owner)

    def stopped():
        return store.load(pid, owner).get('stop_requested', False)

    try:
        actions.validate_plan(p)
        if actions.plan_digest(p) != campaign['plan_digest']:
            raise ValueError('方案已变化，已停止制作')
        actions.bind_inputs(p); persist()
        for chapter in campaign['chapters']:
            if stopped():
                p['state']='paused'; campaign['stage']='paused'; persist(); return
            if chapter['state']=='failed':
                raise RuntimeError('章节生成失败，已有素材保留；请明确规划新版本，不会自动重试')
            if chapter['state']=='completed': continue
            view = actions.chapter_project(p, chapter)
            if chapter.get('inputs') and chapter['inputs'] != view['video_inputs']:
                raise ValueError('章节参考已变化，停止恢复')
            if not chapter.get('job_id'):
                # A crash/lost response after this marker is deliberately not replayed.
                if chapter['state']=='submitting':
                    raise RuntimeError('章节提交结果待核对；不会重复提交付费生成')
                chapter['inputs'] = view['video_inputs']
                chapter['state']='submitting'; campaign['stage']='generating'; persist()
                store.event(p, 'tool', 'chapter_submit_requested', chapter['id'])
                result = await tool.submit(view, dict(id=chapter['id'], duration=15,
                    prompt=actions.chapter_prompt(view, chapter, len(campaign['chapters']))))
                chapter.update(job_id=result['id'], state='generating'); persist()
                store.event(p, 'observation', 'chapter_accepted', chapter['id'])
            for _ in range(1440):
                if stopped():
                    p['state']='paused'; campaign['stage']='paused'; persist(); return
                status = await tool.status(chapter['job_id'])
                chapter['provider_poll'] = provider_status_projection(status)
                chapter['provider_resolution'] = 'polling'
                chapter['progress'] = progress_snapshot(status); persist()
                if status['status']=='completed': break
                if status['status'] in ('failed','error','cancelled','canceled'):
                    chapter['state']='failed'; chapter['provider_resolution']='provider_terminal_failed'; persist()
                    raise RuntimeError('章节生成失败，后续生成已停止，未重试或更换模型')
                if status['status']=='uncertain':
                    raise RuntimeError('章节结果待核对，后续生成已停止')
                await asyncio.sleep(5)
            else: raise RuntimeError('等待超时；恢复时继续查询原章节任务')
            path = directory/(chapter['id']+'.mp4')
            campaign['stage']='checking'; persist()
            if not path.exists(): await tool.download(chapter['job_id'], path)
            chapter['qa'] = await asyncio.to_thread(verify_native_audio, path, 15)
            await asyncio.to_thread(actions.materialize_chapter, p, chapter, path)
            chapter['state']='completed'; chapter['provider_resolution']='source_verified'; persist()
            store.event(p, 'evaluator', 'chapter_source_passed', chapter['id'])
        if stopped():
            p['state']='paused'; campaign['stage']='paused'; persist(); return
        p['state']='rendering'; campaign['stage']='editing'; persist()
        if not campaign.get('edit'):
            campaign['edit'] = await asyncio.to_thread(timeline, p); persist()
        if not campaign.get('rendered_artifact'):
            # Every render attempt has a fresh folder. A valid saved export is reused on resume.
            target = directory/('campaign_'+secrets.token_hex(8))
            p['qa'] = await asyncio.to_thread(render_edit, p, campaign['edit'], target)
            await asyncio.to_thread(verify_native_audio, target/'final.mp4', p['duration'])
            campaign['rendered_artifact'] = str((target/'final.mp4').relative_to(store.DATA)); persist()
        if not campaign.get('result_asset'):
            campaign['result_asset'] = await asyncio.to_thread(actions.attach_final, p,
                store.DATA/campaign['rendered_artifact'])
        p['edit'] = campaign['edit']
        p['artifact'] = campaign['rendered_artifact']
        p['result_artifact'] = p['artifact']
        p.update(state='completed', error='', training_eligible=False)
        # Saving commits the completed result and its delivery intent together.
        # Workspace capacity or concurrent edits must not fail a finished film.
        campaign['stage']='completed'; persist()
        store.event(p, 'evaluator', 'campaign_technical_passed')
    except Exception as exc:
        p['state'] = 'failed' if any(c['state']=='failed' for c in campaign['chapters']) else 'paused'
        campaign['stage'] = p['state']
        p['error'] = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else '自动制作中断，已有章节保留；恢复不会重复提交已接受的任务'
        persist(); store.event(p, 'runner', 'campaign_stopped')
