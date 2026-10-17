"""Account scoped scene documents, immutable GLB inputs and reference handoff."""
import asyncio
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from typing import Literal
from harness.studio import store
from harness.tools.creative_scene import default_scene, validate_scene, validate_glb, scene_hash, trajectory_manifest, station_manifest, station_keyframe_observation, shot_at, shot_note, layout_observation, MAX_GLB
from harness.tools.creative_scene_references import FrameBatch,request_hash,publish_frames
from harness.tools.creative_canvas import save_asset, next_position, validate_graph
from harness.tools.creative_scene_observe import SceneSuggestionRequest,observe_scene
from harness.tools.creative_video import provider_trajectory_view
from harness.tools.trajectory_evaluator import evaluate_trajectory
from harness.core.creative_scene_runner import run_scene_suggestion
from harness.models.video_catalog import model_spec, project_quote, quote as catalog_quote
from harness.models.scene_asset import quote_for as scene_asset_quote, task_status as scene_asset_task_status


class SceneEdit(BaseModel):
    revision: int
    spec: dict


class SceneRoleBinding(BaseModel):
    shot_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    object_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    role: Literal['product', 'person', 'scene', 'style']


class SceneRoleBindingSave(BaseModel):
    revision: int
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    bindings: list[SceneRoleBinding] = Field(max_length=12)
    confirm: Literal['save']


