"""Bounded authenticated video actions through the existing quota gateway."""
import json
import httpx
import math
import time
import asyncio
import hashlib
from harness.models.video_catalog import model_spec
from harness.tools.creative_reference import reference_uri


class CreativeVideoTool:
    def __init__(self, app, authorization):
        self.app, self.authorization = app, authorization

    async def request(self, method, path, **kwargs):
        headers = {'Authorization': self.authorization, **kwargs.pop('headers', {})}
        attempts = 3 if method == 'GET' else 1
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://studio.internal', timeout=180) as client:
                    response = await client.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError:
                if attempt + 1 == attempts:
                    raise
            else:
                if response.status_code not in (502, 503, 504) or attempt + 1 == attempts:
                    break
            await asyncio.sleep((1, 3)[attempt])
        if not response.is_success:
            raise RuntimeError(f'视频接口返回 {response.status_code}；已停止，不会自动重新生成。')
        return response

    async def submit(self, project, shot):
        payload = {'provider': project['provider'], 'model':model_spec(project['provider'],project.get('model'))['id'], 'task': 't2va', 'prompt': shot['prompt'] if project.get('generation_mode')=='single_native' else shot['prompt'] + '\nNo text, no letters, no logos, no interface elements.',
                   'conditions': [], 'target': {'short_edge': 720 if project['provider']=='kling' else 768,
                   'aspect_ratio': project['aspect'], 'duration_seconds': shot['duration']}}
        if project.get('generation_mode')=='single_native':
            spec=model_spec(project['provider'],project.get('model'))
            payload.update(enable_audio=spec['audio'], prefer_multi_shots=bool(spec.get('single_film')))
        if project.get('video_inputs'):
            from harness.tools.creative_video_inputs import conditions
            payload['conditions']=conditions(project)
            payload['task']='ref2va' if project['video_inputs']['mode']=='references' else 'fl2va' if payload['conditions'] else 't2va'
        elif project.get('reference'):
            omni=project.get('model')=='kling-video-v4_0'
            payload['task']='ref2va' if omni else 'fl2va'
            payload['conditions']=[{'type':'image','uri':reference_uri(project),**({'role':'reference','index':1} if omni else {'role':'keyframe','frame_index':0})}]
            if project['provider']=='minimax-h3':
                payload['target']['aspect_ratio']='auto'
        if len(json.dumps(payload).encode())>1_048_576:raise RuntimeError('视频输入超过当前服务大小限制，尚未提交生成')
        return (await self.request('POST', '/v1/videos', headers={'Idempotency-Key': project['run_id']+'-'+shot['id']}, json=payload)).json()

    async def submit_film(self, project):
        if project.get('generation_mode') != 'single_native':
            raise RuntimeError('整片制作必须使用原生有声一次生成模式，请重新审阅制作方案。')
        spec = model_spec(project['provider'], project.get('model'))
        if project.get('creation_mode')=='video':
            if not spec.get('manual_available') or project['duration'] not in spec['manual_durations']:raise RuntimeError('所选模型不支持当前手动生成参数')
        elif not spec.get('single_film') or project['duration'] != 15:
            raise RuntimeError('当前模型尚未验证 15 秒有声整片生成，请选择 Kling 3.0 或 O3。')
        film = {'id': 'film', 'duration': project['duration'], 'prompt': film_prompt(project)}
        return await self.submit(project, film)

    async def status(self, job_id):
        return (await self.request('GET', '/v1/videos/'+job_id)).json()

    async def download(self, job_id, destination):
        response = await self.request('GET', '/v1/videos/'+job_id+'/content')
        temporary = destination.with_suffix('.part')
        temporary.write_bytes(response.content)
        temporary.replace(destination)


def progress_snapshot(status):
    """Only bounded public counters, never raw provider fields or log text."""
    result={}
    # Providers disagree on the field name and occasionally encode the value
    # as a numeric string or nest it under a bounded result object.  Normalize
    # only these known scalar fields; never retain the enclosing payload.
    candidates=[]
    for container in (status, status.get('result'), status.get('output')):
        if not isinstance(container, dict):
            continue
        for key in ('progress', 'progress_percent', 'progressPercent', 'task_progress', 'taskProgress'):
            if key in container:
                value = container[key]
                candidates.append(value)
                # Some video providers return {progress: {percent: 42}}.
                if isinstance(value, dict):
                    candidates.extend(value.get(k) for k in ('percent', 'percentage', 'value'))
    for value in candidates:
        if isinstance(value, bool) or value is None or value == '':
            continue
        try:
            numeric=float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric) and 0<=numeric<=100:
            result['percent']=round(numeric)
            break
    stage=status.get('stage')
    if stage in ('queued','preparing','generating','denoising','encoding','decoding','finalizing'):
        result['stage']=stage
    checked=status.get('checked_at')
    if type(checked) in (int,float) and math.isfinite(checked) and 0<checked<=time.time()+60:
        result['checked_at']=int(checked)
    done,total=status.get('steps_completed'),status.get('steps_total')
    if type(done) is int and type(total) is int and 0<=done<=total<=10000 and total>0:
        result.update(steps_completed=done,steps_total=total)
    return result


