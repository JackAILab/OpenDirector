"""Account-scoped project API; private project data is separate from event trajectory."""
import asyncio
import json
import hashlib
import hmac
import os
import re
from pathlib import Path
import secrets
import sqlite3
import time
from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
from harness.agents.creative_director import direct
from harness.models.video_catalog import MODELS, PENDING_MODELS, model_spec, project_quote
from harness.tools.creative_video import CreativeVideoTool, provider_trajectory_observation, provider_status_projection
from harness.tools.creative_render import render, probe
from harness.tools.creative_reference import MAX_UPLOAD, save_reference, reference_path
from harness.tools.creative_canvas import MAX_CANVAS_UPLOAD, validate_graph, input_signature, save_asset, asset_directory, asset_metadata

from harness.studio.store import (ROOT, DATA, RUNNING, connection, load, save, event, present, lock,
                                  archive_render, apply_provider_callback)
from harness.core.creative_runner import production
from harness.tools.creative_message_context import record_message_context
from harness.tools.creative_workspace_context import sync_context

class Create(BaseModel):
    message: str = Field(min_length=2, max_length=5000)
    provider: Literal['kling','minimax-h3'] = 'kling'
    model: str | None = None
    aspect: Literal['16:9','9:16','1:1'] = '16:9'
    duration: int = Field(default=15,ge=3,le=30)
    skill_id: str = 'ad-video'
    skill_version: int | None = Field(default=None,ge=1,le=100)
    approval_mode: Literal['manual','auto'] = 'manual'
    creation_mode: Literal['agent','video','image'] = 'agent'
    image_model: str | None = None


class ManualNodeReference(BaseModel):
    model_config={'extra':'forbid'}
    revision:int
    asset:str=Field(pattern=r'^[a-f0-9]{32}$')


class ManualNodePosition(BaseModel):
    x: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    y: float = Field(ge=-10000, le=10000, allow_inf_nan=False)


class ManualPrompt(BaseModel):
    model: str | None = None
    duration: int | None = Field(default=None,ge=3,le=30)
    revision: int
    prompt: str = Field(min_length=2,max_length=4000)


class ModelSettings(BaseModel):
    revision: int
    model: str


class CreativeSettings(BaseModel):
    revision: int
    skill_id: str = Field(max_length=80)
    skill_version: int | None = Field(default=None,ge=1,le=100)
    approval_mode: Literal['manual','auto']


class ReferenceConfirm(BaseModel):
    revision: int
    reference_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class Message(BaseModel):
    text: str = Field(default='',max_length=5000)
    background: bool = False
    request_id: str = Field(default='', pattern=r'^[a-f0-9]{0,32}$')
    mode: Literal['interview','plan'] = 'interview'
    revision: int
    auto_approve_credits: int | None = Field(default=None, ge=0, le=100)


class Start(BaseModel):
    revision: int
    approved_credits: int = Field(ge=0,le=100)


class Edit(BaseModel):
    revision: int
    shots: list[dict] = Field(min_length=2,max_length=4)


class CanvasEdit(BaseModel):
    revision: int
    nodes: list[dict] = Field(default_factory=list, max_length=16)
    edges: list[dict] = Field(default_factory=list, max_length=16)
    groups: list[dict] = Field(default_factory=list, max_length=8)


class CanvasLayout(CanvasEdit):
    sizes: dict = Field(default_factory=dict)




class Review(BaseModel):
    revision: int
    decision: Literal['approved', 'changes_requested']
    note: str = Field(default='', max_length=2000)


