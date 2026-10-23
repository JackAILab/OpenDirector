import asyncio
import os
import secrets
from harness.studio.store import DATA, RUNNING, load, save as store_save, event
from harness.tools.creative_video import (CreativeVideoTool, progress_snapshot,
                                          provider_trajectory_observation, provider_status_projection)
from harness.tools.creative_render import render, probe, verify_native_audio, verify_manual_video


def _merge_runtime_observations(p, owner):
    """Keep callback observations when a polling loop saves a stale snapshot."""
    latest = load(p['id'], owner)
    for key in ('manual_nodes','director_project','manual_position'):
        if key in latest:p[key]=latest[key]

    def merge(incoming, current):
        if not isinstance(incoming, dict) or not isinstance(current, dict):
            return
        callback = current.get('provider_callback')
        prior = incoming.get('provider_callback')
        received = callback.get('received_at', 0) if isinstance(callback, dict) else 0
        prior_received = prior.get('received_at', 0) if isinstance(prior, dict) else 0
        if callback and received >= prior_received:
            incoming['provider_callback'] = callback
            if current.get('provider_trajectory'):
                incoming['provider_trajectory'] = current['provider_trajectory']

    if isinstance(p.get('film'), dict):
        merge(p['film'], latest.get('film') if isinstance(latest.get('film'), dict) else None)
    latest_shots = {shot.get('id'): shot for shot in latest.get('shots', []) if isinstance(shot, dict)}
    for shot in p.get('shots', []):
        if isinstance(shot, dict):
            merge(shot, latest_shots.get(shot.get('id')))
    latest_retakes = latest.get('edit_retakes', {}) if isinstance(latest.get('edit_retakes'), dict) else {}
    for jid, job in p.get('edit_retakes', {}).items():
        merge(job, latest_retakes.get(jid))


def _save(p, owner):
    _merge_runtime_observations(p, owner)
    store_save(p, owner)

async def production(app, p, owner, authorization):
    if p.get('generation_mode')=='chaptered_native':
        from harness.core.creative_campaign_runner import production_campaign
        return await production_campaign(app, p, owner, authorization)
    if p.get('generation_mode')=='single_native':
        return await production_film(app, p, owner, authorization)
    tool = CreativeVideoTool(app, authorization)
    directory = DATA/'artifacts'/p['run_id']
    directory.mkdir(parents=True,exist_ok=True)
    try:
        for shot in p['shots']:
            latest = load(p['id'],owner)
            if latest.get('stop_requested'):
                p['state']='paused'; p['stop_requested']=True
                event(p,'runner','paused');_save(p,owner);return
            if shot['state']=='completed': continue
            if shot['state']=='failed': raise RuntimeError('有镜头生成失败；请调整方案后创建新一版，不会自动重试。')
            if not shot.get('job_id'):
                shot['state']='submitting'; _save(p,owner)
                event(p,'tool','submit_requested',shot['id'])
                result = await tool.submit(p,shot)
                shot['job_id'] = result['id'];shot['state']='generating';p['stop_requested']=load(p['id'],owner).get('stop_requested',False);_save(p,owner)
                event(p,'observation','generation_accepted',shot['id'])
            for _ in range(1440):
                status = await tool.status(shot['job_id'])
                status_projection = provider_status_projection(status)
                provider_trajectory = provider_trajectory_observation(status)
                if status_projection and status_projection != shot.get('provider_poll'):
                    shot['provider_poll'] = status_projection
                    shot['provider_resolution'] = 'polling'
                    _save(p, owner)
                if provider_trajectory and provider_trajectory != shot.get('provider_trajectory'):
                    shot['provider_trajectory'] = provider_trajectory
                    _save(p, owner)
                progress=progress_snapshot(status)
                if progress and progress!=shot.get('progress'):
                    shot['progress']=progress
                    p['stop_requested']=load(p['id'],owner).get('stop_requested',False)
                    _save(p,owner)
                if status['status']=='uncertain':
                    shot['provider_resolution'] = 'provider_terminal_uncertain'
                    _save(p, owner)
                    raise RuntimeError('本镜头提交结果待核对，已有请求已保留；不会自动重新生成。')
                if status['status']=='completed':
                    shot['provider_resolution'] = 'provider_terminal_confirmed'
                    _save(p, owner)
                    break
                if status['status'] in ('failed','error','cancelled','canceled'):
                    shot['state']='failed'
                    shot['provider_resolution'] = 'provider_terminal_failed'
                    _save(p, owner)
                    raise RuntimeError('镜头生成失败，已停止本次制作，未自动重试。')
                await asyncio.sleep(5)
            else: raise RuntimeError('生成等待超时；已有任务被保留，可以继续查询。')
            target = directory/(shot['id']+'.mp4')
            shot['provider_resolution'] = 'source_checking'
            _save(p, owner)
            if not target.exists(): await tool.download(shot['job_id'],target)
            metadata = await asyncio.to_thread(probe,target)
            if float(metadata['format']['duration']) < shot['duration']-.15: raise RuntimeError('镜头时长不足，已停止后续付费生成。')
            shot['state']='completed';shot['provider_resolution']='source_verified';p['stop_requested']=load(p['id'],owner).get('stop_requested',False);_save(p,owner);event(p,'evaluator','source_passed',shot['id'])
        if load(p['id'],owner).get('stop_requested'):
            p['state']='paused';p['stop_requested']=True;_save(p,owner);event(p,'runner','paused');return
        p['state']='rendering';_save(p,owner);event(p,'tool','render_started')
        # A stopped process may leave a partial file; each render attempt owns its own folder.
        render_dir = directory/('render_'+secrets.token_hex(5)); render_dir.mkdir()
        for shot in p['shots']:
            os.link(directory/(shot['id']+'.mp4'),render_dir/(shot['id']+'.mp4'))
        p['qa'] = await asyncio.to_thread(render,p,render_dir)
        p['artifact'] = str((render_dir/'final.mp4').relative_to(DATA))
        p['state']='completed';p['error']='';_save(p,owner);event(p,'evaluator','technical_passed')
    except Exception as exc:
        p['state']='paused' if not any(s['state']=='failed' for s in p['shots']) else 'failed'
        p['error'] = str(exc) if isinstance(exc,RuntimeError) else '制作暂时中断，已保存进度。可恢复查询；不会创建重复付费任务。'
        _save(p,owner);event(p,'runner','execution_stopped')
    finally: RUNNING.pop(p['id'],None)