def _safe_text(value, limit):
    if not isinstance(value, str):
        return ''
    return value.strip()[:limit]


def _safe_digest(value):
    value = _safe_text(value, 64).lower()
    return value if len(value) == 64 and all(c in '0123456789abcdef' for c in value) else ''


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _bounded_points(value):
    """Normalize provider points for hashing without retaining coordinates."""
    if isinstance(value, dict):
        value = value.get('points') or value.get('path') or value.get('keyframes')
    if not isinstance(value, list) or not value or len(value) > 256:
        return None
    points = []
    for point in value:
        if isinstance(point, dict):
            point = [point.get('x'), point.get('y'), point.get('z')]
        if not isinstance(point, (list, tuple)) or len(point) not in (2, 3):
            return None
        if not all(_finite(n) and abs(n) <= 100000 for n in point):
            return None
        points.append([round(float(n), 6) for n in point])
    return points


def _trajectory_candidate(status):
    """Find only explicitly named trajectory metadata containers.

    Status responses remain provider-private.  This helper reads a few known
    metadata locations and never serializes the enclosing response.
    """
    if not isinstance(status, dict):
        return None
    containers = [status]
    for key in ('metadata', 'result', 'output'):
        value = status.get(key)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in ('trajectory', 'camera_trajectory', 'cameraPath', 'camera_path'):
            if key in container and isinstance(container[key], (dict, list)):
                return container[key]
    return None


def _trajectory_rows(value):
    if isinstance(value, dict):
        rows = value.get('shots')
        if not isinstance(rows, list):
            rows = [value]
    elif isinstance(value, list):
        rows = value
    else:
        return []
    safe = []
    for index, row in enumerate(rows[:12]):
        if not isinstance(row, dict):
            continue
        raw_path_present = any(key in row for key in ('points', 'path', 'keyframes'))
        points = _bounded_points(row.get('points') or row.get('path') or row.get('keyframes'))
        path_digest = _safe_digest(row.get('path_sha256') or row.get('trajectory_sha256'))
        if raw_path_present and points is None and not path_digest:
            continue
        if points:
            # Coordinates are intentionally discarded after deriving this digest.
            path_digest = hashlib.sha256(json.dumps(points, separators=(',', ':')).encode()).hexdigest()
        digest_basis = row.get('digest_basis') if row.get('digest_basis') in ('points', 'provider') else ('points' if points else 'provider')
        path_points = row.get('path_points')
        if type(path_points) is not int or not 0 <= path_points <= 256:
            path_points = len(points) if points else None
        duration = row.get('duration')
        if not _finite(duration) or not 0 < duration <= 120:
            duration = None
        shot_id = _safe_text(row.get('shot_id') or row.get('id'), 48)
        easing = _safe_text(row.get('path_easing') or row.get('easing'), 24)
        closed = row.get('path_closed') if isinstance(row.get('path_closed'), bool) else row.get('closed')
        item = {'index': index}
        if shot_id:
            item['shot_id'] = shot_id
        if path_digest:
            item['path_sha256'] = path_digest
            item['digest_basis'] = digest_basis
        if path_points is not None:
            item['path_points'] = path_points
        if duration is not None:
            item['duration'] = round(float(duration), 3)
        if isinstance(closed, bool):
            item['path_closed'] = closed
        if easing:
            item['path_easing'] = easing
        # A row with no bounded metadata is not an observation.
        if len(item) > 1:
            safe.append(item)
    return safe


def provider_trajectory_observation(status):
    """Project structured provider status into safe, non-approval metadata.

    The returned object contains no raw response, URLs, handles or path
    coordinates.  It is an observation of what the provider reported, not
    evidence that the rendered camera followed the saved 3D trajectory.
    """
    rows = _trajectory_rows(_trajectory_candidate(status))
    if not rows:
        return None
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'version': 1, 'source': 'provider_status', 'observed': True,
            'sha256': digest, 'shots': rows, 'training_eligible': False}


def provider_trajectory_view(observation):
    """Re-sanitize a stored observation before exposing it through an API."""
    if not isinstance(observation, dict) or observation.get('version') != 1:
        return None
    rows = _trajectory_rows({'shots': observation.get('shots', [])})
    if not rows:
        return None
    digest = _safe_digest(observation.get('sha256'))
    if not digest:
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'version': 1, 'source': 'provider_status', 'observed': True,
            'sha256': digest, 'shots': rows, 'training_eligible': False}