def install(gateway):
    app = gateway.app
    from harness.studio.management_api import install as install_management
    install_management(gateway)
    from harness.studio.templates import install as install_templates
    install_templates(gateway)
    from harness.studio.edit_api import install as install_edit
    install_edit(gateway)
    from harness.studio.retake_api import install as install_retakes
    install_retakes(gateway)
    from harness.studio.scene_api import install as install_scene
    install_scene(gateway)
    from harness.studio.library_api import install as install_library
    install_library(gateway)
    from harness.studio.image_api import install as install_images
    install_images(gateway)
    from harness.studio.image_transform_api import install as install_image_transforms
    install_image_transforms(gateway)
    from harness.studio.video_inputs_api import install as install_video_inputs
    install_video_inputs(gateway)
    from harness.studio.learning_api import install as install_learning
    install_learning(gateway)
    from harness.studio.learning_review_api import install as install_learning_review
    install_learning_review(gateway)
    from harness.studio.learning_curation_api import install as install_learning_curation
    install_learning_curation(gateway)
    from harness.studio.learning_candidate_api import install as install_learning_candidates
    install_learning_candidates(gateway)
    def owner(auth): return gateway.require_session(auth)['id']

    status_lock = asyncio.Lock()
    status_cache = {}

    @app.get('/creative/api/model-status')
    async def model_status(authorization: str|None=Header(None)):
        owner(authorization)
        from harness.models.studio_status import check_pool
        async with status_lock:
            if status_cache and time.monotonic() - status_cache['updated'] < 30:
                return status_cache['result']
            pools = {'kling': [], 'minimax-h3': []}
            if all(hasattr(gateway, name) for name in ('primary_provider', 'worker_urls', 'external_workers')):
                try:
                    primary = gateway.primary_provider()
                    if primary in pools:
                        pools[primary] = [(url, False) for url in gateway.worker_urls()]
                    pools['minimax-h3'] += [(w['url'], True) for w in gateway.external_workers() if w.get('enabled', True)]
                except HTTPException:
                    # Invalid registry must not hide a still functioning local service.
                    pass
            checked = await asyncio.gather(*(check_pool(pools[p]) for p in pools))
            services = dict(zip(pools, checked))
            result = {'models': [dict(id=m['id'], **services[m['provider']]) for m in MODELS],
                      'cache_seconds': 30,
                      'status_note': '仅检查制作服务连通和正在处理状态；未检查供应商授权、余额或排队长度，不产生生成费用。图片服务暂未核验。'}
            status_cache.update(updated=time.monotonic(), result=result)
            return result

    @app.post('/creative/internal/provider-callback', include_in_schema=False)
    async def provider_callback(request: Request):
        """Accept a signed, bounded provider observation without exposing raw payloads."""
        secret = os.getenv('CREATIVE_PROVIDER_CALLBACK_SECRET', '')
        if not secret:
            raise HTTPException(503, '供应商回调尚未配置')
        raw = await request.body()
        if len(raw) > 256 * 1024:
            raise HTTPException(413, '供应商回调超过大小限制')
        timestamp = request.headers.get('X-Provider-Timestamp', '')
        signature = request.headers.get('X-Provider-Signature', '')
        try:
            parsed_timestamp = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise HTTPException(401, '供应商回调签名无效') from exc
        if abs(time.time() - parsed_timestamp) > 300:
            raise HTTPException(401, '供应商回调已过期')
        expected = hmac.new(secret.encode(), (timestamp + '.').encode() + raw, hashlib.sha256).hexdigest()
        if signature.startswith('sha256='):
            signature = signature[7:]
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, '供应商回调签名无效')
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, '供应商回调格式无效') from exc
        if not isinstance(body, dict):
            raise HTTPException(422, '供应商回调格式无效')
        pid = body.get('project_id')
        job_id = body.get('job_id')
        status = body.get('status')
        if not isinstance(pid, str) or not re.fullmatch(r'[a-f0-9]{24}', pid):
            raise HTTPException(422, '项目标识无效')
        if not isinstance(job_id, str) or not 1 <= len(job_id) <= 128:
            raise HTTPException(422, '任务标识无效')
        if status not in ('queued', 'preparing', 'running', 'processing', 'completed',
                          'failed', 'error', 'cancelled', 'canceled', 'uncertain'):
            raise HTTPException(422, '供应商状态不在允许范围')
        callback_digest = hashlib.sha256(raw).hexdigest()
        status_projection = provider_status_projection(body)
        with connection() as c:
            row = c.execute('SELECT data, owner FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:
            raise HTTPException(404, '找不到回调对应的项目')
        uid = row[1]
        observation = provider_trajectory_observation(body)
        received_at = time.time()
        async with lock(pid):
            p, target_kind, idempotent, _target, prior = apply_provider_callback(
                pid, uid, job_id, callback_digest, status, status_projection, observation, received_at)
            if idempotent:
                projection = prior['projection']
                return {'accepted': True, 'idempotent': True, 'target': target_kind,
                        'status': prior['status'],
                        'trajectory_observed': bool(projection.get('trajectory_observed')),
                        'training_eligible': False}
            event(p, 'observation', 'provider_callback_received', target_kind)
            return {'accepted': True, 'idempotent': False, 'target': target_kind,
                    'status': status, 'trajectory_observed': bool(observation),
                    'trajectory_sha256': observation['sha256'] if observation else None,
                    'training_eligible': False}

    @app.get('/creative/login',include_in_schema=False)
    def login_page(): return FileResponse(ROOT/'tools/agent_studio/login.html',headers={'Cache-Control':'no-store'})

    @app.get('/creative',include_in_schema=False)
    def creative_page(): return FileResponse(ROOT/'tools/agent_studio/index.html',headers={'Cache-Control':'no-store'})

    @app.get('/creative/canvas.js',include_in_schema=False)
    def canvas_script(): return FileResponse(ROOT/'tools/agent_studio/canvas.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/creative/canvas.css',include_in_schema=False)
    def canvas_style(): return FileResponse(ROOT/'tools/agent_studio/canvas.css',media_type='text/css',headers={'Cache-Control':'no-store'})

    @app.get('/creative/font.woff2',include_in_schema=False)
    def font(): return FileResponse(ROOT/'tools/asset_studio/public/fonts/studio-chinese.woff2')

    @app.get('/creative/api/models')
    def models(authorization: str|None=Header(None)):
        owner(authorization)
        from harness.models.studio_image import image_models
        from harness.tools.creative_video_inputs import capabilities
        return {'models':[dict(m,available=bool(m.get('single_film')),
                              capability_status='verified' if m.get('single_film') else 'unsupported',
                              service_status='unchecked', video_input_modes=capabilities(m['id'])) for m in MODELS]+list(PENDING_MODELS),
                'image_models':image_models(),
                'status_note':'可选表示已接入当前制作合同；此目录未检查供应商实时健康、余额或排队情况。',
                'pricing_note':'平台积分，非供应商灵感值；每开始 5 秒计费一次'}

    @app.get('/creative/workspace.js',include_in_schema=False)
    def workspace_script(): return FileResponse(ROOT/'tools/agent_studio/workspace.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/creative/workspace.css',include_in_schema=False)
    def workspace_style(): return FileResponse(ROOT/'tools/agent_studio/workspace.css',media_type='text/css',headers={'Cache-Control':'no-store'})

    @app.get('/creative/theme.css',include_in_schema=False)
    def theme_style(): return FileResponse(ROOT/'tools/agent_studio/theme.css',media_type='text/css',headers={'Cache-Control':'no-store'})

    @app.get('/creative/theme.js',include_in_schema=False)
    def theme_script(): return FileResponse(ROOT/'tools/agent_studio/theme.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/creative/portal.js',include_in_schema=False)
    def portal_script(): return FileResponse(ROOT/'tools/agent_studio/portal.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/creative/portal.css',include_in_schema=False)
    def portal_style(): return FileResponse(ROOT/'tools/agent_studio/portal.css',media_type='text/css',headers={'Cache-Control':'no-store'})

    @app.get('/creative/creative-controls.js',include_in_schema=False)
    def creative_controls(): return FileResponse(ROOT/'tools/agent_studio/creative-controls.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.put('/creative/api/projects/{pid}/model')
    async def change_model(pid: str,body: ModelSettings,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=body.revision or pid in RUNNING or p['state'] in ('running','rendering','planning'):
                raise HTTPException(409,'项目已更新或正在处理，请结束后再切换模型')
            spec=next((m for m in MODELS if m['id']==body.model),None)
            if not spec or not spec.get('single_film'):raise HTTPException(422,'该模型尚不支持已验证的 15 秒有声整片路径')
            if p.get('model')==body.model and p.get('generation_mode')=='single_native':return present(p)
            if p.get('video_inputs') and p['model']!=body.model:
                raise HTTPException(409,'请在视频参考窗口同时选择模型与参考模式，避免丢弃已确认图片')
            archive_render(p)
            p.update(model=spec['id'],provider=spec['provider'],generation_mode='single_native',duration=15,state='intake',shots=[],questions=[],error='')
            for k in ('run_id','artifact','qa','stop_requested','film'):p.pop(k,None)
            p['revision']+=1;save(p,uid);event(p,'task','model_changed')
            return present(p)

    @app.get('/creative/api/projects')
    def projects(authorization: str|None=Header(None)):
        uid=owner(authorization)
        with connection() as c: rows=c.execute('SELECT data FROM projects WHERE owner=?',(uid,)).fetchall()
        return sorted([{'id':p['id'],'title':p.get('brief',{}).get('product') or '新创作','state':p['state'],'review_status':p.get('qa',{}).get('human','pending'),'updated_at':p['updated_at']} for (data,) in rows for p in [json.loads(data)]],key=lambda p:p['updated_at'],reverse=True)

    @app.put('/creative/api/projects/{pid}/creative-settings')
    async def creative_settings(pid: str,body: CreativeSettings,authorization: str|None=Header(None)):
        uid=owner(authorization)
        from harness.studio.templates import find_skill
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=body.revision or pid in RUNNING or p['state'] in ('planning','running','rendering'):
                raise HTTPException(409,'项目已更新或正在处理，请结束后修改创作设置')
            same=p.get('skill_id','ad-video')==body.skill_id
            skill=p.get('skill') if same and body.skill_version is None else None
            if not skill: skill=find_skill(body.skill_id,uid,body.skill_version)
            if not same or p.get('skill',{}).get('version')!=skill['version']:
                archive_render(p)
                p.update(state='intake',shots=[],questions=[],error='')
                for k in ('run_id','artifact','qa','film'):p.pop(k,None)
            p.update(skill_id=skill['id'],skill_title=skill['title'],skill=skill,approval_mode=body.approval_mode)
            p.pop('scene_render_intent',None);p.pop('scene_render_review',None)
            p.pop('auto_approval',None)
            p['revision']+=1;save(p,uid);event(p,'task','creative_settings_changed')
            return present(p)

    @app.post('/creative/api/projects')
    async def create(body: Create, authorization: str|None=Header(None)):
        uid=owner(authorization)
        try: spec=model_spec(body.provider,body.model)
        except ValueError as exc: raise HTTPException(422,str(exc))
        if body.creation_mode=='video':
            if not spec.get('manual_available') or body.duration not in spec['manual_durations']:raise HTTPException(422,'所选模型不支持此手动生成时长')
        elif not spec.get('single_film') or body.duration!=15:raise HTTPException(422,'Agent 需要已接入的 15 秒有声视频模型')
        from harness.studio.templates import find_skill
        skill=find_skill(body.skill_id,uid,body.skill_version)
        p={'generation_mode':'single_native','id':secrets.token_hex(12),'state':'intake','revision':0,'messages':[{'role':'user','content':body.message}],
           'duration':body.duration,'provider':body.provider,'model':spec['id'],'aspect':body.aspect,'shots':[], 'questions':[],
           'assumptions':[],'decisions':[],'brief':{},'training_eligible':False,
           'skill_id':skill['id'],'skill_title':skill['title'],'skill':skill,'approval_mode':body.approval_mode}
        record_message_context(p)
        p['creation_mode']=body.creation_mode
        if body.creation_mode=='image':
            from harness.models.studio_image import image_models
            image_spec=next((m for m in image_models() if m['id']==(body.image_model or 'kling-image-v3_0')),None)
            if not image_spec or not image_spec['available']:raise HTTPException(422,'请选择已接入的图片模型')
            p.update(image_model=image_spec['id'],direct_prompt=body.message,brief={'product':'图片节点 1'})
        if body.creation_mode=='video':
            p['direct_prompt']=body.message
            p.update(state='ready',brief={'product':'视频节点 1'},shots=[{
                'id':'shot_1','start':0,'duration':body.duration,'title':'视频节点 1',
                'prompt':body.message,'audio_prompt':'按用户描述生成同步声音','caption':'','state':'planned','rationale':'用户直接描述'}])
        save(p,uid);event(p,'task','created')
        return present(p)

    @app.get('/creative/manual-nodes.js',include_in_schema=False)
    def manual_nodes_script():return FileResponse(ROOT/'tools/agent_studio/manual-nodes.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.post('/creative/api/projects/{pid}/manual-nodes')
    async def add_manual_node(pid:str,body:Create,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            parent=load(pid,uid)
            if body.creation_mode not in ('image','video'):
                raise HTTPException(422,'仅手动画布支持独立图片或视频节点')
            nodes=parent.setdefault('manual_nodes',[])
            if len(nodes)>=15:raise HTTPException(422,'每张画布最多支持16个生成节点')
            child=await create(body,authorization)
            stored=load(child['id'],uid);stored['manual_parent']=pid;save(stored,uid)
            nodes.append({'project':child['id'],'kind':body.creation_mode,'index':len(nodes)+2})
            save(parent,uid);event(parent,'tool','manual_node_added')
            return {'node':nodes[-1],'project':child}

    @app.post('/creative/api/projects/{pid}/director')
    async def workspace_director(pid: str, authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            parent=load(pid,uid)
            if parent.get('creation_mode')=='agent':return present(parent)
            if parent.get('director_project'):return present(load(parent['director_project'],uid))
            nodes=parent.setdefault('manual_nodes',[])
            if len(nodes)>=15:raise HTTPException(422,'当前画布节点已满')
            # A separate run preserves manual prompts, jobs and paid outputs.
            child=await create(Create(message='新的创作需求',creation_mode='agent',skill_id='story-short',
                                      model='kling-video-v4_0',aspect=parent['aspect']),authorization)
            stored=load(child['id'],uid);stored['manual_parent']=pid;save(stored,uid)
            nodes.append({'project':child['id'],'kind':'agent','index':len(nodes)+2})
            parent['director_project']=child['id'];save(parent,uid)
            try:sync_context(parent,stored)
            except ValueError as exc:raise HTTPException(422,str(exc))
            save(stored,uid)
            return present(stored)

    @app.get('/creative/api/projects/{pid}/director-context')
    def workspace_director_context(pid: str, authorization: str|None=Header(None)):
        uid=owner(authorization);child=load(pid,uid)
        parent=load(child['manual_parent'],uid) if child.get('manual_parent') else child
        if parent['id']!=child['id'] and parent.get('director_project')!=child['id']:
            raise HTTPException(404,'关联工作区不存在')
        graph=parent.get('canvas',{'nodes':[],'edges':[]})
        linked={e['source'] for e in graph.get('edges',[]) if e.get('target')=='director'}
        return {'project':parent['id'],'references':[
            {'id':n['id'],'kind':n['kind'],'label':n.get('label') or {'image':'图片参考','video':'视频参考','text':'文字参考'}.get(n['kind'],'参考')}
            for n in graph.get('nodes',[]) if n['id'] in linked]}

    @app.get('/creative/api/projects/{pid}/manual-nodes')
    async def manual_nodes(pid:str,authorization:str|None=Header(None)):
        uid=owner(authorization);parent=load(pid,uid)
        result=[]
        for node in parent.get('manual_nodes',[]):
            child=load(node['project'],uid)
            if child.get('manual_parent')==pid:result.append({'node':node,'project':present(child)})
        return {'nodes':result}

    @app.post('/creative/api/projects/{pid}/manual-nodes/{child_id}/result')
    async def import_manual_result(pid:str,child_id:str,authorization:str|None=Header(None)):
        from harness.tools.creative_workspace_result import import_result
        uid=owner(authorization)
        async with lock(pid):
            parent=load(pid,uid);child=load(child_id,uid)
            if pid in RUNNING or parent['state'] in ('running','rendering','planning') or parent.get('image_task',{}).get('state')=='running':
                raise HTTPException(409,'主节点正在生成，请完成后将结果加入编辑区')
            try:node,changed=import_result(parent,child)
            except ValueError as exc:raise HTTPException(422,str(exc))
            if changed:
                parent['revision']+=1
                save(parent,uid)
                event(parent,'tool','manual_result_imported')
            return {'project':present(parent),'node':node}

    @app.post('/creative/api/projects/{pid}/manual-nodes/{child_id}/reference')
    async def import_manual_reference(pid:str,child_id:str,body:ManualNodeReference,authorization:str|None=Header(None)):
        from harness.tools.creative_workspace_reference import import_reference
        uid=owner(authorization)
        if pid==child_id:raise HTTPException(422,'请选择另一个生成节点')
        async with lock(child_id):
            parent=load(pid,uid);child=load(child_id,uid)
            if child.get('creation_mode') not in ('image','video'):raise HTTPException(422,'请选择图片或视频生成节点')
            if child['revision']!=body.revision or child.get('image_task',{}).get('state') in ('running','needs_review') or child_id in RUNNING or child['state'] in ('running','rendering','planning') or (child.get('film') and child['film'].get('state') not in ('planned','completed','failed')):
                raise HTTPException(409,'节点已更新或任务未完成，请重新核对')
            try:changed=import_reference(parent,child,body.asset)
            except ValueError as exc:raise HTTPException(422,str(exc))
            if changed:
                child['revision']+=1;save(child,uid);event(child,'tool','workspace_reference_imported')
            return present(child)

    @app.patch('/creative/api/projects/{pid}/manual-nodes/{child_id}/position')
    async def move_manual_node(pid:str,child_id:str,body:ManualNodePosition,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            parent=load(pid,uid)
            if child_id==pid and parent.get('creation_mode') in ('image','video'):
                node=parent.setdefault('manual_position',{})
            else:
                node=next((n for n in parent.get('manual_nodes',[]) if n['project']==child_id),None)
                if not node or load(child_id,uid).get('manual_parent')!=pid:
                    raise HTTPException(404,'画布节点不存在')
            # Layout is independent of paid generation inputs and their revision.
            node.update(x=body.x,y=body.y)
            save(parent,uid)
            return {'node':node}

    @app.patch('/creative/api/projects/{pid}/manual-prompt')
    async def manual_prompt(pid: str,body: ManualPrompt,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p.get('creation_mode') not in ('image','video'):raise HTTPException(422,'仅手动创作项目可直接修改生成要求')
            if p['revision']!=body.revision or pid in RUNNING or p['state'] in ('running','rendering','planning'):raise HTTPException(409,'任务正在处理或项目已更新')
            if p['creation_mode']=='video':
                try:spec=model_spec('kling',body.model or p['model'])
                except ValueError as exc:raise HTTPException(422,str(exc))
                duration=body.duration or p['duration']
                if not spec.get('manual_available') or duration not in spec['manual_durations']:raise HTTPException(422,'所选模型不支持此时长')
                if p.get('video_inputs') and spec['id']!=p['model']:raise HTTPException(409,'更换模型前请重新确认参考图片')
            else:spec=None;duration=p['duration']
            if p.get('direct_prompt')==body.prompt and (not spec or spec['id']==p['model']) and duration==p['duration'] and not p.get('film'):return present(p)
            if p.get('film') and p['film'].get('state') not in ('planned','completed','failed'):
                raise HTTPException(409,'原任务仍在生成或待核对，请恢复查询原任务后再创建新生成')
            if p['creation_mode']=='video':
                archive_render(p)
                for name in ('film','run_id','artifact','qa','stop_requested'):p.pop(name,None)
                p.update(model=spec['id'],duration=duration)
                p.update(state='ready',shots=[{'id':'shot_1','start':0,'duration':p['duration'],'title':'视频节点 1','prompt':body.prompt,'audio_prompt':'按用户描述生成同步声音','caption':'','state':'planned','rationale':'用户直接描述'}])
            p['direct_prompt']=body.prompt;p['revision']+=1;save(p,uid);event(p,'task','manual_prompt_changed')
            return present(p)

    @app.get('/creative/api/projects/{pid}')
    async def project(pid: str,authorization: str|None=Header(None)):
        # RUNNING is owned by this event loop. Do not yield between the stored
        # snapshot and its runtime observation; worker completion must not make
        # an older snapshot look interrupted. Keep UI enrichment off the loop.
        snapshot = load(pid, owner(authorization))
        runtime_active = pid in RUNNING
        return await asyncio.to_thread(present, snapshot, runtime_active=runtime_active)

    @app.put('/creative/api/projects/{pid}/canvas')
    async def canvas(pid: str, body: CanvasEdit, authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=body.revision: raise HTTPException(409,'画布已更新，请刷新后再保存')
            if p['state'] in ('running','rendering','planning') or pid in RUNNING:
                raise HTTPException(409,'制作或规划中，请结束后再修改参考画布')
            try: graph=validate_graph(body.model_dump(),p.get('canvas_assets',{}))
            except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc)) from exc
            changed=input_signature(graph)!=input_signature(p.get('canvas',{}))
            if changed:
                archive_render(p)
                p['state']='intake';p['shots']=[];p['questions']=[];p['error']=''
                for key in ('run_id','artifact','qa','stop_requested','film'): p.pop(key,None)
            p['canvas']=graph;p['revision']+=1
            save(p,uid);event(p,'tool','canvas_inputs_changed' if changed else 'canvas_layout_saved')
            return present(p)

    @app.post('/creative/api/projects/{pid}/canvas/layout')
    async def canvas_layout(pid: str, body: CanvasLayout, authorization: str|None=Header(None)):
        from harness.tools.canvas_lineage import lineage, arrange
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=body.revision or pid in RUNNING or p['state'] in ('running','rendering','planning'):
                raise HTTPException(409,'项目已变化，请刷新后再排版')
            try:
                graph=validate_graph(body.model_dump(),p.get('canvas_assets',{}))
                graph=arrange(graph,lineage(p),body.sizes)
            except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
            return {'revision':p['revision'],'canvas':graph}

    @app.post('/creative/api/projects/{pid}/canvas/assets')
    async def canvas_upload(pid: str, kind: Literal['image','video'], revision: int, request: Request, authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=revision: raise HTTPException(409,'画布已更新，请刷新后再上传')
            if p['state'] in ('running','rendering','planning') or pid in RUNNING:
                raise HTTPException(409,'制作或规划中，暂不能上传参考')
            if len(p.get('canvas_assets',{}))>=32: raise HTTPException(422,'本项目最多保存 32 个参考文件')
            content=bytearray()
            async for part in request.stream():
                if len(content)+len(part)>MAX_CANVAS_UPLOAD: raise HTTPException(413,'参考文件不得超过 30 MB')
                content.extend(part)
            try: asset=await asyncio.to_thread(save_asset,p,bytes(content),kind,preserve_pixels=kind=='image')
            except ValueError as exc: raise HTTPException(422,str(exc)) from exc
            p.setdefault('canvas_assets',{})[asset['id']]=asset
            p['revision']+=1;save(p,uid);event(p,'tool','canvas_asset_uploaded')
            return {'project':present(p),'asset':asset}

    @app.post('/creative/api/projects/{pid}/canvas/assets/{aid}/preview-session')
    def canvas_preview_session(pid: str, aid: str, authorization: str|None=Header(None)):
        from harness.studio import media_access
        uid=owner(authorization)
        p=load(pid,uid);asset=p.get('canvas_assets',{}).get(aid)
        if not asset or asset.get('kind')!='video': raise HTTPException(404,'找不到视频文件')
        source=f'/creative/api/projects/{pid}/canvas/assets/{aid}/source'
        response=JSONResponse({'source':source},headers={'Cache-Control':'private, no-store'})
        response.set_cookie(media_access.COOKIE,media_access.issue(uid,pid,aid),max_age=media_access.TTL,
                            path=source,secure=True,httponly=True,samesite='strict')
        return response

    @app.get('/creative/api/projects/{pid}/canvas/assets/{aid}/{view}')
    def canvas_asset(pid: str, aid: str, view: Literal['preview','source','metadata'], request: Request, authorization: str|None=Header(None)):
        from harness.studio import media_access
        uid=owner(authorization) if authorization else (media_access.verify(request.cookies.get(media_access.COOKIE),pid,aid) if view=='source' else None)
        if not uid: raise HTTPException(401,'请重新打开视频预览')
        p=load(pid,uid);asset=p.get('canvas_assets',{}).get(aid)
        if not asset: raise HTTPException(404,'找不到参考文件')
        if view == 'metadata':
            try: return JSONResponse(asset_metadata(p, aid), headers={'Cache-Control': 'private, no-store'})
            except ValueError as exc: raise HTTPException(422, str(exc)) from exc
        path=asset_directory(p,aid)/('frame-0.jpg' if view=='preview' else asset['filename'])
        return FileResponse(path,media_type=('image/png' if path.suffix=='.png' else 'image/jpeg') if view=='preview' or asset['kind']=='image' else 'video/mp4',headers={'Cache-Control':'private, no-store'})

    @app.get('/creative/api/projects/{pid}/reference')
    def reference_image(pid: str,authorization: str|None=Header(None)):
        p=load(pid,owner(authorization))
        if not p.get('reference'): raise HTTPException(404,'尚未上传参考图')
        return FileResponse(reference_path(p),media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

    @app.post('/creative/api/projects/{pid}/reference')
    @app.delete('/creative/api/projects/{pid}/reference')
    async def change_reference(pid: str,revision: int,request: Request,source_asset: str|None=None,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=revision: raise HTTPException(409,'方案已更新，请刷新后操作')
            if p['state'] in ('running','rendering','planning') or pid in RUNNING: raise HTTPException(409,'制作中，不能更换参考图')
            ref=None
            if request.method=='POST':
                if source_asset:
                    asset=p.get('canvas_assets',{}).get(source_asset)
                    if not asset or asset['kind']!='image':raise HTTPException(422,'商品原图不属于本项目')
                    content=(asset_directory(p,source_asset)/asset['filename']).read_bytes()
                else:
                    content=bytearray()
                    async for chunk in request.stream():
                        if len(content)+len(chunk)>MAX_UPLOAD: raise HTTPException(413,'参考图需小于 6 MB')
                        content.extend(chunk)
                try: ref=await asyncio.to_thread(save_reference,p,bytes(content))
                except ValueError as exc: raise HTTPException(422,str(exc)) from exc
                if source_asset:ref['source_asset']=source_asset
            archive_render(p)
            p.pop('video_inputs',None);p.pop('video_inputs_product',None)
            p['reference']=ref
            p['reference_product']=p.get('brief',{}).get('product','')
            p['reference_needs_review']=False
            p['revision']+=1;p['state']='intake';p['shots']=[];p['questions']=[];p['error']=''
            p['messages'].append({'role':'user','content':'已更新画面参考图，请以图中商品外观和场景为依据重新规划。' if ref else '已移除参考图，请按纯文字需求重新规划。'})
            record_message_context(p)
            for k in ('run_id','artifact','qa','stop_requested','film'): p.pop(k,None)
            save(p,uid);event(p,'tool','reference_updated' if ref else 'reference_removed')
            return present(p)

    @app.post('/creative/api/projects/{pid}/reference/confirm')
    async def confirm_reference(pid: str,body: ReferenceConfirm,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['revision']!=body.revision or pid in RUNNING:raise HTTPException(409,'作品已更新，请重新核对')
            if not p.get('reference') or p['reference']['id']!=body.reference_id:raise HTTPException(409,'参考图已变化')
            p['reference_product']=p.get('brief',{}).get('product','')
            p['reference_needs_review']=False;p['revision']+=1
            save(p,uid);event(p,'tool','reference_confirmed')
            return present(p)

    @app.get('/creative/api/projects/{pid}/messages/{message_index}/references/{reference_index}')
    def message_reference(pid: str, message_index: int, reference_index: int, authorization: str|None=Header(None)):
        p = load(pid, owner(authorization))
        snapshot = p.get('message_contexts', {}).get(str(message_index), {})
        refs = snapshot.get('references', [])
        if message_index < 0 or not 0 <= reference_index < min(7, len(refs)):
            raise HTTPException(404, '此消息没有对应参考图')
        ref = refs[reference_index]
        if ref.get('reference_id'):
            try: path = reference_path({**p, 'reference': {'id': ref['reference_id']}})
            except ValueError: raise HTTPException(404, '历史参考暂不可读取')
        elif p.get('canvas_assets', {}).get(ref.get('asset'), {}).get('kind') == 'image':
            path = asset_directory(p, ref['asset']) / 'frame-0.jpg'
        else:
            raise HTTPException(404, '历史参考暂不可读取')
        if not path.is_file(): raise HTTPException(404, '历史参考暂不可读取')
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control':'private, no-store'})

    @app.post('/creative/api/projects/{pid}/message')
    async def message(pid: str,body: Message,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p.get('creation_mode') in ('image','video'):raise HTTPException(409,'这是手动创作项目，请在画布节点直接生成；Agent 创作请新建独立项目')
            if body.request_id and p.get('planning_request_id')==body.request_id: return present(p)
            if p['revision']!=body.revision: raise HTTPException(409,'方案已更新，请刷新后操作')
            if p['state'] in ('running','rendering') or pid in RUNNING: raise HTTPException(409,'制作中，请等待或停止后再修改')
            if p.get('generation_mode')!='single_native':
                raise HTTPException(409,'这是旧版分段项目；请在模型选择器选择 Kling 3.0 或 O3，转为 15 秒有声整片后重新规划。')
            if body.auto_approve_credits is not None:
                if p.get('approval_mode')!='auto' or body.mode!='plan' or not body.background:
                    raise HTTPException(422,'自动审批只能用于已开启自动模式的一次后台规划')
                required=model_spec(p['provider'],p.get('model'))['credits_per_5s']*3
                if body.auto_approve_credits<required:raise HTTPException(400,'授权预算不足以制作当前所选模型的整片')
            if p.get('manual_parent'):
                parent=load(p['manual_parent'],uid)
                try:sync_context(parent,p)
                except ValueError as exc:raise HTTPException(422,str(exc))
            if body.text.strip():
                p['messages'].append({'role':'user','content':body.text.strip()})
                record_message_context(p)
            if len(p['messages'])>40: raise HTTPException(400,'对话已满，请创建新项目')
            archive_render(p)
            event(p,'agent','planning_started')
            # Preserve new context even if the model call fails.
            p['revision']+=1;p['state']='planning';p['error']='';p['planning_request_id']=body.request_id;p['planning_phase']='queued';p['stop_requested']=False
            p.pop('auto_approval',None)
            if body.auto_approve_credits is not None:
                p['auto_approval']={'revision':p['revision'],'model':p['model'],'credits':body.auto_approve_credits,'state':'armed'}
            save(p,uid)
            from harness.core.creative_planner import plan
            if body.background:
                async def planned_work():
                    await plan(p,uid,body.mode,direct)
                    if body.auto_approve_credits is None:return
                    latest=load(pid,uid)
                    if latest['revision']!=p['revision'] or latest['state']!='ready':return
                    latest['auto_approval']={'revision':p['revision'],'credits':body.auto_approve_credits,
                                             'model':p['model'],'state':'consumed'}
                    if latest.get('stop_requested'):
                        latest['auto_approval']['state']='stopped';save(latest,uid);return
                    save(latest,uid)
                    try:
                        await execute(pid,Start(revision=p['revision'],approved_credits=body.auto_approve_credits),authorization)
                    except HTTPException as exc:
                        latest=load(pid,uid)
                        if latest['revision']==p['revision']:
                            latest['auto_approval']['state']='needs_review'
                            latest['error']=str(exc.detail);save(latest,uid)
                            event(latest,'runner','auto_approval_stopped')
                RUNNING[pid]=asyncio.create_task(planned_work())
                return present(p)
            await plan(p,uid,body.mode,direct)
            if p['state']=='planning_failed':
                raise HTTPException(502,p['error'])
            return present(p)

    @app.patch('/creative/api/projects/{pid}/timeline')
    async def edit(pid: str,body: Edit,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if pid in RUNNING or p['state'] not in ('ready','completed') or p['revision']!=body.revision: raise HTTPException(409,'当前方案不可编辑，请先修改需求生成新一版')
            if len(body.shots)!=p['duration']//5 or sorted(s.get('id','') for s in body.shots)!=sorted(s['id'] for s in p['shots']): raise HTTPException(400,'镜头列表不合法')
            old={s['id']:s for s in p['shots']}
            if p.get('generation_mode')=='single_native' and p.get('film',{}).get('job_id') and [s['id'] for s in body.shots]!=[s['id'] for s in p['shots']]:
                raise HTTPException(409,'整片已生成，不能重排源画面；请通过导演创建新版本。')
            updated=[]
            for i,s in enumerate(body.shots):
                if not isinstance(s.get('prompt'),str) or not 1<=len(s['prompt'].strip())<=4000: raise HTTPException(400,'画面说明不能为空且不超过4000字')
                if not isinstance(s.get('caption'),str) or len(s['caption'])>60: raise HTTPException(400,'字幕不超过60字')
                if old[s['id']]['state']=='completed' and s['prompt']!=old[s['id']]['prompt']:
                    raise HTTPException(409,'已有镜头的画面描述不可直接修改。请在导演对话中生成新方案并确认生成预算。')
                audio=s.get('audio_prompt',old[s['id']].get('audio_prompt',''))
                if p.get('generation_mode')=='single_native':
                    if not isinstance(audio,str) or not 1<=len(audio.strip())<=1500:raise HTTPException(400,'请填写分镜声音设计，不超过1500字')
                    if p.get('film',{}).get('job_id') and (audio!=old[s['id']].get('audio_prompt','') or s['prompt']!=old[s['id']]['prompt']):raise HTTPException(409,'已有整片的画面和声音不能直接修改，请创建新方案并确认预算。')
                updated.append({**old[s['id']],'audio_prompt':audio,'prompt':s['prompt'],'caption':s['caption'],'start':i*5})
            archive_render(p)
            p.pop('artifact',None);p.pop('qa',None)
            p['state']='ready';p['shots']=updated;p['revision']+=1;save(p,uid);event(p,'task','timeline_edited')
            return present(p)

    @app.post('/creative/api/projects/{pid}/review')
    async def review(pid: str, body: Review, authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if p['state']!='completed' or not p.get('artifact') or p['revision']!=body.revision:
                raise HTTPException(409,'请审阅当前已完成的版本，方案更新后需要重新确认')
            if body.decision=='changes_requested' and not body.note.strip():
                raise HTTPException(400,'请填写需要修改的内容')
            from harness.learning.governance import current_artifact
            try:artifact_digest=await asyncio.to_thread(current_artifact,p)
            except ValueError:raise HTTPException(409,'成片文件不可读取，请恢复成片后重新审阅')
            record={'revision':p['revision'],'artifact':p['artifact'],'artifact_sha256':artifact_digest,'decision':body.decision,
                    'note':body.note.strip(),'created_at':time.time()}
            p.setdefault('reviews',[]).append(record)
            p.setdefault('qa',{})['human']=body.decision
            # An account owner review does not replace independent semantic review.
            p['training_eligible']=False;p['qa']['training_eligible']=False
            save(p,uid);event(p,'reviewer','human_approved' if body.decision=='approved' else 'changes_requested')
            return present(p)

    @app.get('/creative/api/projects/{pid}/budget')
    def production_budget(pid: str, authorization: str|None=Header(None)):
        account = dict(gateway.require_session(authorization))
        p = load(pid, account['id'])
        required = project_quote(p)['credits']
        remaining = None if account.get('quota', -1) < 0 else max(0, account['quota'] - account.get('used', 0))
        return {'revision': p['revision'], 'required_credits': required,
                'remaining_credits': remaining, 'sufficient': remaining is None or remaining >= required}

    @app.post('/creative/api/projects/{pid}/execute')
    async def execute(pid: str,body: Start,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid)
            if pid in RUNNING: return present(p)
            if p['revision']!=body.revision: raise HTTPException(409,'方案已更新，请重新确认')
            if p['state'] not in ('ready','paused','running','rendering'): raise HTTPException(409,'请先完成创作方案')
            if any(s['state']=='failed' for s in p['shots']): raise HTTPException(409,'失败镜头需明确创建新一版')
            if p.get('generation_mode')!='single_native':raise HTTPException(409,'旧版分段制作已停用；请切换模型并重新规划为15秒有声整片。')
            from harness.tools.creative_video import film_prompt
            try: film_prompt(p)
            except RuntimeError as exc:raise HTTPException(422,str(exc))
            if not p.get('film',{}).get('job_id') and p.get('video_inputs'):
                from harness.tools.creative_video_inputs import validate
                try:validate(p)
                except (ValueError,OSError) as exc:raise HTTPException(409,'视频参考已变化，请重新核对输入') from exc
                if p['video_inputs']['references'] and p.get('video_inputs_product')!=p.get('brief',{}).get('product',''):
                    raise HTTPException(409,'商品已变化，请在视频参考窗口重新确认图片归属')
            if not p.get('video_inputs') and p.get('reference') and (p.get('reference_needs_review') or p.get('reference_product')!=p.get('brief',{}).get('product','')):
                raise HTTPException(409,'请先核对商品参考图是否属于当前商品，或移除旧图后重新规划')
            required=project_quote(p)['credits']
            if not p['shots'] or body.approved_credits<required: raise HTTPException(400,'请确认当前版本所需的生成积分')
            account=dict(gateway.require_session(authorization))
            if account.get('quota',-1)>=0 and account['quota']-account.get('used',0)<required:
                raise HTTPException(402,'当前积分不足以完成本版全部新镜头，请先补充积分或调整方案；尚未提交生成。')
            if not p.get('run_id'): p['run_id']=secrets.token_hex(12)
            p['state']='running';p['stop_requested']=False;p['error']='';save(p,uid);event(p,'runner','execution_approved')
            RUNNING[pid]=asyncio.create_task(production(app,p,uid,authorization))
            return present(p)

    @app.post('/creative/api/projects/{pid}/stop')
    async def stop(pid: str,authorization: str|None=Header(None)):
        uid=owner(authorization)
        async with lock(pid):
            p=load(pid,uid);p['stop_requested']=True;save(p,uid);event(p,'runner','stop_requested')
            return present(p)

    @app.get('/creative/api/projects/{pid}/media/{asset}')
    def media(pid: str,asset: str,authorization: str|None=Header(None)):
        p=load(pid,owner(authorization))
        version=next((v for v in p.get('versions',[]) if asset=='version_'+v['id']),None)
        if version: path=DATA/version['artifact']
        elif asset=='final' and p.get('artifact'): path=DATA/p['artifact']
        elif asset=='film' and p.get('film',{}).get('state')=='completed': path=DATA/'artifacts'/p['run_id']/'film.mp4'
        elif any(s['id']==asset and s['state']=='completed' for s in p['shots']): path=DATA/'artifacts'/p['run_id']/('film.mp4' if p.get('generation_mode')=='single_native' else asset+'.mp4')
        else: raise HTTPException(404,'视频尚未就绪')
        if not path.is_file(): raise HTTPException(404,'视频文件暂不可用')
        return FileResponse(path,media_type='video/mp4',filename=asset+'.mp4')