async def production_film(app, p, owner, authorization):
    """One durable provider job for the complete storyboard; never concatenate shots."""
    tool = CreativeVideoTool(app, authorization)
    directory = DATA/'artifacts'/p['run_id']
    directory.mkdir(parents=True, exist_ok=True)
    film = p.setdefault('film', {'state': 'planned'})
    def persist():
        p['stop_requested'] = load(p['id'], owner).get('stop_requested', False)
        for shot in p['shots']:
            shot['state'] = film['state']
            if film.get('progress'): shot['progress'] = film['progress']
        _save(p, owner)
    try:
        if film['state']=='failed':
            raise RuntimeError('整片生成失败；请明确创建新方案，不会自动重试。')
        if not film.get('job_id'):
            if load(p['id'],owner).get('stop_requested'):
                p['state']='paused';persist();return
            from harness.tools.creative_video import input_manifest
            film['inputs']=input_manifest(p)
            film['state']='submitting';persist();event(p,'tool','submit_requested','film')
            # Replaying after a lost response uses the same key and identical body.
            result = await tool.submit_film(p)
            film.update(job_id=result['id'],state='generating');persist()
            event(p,'observation','generation_accepted','film')
        if film['state']!='completed':
            for _ in range(1440):
                status = await tool.status(film['job_id'])
                status_projection = provider_status_projection(status)
                provider_trajectory = provider_trajectory_observation(status)
                if status_projection and status_projection != film.get('provider_poll'):
                    film['provider_poll'] = status_projection
                    film['provider_resolution'] = 'polling'
                    persist()
                if provider_trajectory and provider_trajectory != film.get('provider_trajectory'):
                    film['provider_trajectory'] = provider_trajectory
                    persist()
                progress = progress_snapshot(status)
                if progress and progress != film.get('progress'):
                    film['progress']=progress;persist()
                if status['status']=='completed':
                    film['provider_resolution'] = 'provider_terminal_confirmed'
                    persist()
                    break
                if status['status'] in ('failed','error','cancelled','canceled'):
                    film['state']='failed'
                    film['provider_resolution'] = 'provider_terminal_failed'
                    raise RuntimeError('整片生成失败，已保留记录，未重试或更换模型。')
                if status['status']=='uncertain':
                    film['provider_resolution'] = 'provider_terminal_uncertain'
                    persist()
                    raise RuntimeError('整片提交结果待核对；不会重新提交付费生成。')
                if load(p['id'],owner).get('stop_requested'):
                    p['state']='paused';persist();event(p,'runner','paused');return
                await asyncio.sleep(5)
            else: raise RuntimeError('等待超时，已有整片任务已保留，恢复时只查询。')
            source = directory/'film.mp4'
            film['provider_resolution'] = 'source_checking';persist()
            if not source.exists(): await tool.download(film['job_id'], source)
            film['source_qa'] = await asyncio.to_thread(verify_manual_video if p.get('creation_mode')=='video' else verify_native_audio,source,p['duration'])
            film['state']='completed';film['provider_resolution']='source_verified';persist();event(p,'evaluator','source_passed','film')
        if load(p['id'],owner).get('stop_requested'):
            p['state']='paused';persist();return
        p['state']='rendering';persist();event(p,'tool','render_started')
        render_dir=directory/('render_'+secrets.token_hex(5));render_dir.mkdir()
        os.link(directory/'film.mp4',render_dir/'film.mp4')
        if p.get('creation_mode')=='video':
            os.link(render_dir/'film.mp4',render_dir/'final.mp4')
            p['qa']=dict(film['source_qa'])
        else:p['qa']=await asyncio.to_thread(render,p,render_dir)
        from harness.tools.creative_video_result import attach_result
        await asyncio.to_thread(attach_result,p,owner,render_dir/'final.mp4')
        p['artifact']=str((render_dir/'final.mp4').relative_to(DATA))
        p['state']='completed';p['error']='';p['training_eligible']=False
        persist()
        try:
            from harness.learning.episodes import record_artifact
            await asyncio.to_thread(record_artifact,p,owner,render_dir/'final.mp4')
        except Exception:event(p,'learning','artifact_capture_failed')
        event(p,'evaluator','technical_passed')
    except Exception as exc:
        p['state']='failed' if film['state']=='failed' else 'paused'
        p['error']=str(exc) if isinstance(exc,RuntimeError) else '整片制作中断，已有任务保留；恢复时不会重复付费。'
        persist();event(p,'runner','execution_stopped')
    finally:
        RUNNING.pop(p['id'],None)