def provider_status_projection(status):
    """Keep the shared terminal-state boundary identical for polling and callbacks."""
    if not isinstance(status, dict):
        return None
    state = status.get('status')
    if state not in ('queued', 'preparing', 'running', 'processing', 'completed',
                     'failed', 'error', 'cancelled', 'canceled', 'uncertain'):
        return None
    result = {'status': state}
    progress = progress_snapshot(status)
    if progress:
        result['progress'] = progress
    observation = provider_trajectory_observation(status)
    if observation:
        result['trajectory_observed'] = True
        result['trajectory_sha256'] = observation['sha256']
    return result


def film_prompt(project):
    """Compile one bounded, timecoded film brief, never one request per beat."""
    if project.get('creation_mode')=='video':
        from harness.tools.creative_video_inputs import description
        return '\n\n'.join(filter(None, [project['shots'][0]['prompt'], description(project),
            'No readable text, captions or UI; these are added in the editor.']))
    shots = project['shots']
    cursor = 0
    sections = [f"Create ONE complete {project['duration']}-second advertisement with native synchronized audio. "
                "Generate all the following timed beats together in this one film. Maintain the same product, "
                "setting and visual identity throughout. Use coherent motivated transitions. "
                "No readable text, logos, captions or UI. Audio must be audible throughout: "
                "an original restrained musical bed, physical sound effects and the specified spoken words. "
                "Do not speak the instructions or timecodes. Speech must finish before the ending."]
    intent = project.get('scene_render_intent') or {}
    trajectory = intent.get('trajectory') if isinstance(intent, dict) else None
    trajectory_rows = trajectory.get('shots', []) if isinstance(trajectory, dict) else []
    if trajectory_rows and intent.get('trajectory_sha256'):
        guidance = [
            '3D staging handoff: use the approved 3D scene references for product placement, lighting and camera rhythm.',
            f"Trajectory lock {str(intent['trajectory_sha256'])[:64]}. This is bounded camera guidance; do not claim exact provider trajectory execution.",
        ]
        for row in trajectory_rows[:12]:
            if not isinstance(row, dict):
                continue
            shot_id = str(row.get('shot_id') or 'shot')[:48]
            duration = float(row.get('duration', 0))
            points = int(row.get('path_points', 0))
            closed = 'closed loop' if row.get('path_closed') else 'open path'
            easing = str(row.get('path_easing') or 'smooth')[:16]
            guidance.append(f"Camera {shot_id}: {duration:g}s, {points} path points, {closed}, {easing} easing.")
        sections.append('\n'.join(guidance))
    for shot in shots:
        if shot['start'] != cursor or shot['duration'] <= 0:
            raise RuntimeError('分镜时间必须连续覆盖完整成片。')
        end = cursor + shot['duration']
        audio = shot.get('audio_prompt', '').strip()
        if not audio:
            raise RuntimeError('请为每个分镜补齐声音设计后再制作。')
        sections.append(f"[{cursor}–{end} seconds] Visual: {shot['prompt']}\nAudio: {audio}")
        cursor = end
    if cursor != project['duration'] or cursor < 15:
        raise RuntimeError('整片至少 15 秒，分镜必须覆盖完整时长。')
    from harness.tools.creative_video_inputs import description
    if project.get('video_inputs'):sections.insert(1,description(project))
    return '\n\n'.join(sections)


def input_manifest(project):
    """Actual model conditions are separate from director-only context."""
    ref=project.get('reference');inputs=project.get('video_inputs')
    mode=inputs['mode'] if inputs else ('references' if project.get('model') in ('kling-video-v3_0_omni','kling-video-v4_0') else 'first_frame') if ref else 'text'
    images=[dict(id=r['asset'],asset=r['asset'],role=r['role'],instruction=r['instruction'],sha256=r['sha256'],transport_sha256=r['transport_sha256'],slot=i+1,scope='whole_film') for i,r in enumerate(inputs['references'])] if inputs else ([dict(id=ref['id'],asset=ref.get('source_asset'),role='product',slot=1,scope='whole_film')] if ref else [])
    graph=project.get('canvas',{});connected={e['source'] for e in graph.get('edges',[]) if e.get('target')=='director'}
    actual={r.get('asset') for r in images if r.get('asset')}
    return dict(request_count=project['duration']//15 if project.get('generation_mode')=='chaptered_native' else 1,mode=mode,images=images,image=(dict(id=ref['id'],role='reference' if mode=='references' else 'first_frame',scope='whole_film') if ref and not inputs else None),
                video=[],audio=[],element_ids=[],
                director_only=[dict(id=n['id'],kind=n['kind'],label=n.get('label',''),asset=n.get('asset')) for n in graph.get('nodes',[]) if n['id'] in connected and n.get('asset') not in actual],
                beats=[dict(id=s['id'],start=s['start'],end=s['start']+s['duration'],image_ids=[r['id'] for r in images],image_id=images[0]['id'] if len(images)==1 else None,audio_source='prompt') for s in project.get('shots',[])])