class SceneAssetIntent(BaseModel):
    revision: int
    model: Literal['meshforge-3d-pro', 'meshforge-3d-fast']
    skill_id: str = Field(default='ad-video', min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    skill_version: int | None = Field(default=None, ge=1, le=100)
    approval_mode: Literal['manual', 'auto']
    prompt: str = Field(min_length=2, max_length=1600)
    reference_asset: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class SceneAssetQuoteRequest(BaseModel):
    revision: int


class SceneAssetApproval(BaseModel):
    revision: int
    quote_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm: Literal['approve']


class SceneAssetProviderCallback(BaseModel):
    project_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    asset_intent_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    task_id: str = Field(min_length=1, max_length=128)
    status: Literal['queued', 'preparing', 'running', 'processing', 'completed',
                    'failed', 'error', 'cancelled', 'canceled', 'uncertain']
    progress: int | None = Field(default=None, ge=0, le=100)
    result_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class SceneAssetBind(BaseModel):
    revision: int
    asset_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    confirm: Literal['bind']


class RenderIntent(BaseModel):
    revision: int
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    model: str = Field(min_length=1, max_length=80)
    approval_mode: Literal['manual', 'auto']
    aspect: Literal['16:9', '9:16', '1:1']
    trajectory_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    station_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class RenderShotReview(BaseModel):
    shot_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    status: Literal['not_reviewed', 'aligned', 'deviation', 'unavailable']
    note: str = Field(default='', max_length=500)


class RenderReviewSubmission(BaseModel):
    revision: int
    scene_revision: int
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['accepted', 'changes_requested']
    note: str = Field(default='', max_length=2000)
    shots: list[RenderShotReview] = Field(min_length=1, max_length=12)


class RenderRetakeSuggestionRequest(BaseModel):
    revision: int
    scene_revision: int
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: str = Field(default='', pattern=r'^[a-f0-9]{0,32}$')
    intent: str = Field(default='', max_length=1600)


class RenderRetakeApproval(BaseModel):
    revision: int
    suggestion_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    quote_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    approved_credits: int = Field(ge=1, le=100)


def install(gateway):
    app = gateway.app
    suggestion_slots=asyncio.Semaphore(2)
    def owner(auth): return gateway.require_session(auth)['id']
    def invalidate_render_intent(p):
        p.pop('scene_render_intent', None)
        p.pop('scene_render_review', None)
        p.pop('scene_retake_suggestions', None)
    def writable(p, revision):
        if p['revision'] != revision or p['id'] in store.RUNNING or p['state'] in ('planning', 'running', 'rendering') or p.get('image_task',{}).get('state')=='running':
            raise HTTPException(409, '项目已更新或正在制作，请重新打开场景')
    def asset_intent_view(p):
        intent = p.get('scene_asset_intent')
        if not isinstance(intent, dict):
            return None
        return {
            'id': str(intent.get('id', ''))[:32],
            'state': str(intent.get('state', 'draft'))[:24],
            'base_scene_revision': int(intent.get('base_scene_revision', 0)),
            'revision_after': int(intent.get('revision_after', 0)),
            'model': str(intent.get('model', ''))[:48],
            'skill_id': str(intent.get('skill_id', 'ad-video'))[:80],
            'skill_title': str(intent.get('skill_title', '商品广告导演'))[:120],
            'skill_version': int(intent.get('skill_version', 1)),
            'approval_mode': intent.get('approval_mode') if intent.get('approval_mode') in ('manual', 'auto') else 'manual',
            'prompt': str(intent.get('prompt', ''))[:1600],
            'reference_asset': intent.get('reference_asset'),
            'paid_generation': bool(intent.get('paid_generation', False)),
            'provider_task_id': str(intent.get('provider_task_id') or '')[:80] or None,
            'training_eligible': False,
            'created_at': intent.get('created_at'),
            'stale': p['revision'] != int(intent.get('revision_after', -1)),
        }
    def reference_asset_views(p):
        """Expose only owned image ids and human labels for the 3D draft picker."""
        labels = {}
        for node in p.get('canvas', {}).get('nodes', []):
            if node.get('kind') == 'image' and node.get('asset'):
                labels[str(node['asset'])] = str(node.get('label') or '')[:80]
        rows = []
        for aid, asset in p.get('canvas_assets', {}).items():
            if not isinstance(asset, dict) or asset.get('kind') != 'image':
                continue
            key = str(aid)[:32]
            rows.append({'id': key, 'label': labels.get(key) or str(asset.get('filename') or '参考图片')[:80]})
        return rows[:32]
    def asset_quote_view(p):
        quote = p.get('scene_asset_quote')
        if not isinstance(quote, dict):
            return None
        allowed = ('id', 'state', 'asset_intent_id', 'revision', 'model', 'model_label',
                   'provider', 'provider_available', 'credits', 'currency', 'limitation',
                   'quote_digest', 'requires_explicit_approval', 'approval_state',
                   'approved_credits', 'paid_generation', 'provider_task_id', 'provider_status',
                   'provider_progress', 'result_asset_id', 'bound_object_id', 'created_at', 'approval_attempted_at')
        view = {key: quote.get(key) for key in allowed if key in quote}
        view['stale'] = (p['revision'] != int(quote.get('revision', -1)) or
                         quote.get('asset_intent_id') != (p.get('scene_asset_intent') or {}).get('id'))
        return view
    def asset_task_view(p):
        intent = p.get('scene_asset_intent')
        stale = bool(intent and p['revision'] != int(intent.get('revision_after', -1)))
        return scene_asset_task_status(intent, asset_quote_view(p), stale=stale)
    def role_binding_view(p, spec=None):
        record = p.get('scene_role_bindings') if isinstance(p.get('scene_role_bindings'), dict) else {}
        spec = spec or (validate_scene(p['scene3d'], p.get('scene_assets', {})) if p.get('scene3d') else default_scene(p.get('aspect', '16:9')))
        current_hash = scene_hash(spec)
        rows = []
        for item in record.get('bindings', [])[:12]:
            if not isinstance(item, dict):
                continue
            rows.append({key: str(item.get(key) or '')[:48] for key in ('shot_id', 'object_id', 'role')})
        return {
            'version': 1,
            'scene_hash_prefix': str(record.get('scene_hash') or '')[:12] or None,
            'bindings': rows,
            'stale': bool(record) and record.get('scene_hash') != current_hash,
            'training_eligible': False,
        }
    def response(p):
        spec = validate_scene(p['scene3d'],p.get('scene_assets',{})) if p.get('scene3d') else default_scene(p.get('aspect', '16:9'))
        project_skill = p.get('skill') or {}
        return {'id': p['id'], 'revision': p['revision'], 'spec': spec, 'hash': scene_hash(spec), 'assets': p.get('scene_assets', {}),
                'layout_observation': layout_observation(spec, p.get('scene_assets', {})),
                'station_keyframe_observation': station_keyframe_observation(spec, p.get('scene_assets', {})),
                'station_manifest': station_manifest(spec),
                'project_skill': {'id': str(p.get('skill_id') or 'ad-video')[:80],
                                  'title': str(p.get('skill_title') or project_skill.get('title') or '商品广告导演')[:120],
                                  'version': int(project_skill.get('version') or 1)},
                'reference_assets': reference_asset_views(p),
                'suggestion':suggestion_view(p,p.get('scene_suggestions',{}).get(p.get('scene_suggestion_id'))),
                'asset_intent': asset_intent_view(p),
                'asset_quote': asset_quote_view(p),
                'asset_task': asset_task_view(p),
                'role_bindings': role_binding_view(p, spec)}
    def suggestion_view(p,job):
        if not job:return None
        view=dict(job,stale=p['revision']!=job['revision'])
        if job['state']=='running' and p['id'] not in store.RUNNING:
            view.update(state='interrupted',error='场景建议曾中断；原场景保留，没有重新调用模型。')
        return view
    async def body(request, maximum):
        data = bytearray()
        async for part in request.stream():
            if len(data)+len(part) > maximum: raise HTTPException(413, '文件超过大小限制')
            data.extend(part)
        return bytes(data)

    @app.get('/creative/scene', include_in_schema=False)
    def page(): return FileResponse(store.ROOT/'tools/agent_studio/scene.html', headers={'Cache-Control': 'no-store'})

    @app.get('/creative/scene/{filename}', include_in_schema=False)
    def static(filename: str):
        if filename not in ('scene.js', 'scene.css', 'scene-runtime.js', 'scene-timing.mjs', 'scene-risk.mjs', 'scene-risk-context.js', 'scene-workspace.js', 'scene-agent.js'): raise HTTPException(404)
        return FileResponse(store.ROOT/'tools/agent_studio'/filename, media_type='text/css' if filename.endswith('.css') else 'text/javascript', headers={'Cache-Control': 'no-cache'})

    @app.get('/creative/api/scene3d/default')
    def default_document(): return {'spec': default_scene()}

    @app.get('/creative/api/projects/{pid}/scene3d')
    def document(pid: str, authorization: str|None=Header(None)):
        return response(store.load(pid, owner(authorization)))

    @app.get('/creative/api/projects/{pid}/scene3d/render-preflight')
    def render_preflight(pid: str, authorization: str|None=Header(None)):
        """Return a bounded, read-only handoff package for AI video rendering.

        This endpoint deliberately does not enqueue a render, reserve credits, or
        mutate the scene. It makes the boundary between 3D authoring and video
        generation visible before a later, explicit submit action is added.
        """
        p = store.load(pid, owner(authorization))
        if not p.get('scene3d'):
            raise HTTPException(409, '请先保存 3D 场景，再核对视频渲染')
        try:
            spec = validate_scene(p['scene3d'], p.get('scene_assets', {}))
        except ValueError as exc:
            raise HTTPException(422, '场景无效：'+str(exc)[:400]) from exc

        quote = {}
        try:
            quote = project_quote(p)
        except (KeyError, ValueError):
            quote = {}
        model = str(p.get('model') or quote.get('model') or '')[:80]
        model_label = str(quote.get('label') or model or '未选择视频模型')[:100]
        approval = p.get('approval_mode') if p.get('approval_mode') in ('manual', 'auto') else 'manual'
        objects = spec.get('objects', [])
        trajectory = trajectory_manifest(spec)
        station = station_manifest(spec)
        layout = layout_observation(spec, p.get('scene_assets', {}))
        glb_ids = {str(aid) for aid in p.get('scene_assets', {}).keys()}
        glb_objects = [o for o in objects if o.get('kind') == 'glb' and str(o.get('asset')) in glb_ids]
        placeholders = [str(o.get('name') or '未命名对象')[:80] for o in objects
                        if '占位' in str(o.get('name') or '')]
        shots = [{
            'id': str(s.get('id', ''))[:80],
            'name': str(s.get('name') or '未命名镜头')[:80],
            'duration': float(s.get('duration', 0)),
            'path_points': len(s.get('camera', {}).get('points', [])),
            'path_sha256': next(row['path_sha256'] for row in trajectory['shots'] if row['shot_id'] == s['id']),
            'path_closed': bool(s.get('camera', {}).get('closed', False)),
            'path_easing': str(s.get('camera', {}).get('easing', 'smooth')),
            'path_length': next(row['path_length'] for row in trajectory['shots'] if row['shot_id'] == s['id']),
            'station_keyframe_count': min(24, len(s.get('station_keyframes', []))),
            'station_object_ids': [str(item.get('object_id') or '')[:48] for item in s.get('station_keyframes', [])[:12]],
        } for s in spec.get('shots', [])]
        valid_paths = bool(shots) and all(s['path_points'] >= 2 and s['duration'] >= .5 for s in shots)
        references = sum(len(v.get('references', [])) for v in p.get('scene_reference_batches', {}).values()
                        if isinstance(v, dict) and isinstance(v.get('references', []), list))
        checks = [
            {
                'id': 'product_asset', 'label': '商品 3D 资产',
                'status': 'passed' if glb_objects and not placeholders else 'needs_check',
                'detail': (f'{len(glb_objects)} 个 GLB 商品对象已绑定。' if glb_objects and not placeholders
                           else '需要导入并绑定至少一个真实 GLB，并移除名称含“占位”的商品对象。'),
            },
            {
                'id': 'camera_paths', 'label': '镜头与轨迹',
                'status': 'passed' if valid_paths else 'needs_check',
                'detail': (f'{len(shots)} 个镜头，轨迹点和时长均可用。' if valid_paths
                           else '每个镜头至少需要两个轨迹点和 0.5 秒时长。'),
            },
            {
                'id': 'render_config', 'label': '模型 / 审批 / 画幅',
                'status': 'passed' if model and approval in ('manual', 'auto') and spec.get('aspect') else 'needs_check',
                'detail': f'{model_label} · {"手动审批" if approval == "manual" else "自动审批"} · {spec.get("aspect", "未设置")}',
            },
            {
                'id': 'reference_frames', 'label': '参考帧',
                'status': 'passed' if references else 'needs_check',
                'detail': (f'已记录 {references} 张镜头参考帧，可回导演画布继续选择。' if references
                           else '尚未连接镜头参考帧；可回导演画布按镜头继续核对。'),
            },
            {
                'id': 'layout', 'label': '站位与重叠',
                'status': 'passed' if layout['status'] == 'clear' else 'needs_check',
                'detail': ('基础几何体没有检测到包围盒重叠。' if layout['status'] == 'clear'
                           else f"检测到 {len(layout['collisions'])} 组对象重叠，另有 {len(layout['unknown_bounds'])} 个 GLB 边界待人工核对。"),
            },
        ]
        ready = all(c['status'] == 'passed' for c in checks[:3])
        return {
            'id': pid,
            'revision': p['revision'],
            'scene_hash': scene_hash(spec),
            'trajectory_sha256': trajectory['sha256'],
            'station_sha256': station['sha256'],
            'trajectory': trajectory,
            'ready': ready,
            'model': model,
            'model_label': model_label,
            'approval_mode': approval,
            'aspect': spec.get('aspect', '16:9'),
            'shots': shots,
            'assets': {'glb': len(glb_objects), 'placeholders': placeholders[:16],
                       'lights': sum(o.get('kind') == 'light' for o in objects)},
            'references': references,
            'layout_observation': layout,
            'checks': checks,
            'render_request': {
                'scene_revision': p['revision'], 'scene_hash': scene_hash(spec),
                'trajectory_sha256': trajectory['sha256'],
                'station_sha256': station['sha256'],
                'model': model, 'approval_mode': approval, 'aspect': spec.get('aspect', '16:9'),
                'shots': shots,
            },
        }

    @app.post('/creative/api/projects/{pid}/scene3d/render-intent')
    async def confirm_render_intent(pid: str, data: RenderIntent, authorization: str|None=Header(None)):
        """Confirm a 3D handoff without starting paid video generation."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            current = p.get('scene_render_intent')
            if current and current.get('scene_revision') == data.revision and current.get('scene_hash') == data.scene_hash:
                if all(current.get(key) == value for key, value in (
                    ('model', data.model), ('approval_mode', data.approval_mode), ('aspect', data.aspect))):
                    if data.trajectory_sha256 and current.get('trajectory_sha256') != data.trajectory_sha256:
                        raise HTTPException(409, '已有渲染意图的轨迹版本不同，请重新核对')
                    if data.station_sha256 and current.get('station_sha256') != data.station_sha256:
                        raise HTTPException(409, '已有渲染意图的站位版本不同，请重新核对')
                    return {'project': store.present(p), 'intent': current}
                raise HTTPException(409, '已有渲染意图的模型或审批设置不同，请重新核对')
            packet = render_preflight(pid, authorization)
            if p['revision'] != data.revision or packet['revision'] != data.revision:
                raise HTTPException(409, '场景或项目已更新，请重新核对渲染准备包')
            if not packet['ready']:
                raise HTTPException(409, '渲染准备包仍有核心条件待核对')
            if any(packet[key] != value for key, value in (
                ('scene_hash', data.scene_hash), ('model', data.model),
                ('approval_mode', data.approval_mode), ('aspect', data.aspect))):
                raise HTTPException(409, '模型、审批、画幅或场景哈希已变化，请重新核对')
            if data.trajectory_sha256 and packet['trajectory_sha256'] != data.trajectory_sha256:
                raise HTTPException(409, '镜头轨迹版本已变化，请重新核对渲染准备包')
            if data.station_sha256 and packet['station_sha256'] != data.station_sha256:
                raise HTTPException(409, '对象站位版本已变化，请重新核对渲染准备包')
            intent = {
                'scene_revision': data.revision, 'scene_hash': data.scene_hash,
                'trajectory_sha256': packet['trajectory_sha256'],
                'station_sha256': packet['station_sha256'],
                'trajectory': packet['trajectory'],
                'model': data.model, 'approval_mode': data.approval_mode,
                'aspect': data.aspect, 'state': 'confirmed', 'created_at': time.time(),
            }
            p['scene_render_intent'] = intent
            p['revision'] += 1
            store.save(p, uid);store.event(p, 'tool', 'scene_render_intent_confirmed')
            return {'project': store.present(p), 'intent': intent}

    def review_digest(review):
        stable = {key: review.get(key) for key in ('revision', 'scene_revision', 'scene_hash', 'artifact_sha256', 'decision', 'note', 'shots')}
        return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def retake_suggestion_view(p, suggestion):
        view = {key: value for key, value in suggestion.items() if key not in ('request_digest',)}
        view['project_revision'] = p['revision']
        current_review = p.get('scene_render_review', {})
        view['stale'] = any((suggestion.get('scene_hash') != p.get('scene_render_intent', {}).get('scene_hash'),
                             suggestion.get('artifact_sha256') != current_review.get('artifact_sha256')))
        view['editor_url'] = f"/creative/editor?project={p['id']}&scene_retake={suggestion['id']}"
        candidates = [job for job in p.get('edit_retakes', {}).values()
                      if job.get('scene_retake_id') == suggestion['id']]
        if candidates:
            job = sorted(candidates, key=lambda item: item.get('created_at', 0))[-1]
            view['candidate'] = {key: job.get(key) for key in
                                 ('id', 'state', 'credits', 'approved_credits', 'asset',
                                  'candidate_sha256', 'qa', 'training_eligible', 'revision')}
            if job.get('completed_revision') is not None:
                view['candidate']['revision'] = job.get('completed_revision')
            if job.get('asset') and job.get('clip'):
                view['candidate']['media'] = {
                    'original_url': f"/creative/api/projects/{p['id']}/edit/source",
                    'candidate_url': f"/creative/api/projects/{p['id']}/edit/sources/{job['asset']}",
                    'source_start': job['clip'].get('start'),
                    'source_end': job['clip'].get('end'),
                    'duration': job.get('duration'),
                }
            if isinstance(job.get('candidate_review'), dict):
                view['candidate']['candidate_review'] = dict(job['candidate_review'])
        return view

    def retake_suggestion_list(p):
        return [retake_suggestion_view(p, suggestion) for suggestion in p.get('scene_retake_suggestions', {}).values()]

    def retake_billable_duration(model, duration):
        seconds = max(3, math.ceil(float(duration)))
        if model == 'kling-video-v2_5':
            if seconds <= 5:
                return 5
            if seconds <= 10:
                return 10
            raise ValueError('Kling 2.5 单个重拍镜头最长 10 秒')
        if model == 'MiniMax-H3':
            return max(4, seconds)
        if seconds > 15:
            raise ValueError('当前视频模型单个重拍镜头最长 15 秒')
        return seconds

    def provider_trajectory_for_project(p):
        """Return only the bounded provider camera metadata saved by a runner."""
        film = p.get('film') if isinstance(p.get('film'), dict) else {}
        view = provider_trajectory_view(film.get('provider_trajectory'))
        if view:
            return view
        rows = []
        for shot in p.get('shots', []):
            if not isinstance(shot, dict):
                continue
            shot_view = provider_trajectory_view(shot.get('provider_trajectory'))
            if not shot_view:
                continue
            for row in shot_view['shots']:
                item = dict(row)
                item.setdefault('shot_id', str(shot.get('id', ''))[:48])
                rows.append(item)
        if not rows:
            return None
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'version': 1, 'source': 'provider_status', 'observed': True,
                'sha256': digest, 'shots': rows, 'training_eligible': False}

    def render_review_packet(p, pid, artifact_sha256=None):
        intent = p.get('scene_render_intent')
        if not intent or not p.get('scene3d'):
            raise HTTPException(409, '请先确认 3D 渲染准备，再查看成片回放')
        try:
            spec = validate_scene(p['scene3d'], p.get('scene_assets', {}))
        except ValueError as exc:
            raise HTTPException(422, '场景无效：'+str(exc)[:400]) from exc
        trajectory = trajectory_manifest(spec)
        trajectory_rows = {row['shot_id']: row for row in trajectory['shots']}
        expected_trajectory = intent.get('trajectory_sha256')
        trajectory_matches = expected_trajectory in (None, trajectory['sha256'])
        starts = 0.0
        shots = []
        stored = p.get('scene_render_review')
        stored_shots = {item.get('shot_id'): item for item in stored.get('shots', [])} if isinstance(stored, dict) else {}
        for shot in spec['shots']:
            item = stored_shots.get(shot['id'], {})
            trajectory_row = trajectory_rows[shot['id']]
            shots.append({
                'id': shot['id'], 'name': shot['name'], 'start': starts,
                'duration': shot['duration'], 'end': starts + shot['duration'],
                'path_points': trajectory_row['path_points'],
                'path_sha256': trajectory_row['path_sha256'],
                'path_closed': trajectory_row['path_closed'],
                'path_easing': trajectory_row['path_easing'],
                'path_length': trajectory_row['path_length'],
                'status': item.get('status', 'not_reviewed'),
                'note': item.get('note', ''),
            })
            starts += shot['duration']
        actual = None
        media = None
        state = 'pending'
        if p.get('state') == 'completed' and p.get('artifact'):
            try:
                from harness.learning.governance import current_artifact
                artifact_sha256 = artifact_sha256 or current_artifact(p)
            except ValueError as exc:
                raise HTTPException(409, '成片文件不可读取，请恢复成片后重新回放') from exc
            actual = {k: p.get('qa', {}).get(k) for k in ('duration', 'width', 'height', 'audio', 'technical')}
            media = {'asset': 'final', 'url': f'/creative/api/projects/{pid}/media/final'}
            state = 'ready'
        if stored and artifact_sha256 and stored.get('artifact_sha256') != artifact_sha256:
            stored = None
        reviewed = stored is not None and stored.get('artifact_sha256') == artifact_sha256
        provider_trajectory = provider_trajectory_for_project(p)
        provider_comparison = evaluate_trajectory(trajectory['shots'], provider_trajectory)
        return {
            'state': state, 'project_revision': p['revision'],
            'scene_revision': intent['scene_revision'], 'scene_hash': intent['scene_hash'],
            'trajectory_sha256': trajectory['sha256'],
            'trajectory_lock': {
                'expected_sha256': expected_trajectory,
                'actual_sha256': trajectory['sha256'],
                'matches_scene_intent': trajectory_matches,
                'status': 'locked' if trajectory_matches else 'stale',
            },
            'model': intent['model'], 'approval_mode': intent['approval_mode'],
            'aspect': intent['aspect'], 'expected': {'duration': spec['duration'], 'shots': len(spec['shots'])},
            'actual': actual, 'artifact_sha256': artifact_sha256, 'media': media,
            'provider_trajectory': provider_trajectory,
            'trajectory_evaluation': {
                'status': 'manual_review_required',
                'message': provider_comparison['message'],
                'trajectory_sha256': trajectory['sha256'],
                'trajectory_lock': 'locked' if trajectory_matches else 'stale',
                'provider_metadata': provider_comparison,
                'evaluator': provider_comparison['evaluator'],
                'evaluator_version': provider_comparison['version'],
            },
            'reviewed': reviewed, 'review': stored if reviewed else None, 'shots': shots,
            'retake_suggestions': retake_suggestion_list(p),
        }

    @app.get('/creative/api/projects/{pid}/scene3d/render-review')
    def render_review(pid: str, authorization: str|None=Header(None)):
        uid = owner(authorization)
        return render_review_packet(store.load(pid, uid), pid)

    @app.post('/creative/api/projects/{pid}/scene3d/render-review')
    async def submit_render_review(pid: str, data: RenderReviewSubmission, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            packet = render_review_packet(p, pid)
            if packet['state'] != 'ready' or not packet['artifact_sha256']:
                raise HTTPException(409, '成片尚未完成，暂不能记录回放核对')
            if p['revision'] != data.revision or packet['scene_revision'] != data.scene_revision:
                raise HTTPException(409, '项目或 3D 场景版本已变化，请重新打开回放核对')
            if packet['scene_hash'] != data.scene_hash or packet['artifact_sha256'] != data.artifact_sha256:
                raise HTTPException(409, '场景或成片哈希已变化，请重新打开回放核对')
            expected = {shot['id'] for shot in packet['shots']}
            submitted = [shot.shot_id for shot in data.shots]
            if len(set(submitted)) != len(submitted) or set(submitted) != expected:
                raise HTTPException(422, '必须为当前 3D 场景的每个镜头各记录一次回放结果')
            if data.decision == 'accepted' and any(shot.status != 'aligned' for shot in data.shots):
                raise HTTPException(422, '接受成片前，请将所有镜头标为基本一致')
            review = {
                'revision': data.revision, 'scene_revision': data.scene_revision,
                'scene_hash': data.scene_hash, 'artifact_sha256': data.artifact_sha256,
                'trajectory_sha256': packet['trajectory_sha256'],
                'decision': data.decision, 'note': data.note.strip(),
                'shots': [shot.model_dump() for shot in data.shots],
                'created_at': time.time(), 'training_eligible': False,
            }
            current = p.get('scene_render_review')
            stable_keys = ('revision', 'scene_revision', 'scene_hash', 'artifact_sha256', 'trajectory_sha256', 'decision', 'note', 'shots', 'training_eligible')
            if isinstance(current, dict) and all(current.get(key) == review.get(key) for key in stable_keys):
                return {'project': store.present(p), 'review': current, 'packet': render_review_packet(p, pid)}
            p['scene_render_review'] = review
            p.pop('scene_retake_suggestions', None)
            store.save(p, uid); store.event(p, 'evaluator', 'scene_render_review_recorded')
            return {'project': store.present(p), 'review': review, 'packet': render_review_packet(p, pid)}

    @app.get('/creative/api/projects/{pid}/scene3d/render-review/retake-suggestions')
    def render_retake_suggestions(pid: str, authorization: str|None=Header(None)):
        p = store.load(pid, owner(authorization))
        return {'suggestions': retake_suggestion_list(p)}

    @app.post('/creative/api/projects/{pid}/scene3d/render-review/retake-suggestions')
    async def prepare_render_retake(pid: str, data: RenderRetakeSuggestionRequest, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            packet = render_review_packet(p, pid)
            if packet['state'] != 'ready' or not packet['artifact_sha256']:
                raise HTTPException(409, '成片尚未完成，暂不能准备重拍建议')
            if p['revision'] != data.revision or packet['scene_revision'] != data.scene_revision:
                raise HTTPException(409, '项目或 3D 场景版本已变化，请重新打开回放核对')
            if packet['scene_hash'] != data.scene_hash or packet['artifact_sha256'] != data.artifact_sha256:
                raise HTTPException(409, '场景或成片哈希已变化，请重新打开回放核对')
            review = packet.get('review')
            if not review or review.get('decision') != 'changes_requested':
                raise HTTPException(409, '请先保存“存在偏差”的回放核对结果')
            deviations = [shot for shot in packet['shots'] if shot['status'] in ('deviation', 'unavailable')]
            if not deviations:
                raise HTTPException(422, '请至少将一个镜头标为存在偏差或无法判断')
            if len(p.get('scene_retake_suggestions', {})) >= 20:
                raise HTTPException(422, '本项目最多保留 20 条 3D 重拍建议')
            request_digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
            existing = next((item for item in p.get('scene_retake_suggestions', {}).values()
                             if data.request_id and item.get('request_id') == data.request_id), None)
            if existing:
                if existing.get('request_digest') != request_digest:
                    raise HTTPException(409, '相同请求不能更换重拍要求')
                return {'suggestion': retake_suggestion_view(p, existing), 'packet': render_review_packet(p, pid)}
            intent = data.intent.strip() or '保持 3D 场景商品资产、站位与光照，优先修正以下镜头的商品外观、镜头轨迹或动作偏差。'
            render_intent = p.get('scene_render_intent', {})
            try:
                provider = str(p.get('provider') or 'kling')
                model = str(render_intent.get('model') or p.get('model') or '')
                spec = model_spec(provider, model)
                segments = []
                total = 0
                for shot in deviations:
                    billable = retake_billable_duration(spec['id'], shot['duration'])
                    credits = catalog_quote(provider, spec['id'], billable)
                    total += credits
                    segments.append({'shot_id': shot['id'], 'name': shot['name'], 'start': shot['start'],
                                     'end': shot['end'], 'duration': shot['duration'], 'billable_duration': billable,
                                     'credits': credits, 'status': shot['status'], 'note': shot['note'][:500]})
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(422, '当前视频模型暂时无法为这些镜头提供重拍报价，请先回导演画布选择可用模型') from exc
            suggestion_id = secrets.token_hex(16)
            suggestion = {
                'id': suggestion_id, 'request_id': data.request_id, 'revision': data.revision,
                'scene_revision': data.scene_revision, 'scene_hash': data.scene_hash,
                'trajectory_sha256': packet['trajectory_sha256'],
                'artifact_sha256': data.artifact_sha256, 'review_digest': review_digest(review),
                'model': spec['id'], 'model_label': spec['label'], 'provider': provider,
                'approval_mode': render_intent.get('approval_mode', 'manual'), 'aspect': packet['aspect'],
                'intent': intent, 'segments': segments, 'credits': total,
                'quote_digest': '', 'state': 'ready_for_approval',
                'requires_explicit_approval': True, 'training_eligible': False,
                'created_at': time.time(), 'request_digest': request_digest,
            }
            suggestion['quote_digest'] = hashlib.sha256(json.dumps({key: value for key, value in suggestion.items() if key != 'quote_digest' and key != 'request_digest'}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            p.setdefault('scene_retake_suggestions', {})[suggestion_id] = suggestion
            store.save(p, uid); store.event(p, 'tool', 'scene_retake_suggestion_prepared')
            return {'suggestion': retake_suggestion_view(p, suggestion), 'packet': render_review_packet(p, pid)}

    @app.post('/creative/api/projects/{pid}/scene3d/render-review/retake-suggestions/{suggestion_id}/approve')
    async def approve_render_retake(pid: str, suggestion_id: str, data: RenderRetakeApproval, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            suggestion = p.get('scene_retake_suggestions', {}).get(suggestion_id)
            if not suggestion:
                raise HTTPException(404, '找不到 3D 重拍建议')
            if data.suggestion_id != suggestion_id or data.revision != p['revision']:
                raise HTTPException(409, '项目或重拍建议版本已变化，请重新核对')
            if data.quote_digest != suggestion.get('quote_digest') or data.approved_credits != suggestion.get('credits'):
                raise HTTPException(409, '费用摘要或确认积分已变化，请重新核对重拍建议')
            packet = render_review_packet(p, pid)
            current_review = packet.get('review')
            if packet['state'] != 'ready' or not current_review or review_digest(current_review) != suggestion.get('review_digest'):
                raise HTTPException(409, '回放核对已变化，请重新准备重拍建议')
            if suggestion['state'] == 'approved_for_generation':
                return {'suggestion': retake_suggestion_view(p, suggestion), 'packet': packet}
            if suggestion['state'] != 'ready_for_approval':
                raise HTTPException(409, '当前重拍建议不可确认')
            suggestion.update(state='approved_for_generation', approved_credits=data.approved_credits, approved_at=time.time())
            store.save(p, uid); store.event(p, 'evaluator', 'scene_retake_suggestion_approved')
            return {'suggestion': retake_suggestion_view(p, suggestion), 'packet': render_review_packet(p, pid)}

    @app.post('/creative/api/projects/{pid}/scene3d/suggestions')
    async def suggest(pid:str,request:Request,authorization:str|None=Header(None)):
        uid=owner(authorization)
        try:data=SceneSuggestionRequest.model_validate_json(await body(request,11_500_000))
        except ValidationError as exc:raise HTTPException(422,'请提交场景目标与最多四张有效截图') from exc
        fingerprint=hashlib.sha256(data.model_dump_json().encode()).hexdigest()
        async with store.lock(pid):
            p=store.load(pid,uid);jobs=p.setdefault('scene_suggestions',{})
            if data.request_id in jobs:
                job=jobs[data.request_id]
                if job['request_digest']!=fingerprint:raise HTTPException(409,'同一请求不能更换目标或场景')
                return suggestion_view(p,job)
            writable(p,data.revision)
            if not p.get('scene3d'):raise HTTPException(409,'请先保存当前场景')
            if len(jobs)>=100:raise HTTPException(422,'本项目最多保留 100 次场景建议')
            spec=validate_scene(p['scene3d'],p.get('scene_assets',{}))
            if scene_hash(spec)!=data.scene_hash:raise HTTPException(409,'场景已变化，请重新核对')
            try:observations=await asyncio.to_thread(observe_scene,spec,data)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            job=dict(id=data.request_id,revision=p['revision'],request_digest=fingerprint,base_digest=data.scene_hash,
                     state='running',intent=data.intent,training_eligible=False)
            jobs[job['id']]=job;p['scene_suggestion_id']=job['id'];store.save(p,uid)
            store.event(p,'tool','scene_observation_completed');store.event(p,'agent','scene_suggestion_requested')
            selection=dict(object=data.selected_object,shot=data.selected_shot)
            store.RUNNING[pid]=asyncio.create_task(run_scene_suggestion(pid,uid,job['id'],p,data.intent,selection,observations,suggestion_slots))
            return suggestion_view(p,job)

    @app.post('/creative/api/projects/{pid}/scene3d/asset-intent')
    async def save_asset_intent(pid: str, data: SceneAssetIntent, authorization: str|None=Header(None)):
        """Persist a bounded 3D asset generation draft without calling a provider or charging credits."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, data.revision)
            if not p.get('scene3d'):
                raise HTTPException(409, '请先保存当前 3D 场景，再保存资产生成草稿')
            prompt = data.prompt.strip()
            if len(prompt) < 2:
                raise HTTPException(422, '资产描述至少需要 2 个字符')
            from harness.studio.templates import find_skill
            skill = find_skill(data.skill_id, uid, data.skill_version)
            if data.reference_asset:
                reference = p.get('canvas_assets', {}).get(data.reference_asset)
                if not reference or reference.get('kind') != 'image':
                    raise HTTPException(422, '3D 资产参考图必须是当前项目中的图片')
            intent = {
                'id': secrets.token_hex(16),
                'state': 'draft',
                'base_scene_revision': data.revision,
                'revision_after': data.revision + 1,
                'model': data.model,
                'skill_id': skill['id'],
                'skill_title': skill.get('title', skill['id']),
                'skill_version': int(skill.get('version') or 1),
                'approval_mode': data.approval_mode,
                'prompt': prompt,
                'reference_asset': data.reference_asset,
                'paid_generation': False,
                'provider_task_id': None,
                'training_eligible': False,
                'created_at': time.time(),
            }
            invalidate_render_intent(p)
            p['scene_asset_intent'] = intent
            p.pop('scene_asset_quote', None)
            p['revision'] += 1
            store.save(p, uid)
            store.event(p, 'tool', 'scene_asset_intent_saved')
            return response(p)

    @app.get('/creative/api/projects/{pid}/scene3d/asset-intent/quote')
    def get_asset_quote(pid: str, authorization: str|None=Header(None)):
        p = store.load(pid, owner(authorization))
        return {'quote': asset_quote_view(p), 'task': asset_task_view(p)}

    @app.get('/creative/api/projects/{pid}/scene3d/asset-intent/status')
    def get_asset_task_status(pid: str, authorization: str|None=Header(None)):
        """Return only the bounded 3D asset task state; never poll a provider."""
        p = store.load(pid, owner(authorization))
        return {'task': asset_task_view(p)}

    @app.post('/creative/internal/scene-asset-callback', include_in_schema=False)
    async def scene_asset_callback(request: Request):
        """Accept a signed, bounded 3D asset status callback.

        The trusted worker must upload and validate a GLB separately; this
        callback can only reference an already-owned scene asset ID.
        """
        secret = os.getenv('CREATIVE_3D_ASSET_CALLBACK_SECRET', '')
        if not secret:
            raise HTTPException(503, '3D 资产回调尚未配置')
        raw = await request.body()
        if len(raw) > 64 * 1024:
            raise HTTPException(413, '3D 资产回调超过大小限制')
        timestamp = request.headers.get('X-Provider-Timestamp', '')
        signature = request.headers.get('X-Provider-Signature', '')
        try:
            parsed_timestamp = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise HTTPException(401, '3D 资产回调签名无效') from exc
        if abs(time.time() - parsed_timestamp) > 300:
            raise HTTPException(401, '3D 资产回调已过期')
        expected = hmac.new(secret.encode(), (timestamp + '.').encode() + raw, hashlib.sha256).hexdigest()
        if signature.startswith('sha256='):
            signature = signature[7:]
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, '3D 资产回调签名无效')
        try:
            body_data = json.loads(raw)
            data = SceneAssetProviderCallback.model_validate(body_data)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(422, '3D 资产回调格式无效') from exc
        callback_digest = hashlib.sha256(raw).hexdigest()
        projection = {'status': data.status}
        if data.progress is not None:
            projection['progress'] = data.progress
        if data.result_asset_id:
            projection['result_asset_id'] = data.result_asset_id
        with store.connection() as c:
            row = c.execute('SELECT owner FROM projects WHERE id=?', (data.project_id,)).fetchone()
        if not row:
            raise HTTPException(404, '找不到回调对应的项目')
        received_at = time.time()
        async with store.lock(data.project_id):
            saved, idempotent, prior = store.apply_scene_asset_callback(
                data.project_id, row[0], data.asset_intent_id, data.task_id,
                callback_digest, data.status, projection, received_at,
                data.result_asset_id)
            if idempotent:
                return {'accepted': True, 'idempotent': True,
                        'status': prior['status'], 'training_eligible': False}
            event = store.event
            event(saved, 'observation', 'scene_asset_callback_received', '3d_asset')
            return {'accepted': True, 'idempotent': False, 'status': data.status,
                    'progress': data.progress, 'result_asset_id': data.result_asset_id,
                    'training_eligible': False}

    @app.post('/creative/api/projects/{pid}/scene3d/asset-intent/quote')
    async def create_asset_quote(pid: str, data: SceneAssetQuoteRequest, authorization: str|None=Header(None)):
        """Create a bounded availability quote without reserving credits or calling a provider."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, data.revision)
            intent = p.get('scene_asset_intent')
            if not isinstance(intent, dict):
                raise HTTPException(409, '请先保存 3D 资产生成草稿')
            if p['revision'] != int(intent.get('revision_after', -1)):
                raise HTTPException(409, '3D 资产草稿已过期，请重新保存后再报价')
            try:
                catalog = scene_asset_quote(str(intent.get('model', '')))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            quote = {
                'id': secrets.token_hex(16), 'state': 'provider_unconfigured',
                'asset_intent_id': intent['id'], 'revision': p['revision'],
                **catalog, 'quote_digest': '', 'requires_explicit_approval': True,
                'approval_state': 'not_requested', 'approved_credits': None,
                'paid_generation': False, 'provider_task_id': None,
                'training_eligible': False, 'created_at': time.time(),
            }
            digest_payload = {key: value for key, value in quote.items() if key not in ('quote_digest', 'created_at')}
            quote['quote_digest'] = hashlib.sha256(json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            p['scene_asset_quote'] = quote
            store.save(p, uid)
            store.event(p, 'tool', 'scene_asset_quote_prepared')
            return {'quote': asset_quote_view(p), 'task': asset_task_view(p), 'project': store.present(p)}

    @app.post('/creative/api/projects/{pid}/scene3d/asset-intent/approve')
    async def approve_asset_quote(pid: str, data: SceneAssetApproval, authorization: str|None=Header(None)):
        """Record an explicit approval attempt, but never submit an unavailable provider."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, data.revision)
            quote = p.get('scene_asset_quote')
            if not isinstance(quote, dict):
                raise HTTPException(409, '请先生成当前版本的 3D 资产报价')
            if p['revision'] != data.revision or int(quote.get('revision', -1)) != p['revision']:
                raise HTTPException(409, '报价或项目版本已变化，请重新报价')
            if quote.get('quote_digest') != data.quote_digest:
                raise HTTPException(409, '报价摘要已变化，请重新报价')
            if quote.get('approval_state') == 'blocked_provider_unconfigured':
                return {'quote': asset_quote_view(p), 'task': asset_task_view(p), 'project': store.present(p),
                        'message': '3D 供应商适配器尚未配置，未提交任务或扣费'}
            quote['approval_state'] = 'blocked_provider_unconfigured'
            quote['approval_attempted_at'] = time.time()
            quote['approved_credits'] = None
            quote['paid_generation'] = False
            quote['provider_task_id'] = None
            store.save(p, uid)
            store.event(p, 'tool', 'scene_asset_approval_blocked')
            return {'quote': asset_quote_view(p), 'task': asset_task_view(p), 'project': store.present(p),
                    'message': '3D 供应商适配器尚未配置，未提交任务或扣费'}

    @app.post('/creative/api/projects/{pid}/scene3d/asset-intent/bind')
    async def bind_asset_result(pid: str, data: SceneAssetBind, authorization: str|None=Header(None)):
        """Explicitly bind a verified callback result as a scene GLB object."""
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid)
            writable(p, data.revision)
            intent = p.get('scene_asset_intent') if isinstance(p.get('scene_asset_intent'), dict) else None
            quote = p.get('scene_asset_quote') if isinstance(p.get('scene_asset_quote'), dict) else None
            if not intent or not quote or quote.get('asset_intent_id') != intent.get('id'):
                raise HTTPException(409, '当前没有可绑定的 3D 资产任务')
            if quote.get('provider_status') != 'completed' or quote.get('result_asset_id') != data.asset_id:
                raise HTTPException(409, '3D 资产尚未完成回调或结果已变化')
            if data.asset_id not in p.get('scene_assets', {}):
                raise HTTPException(422, 'GLB 资产不属于当前项目')
            spec = validate_scene(p.get('scene3d') or default_scene(p.get('aspect', '16:9')), p.get('scene_assets', {}))
            bound_id = str(quote.get('bound_object_id') or '')
            if bound_id and any(obj.get('id') == bound_id for obj in spec.get('objects', [])):
                return {'object_id': bound_id, 'project': store.present(p), 'scene': response(p), 'idempotent': True}
            if len(spec['objects']) >= 32:
                raise HTTPException(422, '场景对象已满，无法绑定新的 GLB')
            object_id = 'asset_' + secrets.token_hex(10)
            object_spec = {
                'id': object_id, 'name': '回调资产 · ' + data.asset_id[:8], 'kind': 'glb',
                'position': [0, 1, 0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1],
                'color': '#b6c7ca', 'roughness': .4, 'metalness': .1,
                'intensity': 40, 'asset': data.asset_id, 'visible': True,
            }
            spec['objects'].append(object_spec)
            spec = validate_scene(spec, p.get('scene_assets', {}))
            invalidate_render_intent(p)
            p['scene3d'] = spec
            quote['bound_object_id'] = object_id
            quote['approval_state'] = 'bound'
            p['revision'] += 1
            intent['revision_after'] = p['revision']
            quote['revision'] = p['revision']
            digest_payload = {key: value for key, value in quote.items()
                              if key not in ('quote_digest', 'created_at')}
            quote['quote_digest'] = hashlib.sha256(json.dumps(
                digest_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            store.save(p, uid)
            store.event(p, 'tool', 'scene_asset_bound')
            return {'object_id': object_id, 'project': store.present(p), 'scene': response(p), 'idempotent': False}

    @app.get('/creative/api/projects/{pid}/scene3d/suggestions/{job_id}')
    def suggestion(pid:str,job_id:str,authorization:str|None=Header(None)):
        p=store.load(pid,owner(authorization));job=p.get('scene_suggestions',{}).get(job_id)
        if not job:raise HTTPException(404,'找不到场景建议')
        return suggestion_view(p,job)

    @app.put('/creative/api/projects/{pid}/scene3d')
    async def save_scene(pid: str, data: SceneEdit, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, data.revision)
            try: spec = validate_scene(data.spec, p.get('scene_assets', {}))
            except ValueError as exc: raise HTTPException(422, '场景无效：'+str(exc)[:500]) from exc
            invalidate_render_intent(p);p['scene3d'] = spec; p['revision'] += 1; store.save(p, uid); store.event(p, 'tool', 'scene_saved')
            return response(p)

    @app.post('/creative/api/projects/{pid}/scene3d/role-bindings')
    async def save_role_bindings(pid: str, data: SceneRoleBindingSave, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, data.revision)
            try:
                spec = validate_scene(p.get('scene3d') or default_scene(p.get('aspect', '16:9')), p.get('scene_assets', {}))
            except ValueError as exc:
                raise HTTPException(422, '场景无效：' + str(exc)[:500]) from exc
            current_hash = scene_hash(spec)
            if current_hash != data.scene_hash:
                raise HTTPException(409, '场景已变化，请重新打开角色绑定')
            shot_ids = {str(item.get('id')) for item in spec.get('shots', [])}
            object_ids = {str(item.get('id')) for item in spec.get('objects', []) if item.get('kind') not in ('light', 'plane')}
            seen_shots = set()
            rows = []
            for item in data.bindings:
                if item.shot_id not in shot_ids:
                    raise HTTPException(422, '角色绑定引用了不存在的镜头')
                if item.object_id not in object_ids:
                    raise HTTPException(422, '角色绑定只能选择当前场景中的可移动对象')
                if item.shot_id in seen_shots:
                    raise HTTPException(422, '同一镜头只能保存一条角色绑定')
                seen_shots.add(item.shot_id)
                rows.append(item.model_dump())
            invalidate_render_intent(p)
            p['scene_role_bindings'] = {
                'version': 1, 'scene_hash': current_hash, 'revision_before': p['revision'],
                'bindings': rows, 'training_eligible': False,
            }
            p['revision'] += 1
            p['scene_role_bindings']['revision_after'] = p['revision']
            store.save(p, uid); store.event(p, 'tool', 'scene_role_bindings_saved')
            return response(p)

    @app.post('/creative/api/projects/{pid}/scene3d/assets')
    async def upload(pid: str, revision: int, request: Request, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, revision)
            if len(p.get('scene_assets', {})) >= 16: raise HTTPException(422, '每个项目最多导入 16 个 GLB')
            raw = await body(request, MAX_GLB)
            try: meta = await asyncio.to_thread(validate_glb, raw)
            except ValueError as exc: raise HTTPException(422, str(exc)) from exc
            aid = secrets.token_hex(16); directory = store.DATA/'scenes'/pid/aid
            directory.mkdir(parents=True, mode=0o700); path=directory/'source.glb'; path.write_bytes(raw); path.chmod(0o600)
            meta.update(id=aid); p.setdefault('scene_assets', {})[aid] = meta
            invalidate_render_intent(p)
            p['revision'] += 1; store.save(p, uid); store.event(p, 'tool', 'scene_asset_uploaded')
            return {'revision': p['revision'], 'asset': meta}

    @app.get('/creative/api/projects/{pid}/scene3d/assets/{aid}')
    def asset(pid: str, aid: str, authorization: str|None=Header(None)):
        p = store.load(pid, owner(authorization))
        if aid not in p.get('scene_assets', {}): raise HTTPException(404, '找不到 3D 资产')
        return FileResponse(store.DATA/'scenes'/pid/aid/'source.glb', media_type='model/gltf-binary', headers={'Cache-Control': 'private, no-store'})

    @app.post('/creative/api/projects/{pid}/scene3d/reference')
    async def reference(pid: str, revision: int, at: float, request: Request, authorization: str|None=Header(None)):
        uid = owner(authorization)
        async with store.lock(pid):
            p = store.load(pid, uid); writable(p, revision)
            spec = validate_scene(p['scene3d'],p.get('scene_assets',{})) if p.get('scene3d') else None
            if not spec or not 0 <= at <= spec['duration']: raise HTTPException(422, '请保存有效场景并选择预演时间')
            graph = p.get('canvas', {'nodes': [], 'edges': []})
            if len(graph['nodes']) >= 16 or len(p.get('canvas_assets', {})) >= 32:
                raise HTTPException(422, '画布参考已满，请先整理素材')
            # Check connected input limits before persisting another asset.
            if sum(n['kind'] != 'text' for n in graph['nodes'] if any(e['source']==n['id'] for e in graph['edges'])) >= 6:
                raise HTTPException(422, '已连接 6 个参考，请先断开不需要的参考')
            raw = await body(request, 5*1024*1024)
            try: asset = await asyncio.to_thread(save_asset, p, raw, 'image')
            except ValueError as exc: raise HTTPException(422, str(exc)) from exc
            asset['provenance'] = {'kind': 'scene_browser_preview', 'scene_hash': scene_hash(spec), 'at': at, 'shot_id': shot_at(spec,at)['shot']['id'], 'local_time': shot_at(spec,at)['local'], 'verified_render': False}
            p.setdefault('canvas_assets', {})[asset['id']] = asset
            nid = 'scene_'+secrets.token_hex(6)
            note = shot_note(spec,at)
            graph['nodes'].append(dict(id=nid, kind='image', label=f'3D 预演 · {at:.1f}s', text=note[:4000], asset=asset['id'], **next_position(graph)))
            graph['edges'].append(dict(source=nid, target='director')); p['canvas'] = validate_graph(graph, p['canvas_assets'])
            store.archive_render(p);invalidate_render_intent(p)
            p.update(state='intake', shots=[], questions=[], error='')
            for key in ('run_id', 'artifact', 'qa', 'stop_requested', 'film'): p.pop(key, None)
            p['revision'] += 1; store.save(p, uid); store.event(p, 'tool', 'scene_reference_added')
            return {'revision': p['revision'], 'asset': asset, 'node': nid}


    @app.post('/creative/api/projects/{pid}/scene3d/references')
    async def references(pid: str, request: Request, authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid)
            try:data=FrameBatch.model_validate_json(await body(request,17_000_000))
            except ValidationError as exc:raise HTTPException(422,'请提交最多六张有效镜头参考帧') from exc
            digest=request_hash(data);prior=p.get('scene_reference_batches',{}).get(data.request_id)
            if prior:
                if prior['request_hash']!=digest:raise HTTPException(409,'相同请求不能更换镜头或图片')
                return dict(revision=p['revision'],references=prior['references'])
            writable(p,data.revision)
            if len(p.get('scene_reference_batches',{}))>=100:raise HTTPException(422,'项目镜头参考记录已满')
            try:updated,records=await asyncio.to_thread(publish_frames,p,data)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            if data.connect_to_director:
                store.archive_render(updated)
                updated.update(state='intake',shots=[],questions=[],error='')
                for k in ('run_id','artifact','qa','stop_requested','film','auto_approval'):updated.pop(k,None)
            invalidate_render_intent(updated);updated['revision']+=1
            updated.setdefault('scene_reference_batches',{})[data.request_id]=dict(request_hash=digest,references=records)
            store.save(updated,uid);store.event(updated,'tool','scene_references_added')
            return dict(revision=updated['revision'],references=records)
