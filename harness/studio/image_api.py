"""Durable single-submit image jobs, explicit credit approval and owned assets."""
import asyncio
import secrets
import time
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from fastapi.responses import FileResponse
from harness.models.studio_image import image_models
from harness.tools.creative_image import create_image
from harness.studio import store
from harness.tools.creative_image_inputs import prepare_inputs, content_hash
from harness.tools.creative_canvas import asset_directory
from harness.evaluators.image_transform import observe_transform


class ImageReference(BaseModel):
    model_config={'extra':'forbid'}
    asset: str = Field(pattern=r'^[a-f0-9]{32}$')
    role: Literal['product','person','scene','style','reference']='reference'
    instruction: str = Field(default='',max_length=240)


class ImageDraft(BaseModel):
    model_config={'extra':'forbid'}
    revision: int
    model: str = Field(max_length=100)
    prompt: str = Field(default='',max_length=4000)
    references: list[ImageReference] = Field(default_factory=list,max_length=3)


class ImageAdjustments(BaseModel):
    model_config={'extra':'forbid'}
    angle: Literal['保留原角度','正面平视','侧面 45 度','俯视特写','低机位仰视'] = '保留原角度'
    light: Literal['保留原光照','窗边柔光','暖色侧光','冷色轮廓光','影棚柔光'] = '保留原光照'


class BrushStroke(BaseModel):
    model_config={'extra':'forbid','allow_inf_nan':False}
    points: list[tuple[float,float]] = Field(min_length=1,max_length=256)
    size: float = Field(ge=.005,le=.3)
    erase: bool = False


class ImageRegion(BaseModel):
    model_config={'extra':'forbid','allow_inf_nan':False}
    x: float = Field(ge=0,lt=1)
    y: float = Field(ge=0,lt=1)
    width: float = Field(gt=0,le=1)
    height: float = Field(gt=0,le=1)
    feather: int = Field(default=8,ge=0,le=32)
    shape: Literal['rectangle','brush'] = 'rectangle'
    strokes: list[BrushStroke] = Field(default_factory=list,max_length=32)


class ImagePreview(BaseModel):
    model_config={'extra':'forbid'}
    revision: int
    model: str
    prompt: str = Field(min_length=2,max_length=4000)
    source_asset: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    references: list[ImageReference] = Field(default_factory=list,max_length=3)
    connect_to_director: bool = True
    director_reference: bool = False
    director_context: str = Field(default='',max_length=5000)
    director_video_credits: int | None = Field(default=None,ge=1,le=10000,strict=True)
    adjustments: ImageAdjustments = Field(default_factory=ImageAdjustments)
    region: ImageRegion | None = None
    control_parameters: dict | None = None
    transform_draft_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class ImageStart(ImagePreview):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    approved_credits: int = Field(ge=1,le=1)
    input_hash: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')


class DirectorReferences(BaseModel):
    model_config={'extra':'forbid'}
    revision: int
    references: list[ImageReference] = Field(min_length=1,max_length=6)


def install(gateway, execute_video=None):
    @gateway.app.post('/creative/api/projects/{pid}/director-references')
    async def attach_references(pid:str,body:DirectorReferences,authorization:str|None=Header(None)):
        from harness.tools.director_references import attach
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid)
            if p['revision']!=body.revision or pid in store.RUNNING or p['state'] in ('running','rendering','planning'):
                raise HTTPException(409,'项目已更新或正在处理，请重新核对参考图')
            try:attach(p,[r.model_dump() for r in body.references])
            except (ValueError,OSError) as exc:
                raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else '参考图片暂不可读取') from exc
            store.archive_render(p)
            p.update(state='intake',shots=[],error='')
            for name in ('run_id','artifact','qa','film','campaign','auto_approval'):p.pop(name,None)
            p['revision']+=1;store.save(p,uid);store.event(p,'tool','director_reference_bound')
            return store.present(p)

    @gateway.app.get('/creative/image-composer.js',include_in_schema=False)
    def composer_script():return FileResponse(store.ROOT/'tools/agent_studio/image-composer.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @gateway.app.get('/creative/image-adjustments.js',include_in_schema=False)
    def adjustments_script():return FileResponse(store.ROOT/'tools/agent_studio/image-adjustments.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    def prepared(p,body):
        if p['revision']!=body.revision or p['id'] in store.RUNNING or p['state'] in ('running','rendering','planning'):
            raise HTTPException(409,'项目已更新或正在处理，请重新核对生成输入')
        if p.get('creation_mode') in ('image','video') and body.connect_to_director:
            raise HTTPException(422,'手动创作结果保留在画布，不会自动转入 Agent')
        if body.director_reference:
            from harness.tools.director_references import check_available
            if not body.connect_to_director:raise HTTPException(422,'Agent 参考生成必须交给导演')
            try:check_available(p)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            if len(p.get('messages',[]))>36:raise HTTPException(422,'对话已满，请新建项目')
            expected=[{k:r[k] for k in ('asset','role','instruction')} for r in p.get('video_inputs',{}).get('references',[])]
            if body.source_asset or [r.model_dump() for r in body.references]!=expected:
                raise HTTPException(409,'Agent 生图须使用当前已绑定参考，请刷新输入；不会忽略商品图片')
        elif body.director_context:raise HTTPException(422,'补充回答只用于 Agent 参考生成')
        if body.director_video_credits is not None:
            from harness.models.video_catalog import model_spec
            if not body.director_reference or p.get('approval_mode')!='auto' or execute_video is None:
                raise HTTPException(422,'参考图与成片连续制作需要 Agent 自动审批模式')
            if p.get('generation_mode') not in ('single_native','chaptered_native'):
                raise HTTPException(422,'当前制作模式不支持连续制作')
            required=model_spec(p['provider'],p['model'])['credits_per_5s']*(p['duration']//5)
            if body.director_video_credits!=required:
                raise HTTPException(409,'视频预算已变化，请重新确认参考图与成片总费用')
        spec=next((m for m in image_models() if m['id']==body.model),None)
        if not spec or not spec['available']:raise HTTPException(422,'该图片模型当前不可用')
        try:result=prepare_inputs(p,spec,body.prompt,[v.model_dump() for v in body.references],body.source_asset,body.connect_to_director,body.adjustments.model_dump(),body.region.model_dump() if body.region else None,body.control_parameters)
        except (ValueError,OSError) as exc:raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else '参考图片暂不可读取') from exc
        if body.transform_draft_id:
            if body.control_parameters is not None:raise HTTPException(422,'不能同时提交控制面板参数和旧变换草稿')
            draft=p.get('image_transform_drafts',{}).get(body.transform_draft_id)
            if not isinstance(draft,dict) or draft.get('state')!='applied' or not draft.get('reversible'):
                raise HTTPException(409,'图片变换草稿已失效，请重新保存后再生成')
            if body.source_asset!=draft.get('asset') or draft.get('revision_after')!=p['revision']:
                raise HTTPException(409,'图片变换草稿已过期，请重新预览并保存后再生成')
            expected={'angle':draft.get('angle'),'light':draft.get('light')}
            if result['adjustments']!=expected:
                raise HTTPException(409,'生成参数与图片变换草稿不一致，请重新核对')
            result['transform_draft_id']=body.transform_draft_id
        graph=p.get('canvas',{})
        if len(graph.get('nodes',[]))>=16 or len(p.get('canvas_assets',{}))>=32:
            raise HTTPException(422,'参考素材已满，请整理画布后再生成')
        connected={e['source'] for e in graph.get('edges',[])}
        if body.connect_to_director and sum(n['id'] in connected and n['kind']!='text' for n in graph.get('nodes',[]))>=6:
            raise HTTPException(422,'导演最多接收6个图片或视频参考，可取消生成后交给导演')
        return result

    @gateway.app.put('/creative/api/projects/{pid}/images/draft')
    async def save_image_draft(pid:str,body:ImageDraft,authorization:str|None=Header(None)):
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid)
            if p.get('creation_mode')!='image':raise HTTPException(422,'请从图片节点保存参考')
            if p['revision']!=body.revision or pid in store.RUNNING or p['state'] in ('running','rendering','planning') or p.get('image_task',{}).get('state') in ('running','needs_review'):
                raise HTTPException(409,'项目已更新或任务未结束，请重新打开参考设置')
            if body.model not in {m['id'] for m in image_models()}:raise HTTPException(422,'未知图片模型')
            refs=[r.model_dump() for r in body.references]
            if len({r['asset'] for r in refs})!=len(refs):raise HTTPException(422,'参考图片不能重复')
            assets=p.get('canvas_assets',{})
            if any(assets.get(r['asset'],{}).get('kind')!='image' for r in refs):raise HTTPException(422,'参考图片不属于当前项目')
            draft={'model':body.model,'prompt':body.prompt,'references':refs}
            if p.get('image_draft')!=draft:
                p['image_draft']=draft;p['revision']+=1;p['updated_at']=time.time();store.save(p,uid)
            return store.present(p)

    @gateway.app.post('/creative/api/projects/{pid}/images/preview')
    async def preview(pid:str,body:ImagePreview,authorization:str|None=Header(None)):
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid);result=dict(prepared(p,body),credits=1)
            if body.director_video_credits is not None:
                result.update(video_credits=body.director_video_credits,total_credits=1+body.director_video_credits)
            return result

    def ledger(c):
        c.execute('CREATE TABLE IF NOT EXISTS creative_image_requests(owner INTEGER, project TEXT, request TEXT, state TEXT, credits INTEGER, PRIMARY KEY(owner,project,request))')

    async def run(pid,uid,task,authorization):
        completed=False
        try:
            p=store.load(pid,uid)
            with gateway.db() as c:
                ledger(c)
                claimed=c.execute("UPDATE creative_image_requests SET state='dispatched' WHERE owner=? AND project=? AND request=? AND state='reserved'",(uid,pid,task['id']))
                if claimed.rowcount!=1:raise RuntimeError('Image request already claimed')
            loop=asyncio.get_running_loop()
            async def update_progress(observation):
                async with store.lock(pid):
                    current=store.load(pid,uid)
                    if current.get('image_task',{}).get('id')==task['id'] and current['image_task'].get('state')=='running':
                        current['image_task']['progress']={**observation,'updated_at':time.time()}
                        store.save(current,uid)
            def generate_observed():
                from harness.models.generation_progress import observing
                def observe(value):asyncio.run_coroutine_threadsafe(update_progress(value),loop).result(timeout=20)
                with observing(observe):return create_image(p,task)
            asset=await asyncio.to_thread(generate_observed)
            async with store.lock(pid):
                p=store.load(pid,uid);p.setdefault('canvas_assets',{})[asset['id']]=asset
                graph=p.setdefault('canvas',{'nodes':[],'edges':[]});node_id='n'+secrets.token_hex(16)
                from harness.tools.creative_canvas import next_position
                from harness.tools.canvas_lineage import auto_place_generated_node, lineage
                parents=asset.get('provenance',{}).get('sources',[])
                parent_nodes=[n for n in graph['nodes'] if n.get('asset') in parents]
                source=max(parent_nodes,key=lambda n:n['x'])['asset'] if parent_nodes else task.get('source_asset') or task.get('reference_asset')
                role='reference' if len(parents)>1 else next((n.get('role','reference') for n in graph['nodes'] if n.get('asset')==source),'reference')
                graph['nodes'].append({'id':node_id,'kind':'image','asset':asset['id'],
                                      'label':'局部修改结果' if task.get('prepared',{}).get('region') else '多参考合成图' if len(parents)>1 else '图像变体' if source else '生成的参考图',
                                      'text':'','role':role,**next_position(graph,source)})
                graph = auto_place_generated_node(graph, lineage(p), node_id)
                p['canvas'] = graph
                p['canvas_auto_layout'] = {
                    'mode': 'generated-result',
                    'node_id': node_id,
                    'asset': asset['id'],
                    'x': next(n['x'] for n in graph['nodes'] if n['id'] == node_id),
                    'y': next(n['y'] for n in graph['nodes'] if n['id'] == node_id),
                    'revision': p['revision'] + 1,
                }
                if task.get('connect_to_director',True):
                    graph['edges'].append({'source':node_id,'target':'director'})
                    store.archive_render(p);p.update(state='intake',shots=[],questions=[],error='')
                    for key in ('run_id','artifact','qa','film'):p.pop(key,None)
                    if not task.get('video_approval'):p.pop('stop_requested',None)
                draft_id=task.get('transform_draft_id')
                if draft_id:
                    draft=p.get('image_transform_drafts',{}).get(draft_id)
                    if isinstance(draft,dict) and draft.get('state')=='applied':
                        source_id=task.get('source_asset')
                        source=p.get('canvas_assets',{}).get(source_id) if source_id else None
                        if source:
                            source_path=asset_directory(p,source_id)/source['filename']
                            result_path=asset_directory(p,asset['id'])/asset['filename']
                            observation=observe_transform(source_path,result_path)
                            asset.setdefault('provenance',{})['transform_alignment']=observation
                            draft['result_observation']=observation
                        draft.update(result_asset=asset['id'],result_revision=p['revision']+1,result_state='available')
                p['image_task'].update(state='completed',asset=asset['id']);p['image_attempts'][-1]=dict(p['image_task']);p['revision']+=1
                store.save(p,uid);store.event(p,'tool','image_completed')
                with gateway.db() as c:
                    c.execute("UPDATE creative_image_requests SET state='completed' WHERE owner=? AND project=? AND request=?",(uid,pid,task['id']))
                completed=True
            if task.get('director_reference'):
                from harness.tools.director_references import attach
                from harness.core.creative_planner import plan
                from harness.studio.api import direct
                async with store.lock(pid):
                    p=store.load(pid,uid)
                    attach(p,[dict(asset=asset['id'],role='style',instruction='Agent 生成的概念视觉参考；不代表真实产品界面或品牌标识')])
                    p['messages'].append({'role':'assistant','content':'概念参考图已生成并绑定到视频输入。沿用已有回答继续规划；此图仅作视觉方向，不是真实应用截图或品牌标识。'})
                    p.update(state='planning',planning_phase='queued',error='')
                    if not task.get('video_approval'):p.pop('auto_approval',None)
                    p['revision']+=1;store.save(p,uid);store.event(p,'tool','director_reference_bound')
                await plan(p,uid,'plan' if task.get('video_approval') else 'interview',direct)
                if task.get('video_approval'):
                    latest=store.load(pid,uid);approval=task['video_approval']
                    if latest.get('stop_requested'):
                        latest['auto_approval']['state']='stopped';store.save(latest,uid);return
                    if (latest['state']!='ready' or latest['revision']!=p['revision']
                            or latest['model']!=approval['model'] or latest['duration']!=approval['duration']
                            or latest['aspect']!=approval['aspect']
                            or latest.get('image_task',{}).get('id')!=task['id']):
                        latest['auto_approval']['state']='needs_review';store.save(latest,uid);return
                    latest['auto_approval'].update(state='consumed',revision=latest['revision']);store.save(latest,uid)
                    # Hand over to the same versioned, owned execution gate used
                    # by the video button. No credentials are saved in the task.
                    if store.RUNNING.get(pid) is asyncio.current_task():store.RUNNING.pop(pid,None)
                    try:await execute_video(pid,latest['revision'],approval['credits'],authorization)
                    except HTTPException as exc:
                        latest=store.load(pid,uid)
                        latest['auto_approval']['state']='needs_review'
                        latest['error']='参考图已保存，自动制作已停止：'+str(exc.detail)
                        store.save(latest,uid);store.event(latest,'runner','auto_approval_stopped')
        except Exception:
            async with store.lock(pid):
                p=store.load(pid,uid);task=p.get('image_task') or {};draft_id=task.get('transform_draft_id');draft=p.get('image_transform_drafts',{}).get(draft_id) if draft_id else None
                if task.get('video_approval') and p.get('auto_approval',{}).get('state') in ('armed','consumed'):
                    p['auto_approval']['state']='needs_review'
                if completed:
                    p['error']=('参考图已保存，后续制作中断，请核对已有视频任务；不会自动重新提交。' if task.get('video_approval') else
                                '图片已生成并保存在画布，参考绑定或继续规划未完成。请核对视频参考输入后继续；不会再次生图。')
                    store.save(p,uid);store.event(p,'agent','director_reference_needs_review')
                    return
                if isinstance(draft,dict) and draft.get('state')=='applied':draft.update(result_state='needs_review')
                p['image_task'].update(state='needs_review',error='图片尚未完成或结果待核对；可能已消耗额度，不会自动重试。')
                p['image_attempts'][-1]=dict(p['image_task']);store.save(p,uid);store.event(p,'tool','image_needs_review')
                with gateway.db() as c:
                    c.execute("UPDATE creative_image_requests SET state='needs_review' WHERE owner=? AND project=? AND request=? AND state='dispatched'",(uid,pid,task['id']))
        finally:
            if store.RUNNING.get(pid) is asyncio.current_task():store.RUNNING.pop(pid,None)

    @gateway.app.post('/creative/api/projects/{pid}/images')
    async def start(pid: str,body: ImageStart,authorization: str|None=Header(None)):
        account=gateway.require_session(authorization);uid=account['id']
        async with store.lock(pid):
            p=store.load(pid,uid)
            request_body=body.model_dump(exclude={'request_id','approved_credits'})
            # Keep fingerprints compatible with requests created before these
            # optional handoff fields existed.
            if not body.director_reference:request_body.pop('director_reference',None)
            if not body.director_context:request_body.pop('director_context',None)
            if body.director_video_credits is None:request_body.pop('director_video_credits',None)
            if body.control_parameters is None:request_body.pop('control_parameters',None)
            if body.region is None:request_body.pop('region',None)
            elif body.region.shape=='rectangle' and not body.region.strokes:
                request_body['region'].pop('shape',None);request_body['region'].pop('strokes',None)
            fingerprint=content_hash(request_body)
            existing=next((t for t in p.get('image_attempts',[]) if t['id']==body.request_id),None)
            if existing:
                if existing.get('request_hash') and existing['request_hash']!=fingerprint:
                    raise HTTPException(409,'同一生成请求的参数已改变，请核对原任务；不会再次提交')
                if not existing.get('request_hash') and (existing['model']!=body.model or existing['prompt']!=body.prompt or existing.get('source_asset')!=body.source_asset or body.references):
                    raise HTTPException(409,'旧生成请求参数不一致，请核对原任务')
                return store.present(p)
            inputs=prepared(p,body)
            if (body.references or body.region or body.control_parameters or body.input_hash) and body.input_hash!=inputs['input_hash']:
                raise HTTPException(409,'输入与确认版本不一致，请重新预览参考图片和提示词')
            task={'id':body.request_id,'model':body.model,'prompt':inputs['prompt'],'prepared':inputs,
                  'adjustments':inputs['adjustments'],
                  'request_hash':fingerprint,'connect_to_director':body.connect_to_director,'state':'running','credits':1,'started_at':time.time(),'progress':{'phase':'queued','updated_at':time.time()}}
            if body.director_reference:task.update(director_reference=True,director_context=body.director_context)
            if body.director_video_credits is not None:
                task['video_approval']=dict(model=p['model'],duration=p['duration'],aspect=p['aspect'],credits=body.director_video_credits)
                p['auto_approval']=dict(task['video_approval'],state='armed',revision=p['revision']+1)
                p['stop_requested']=False
            if body.transform_draft_id:task['transform_draft_id']=body.transform_draft_id
            if body.source_asset:task['source_asset']=body.source_asset
            elif inputs['references'] and inputs['references'][0].get('reference_id'):
                task['reference_id']=p['reference']['id']
                if p['reference'].get('source_asset'):task['reference_asset']=p['reference']['source_asset']
            p.setdefault('image_attempts',[]).append(dict(task));p['image_task']=task;p['revision']+=1;p['updated_at']=time.time()
            if body.director_reference and body.director_context:
                p['messages'].append({'role':'user','content':body.director_context})
            # Reservation and debit share ONE database; project persistence is separate.
            # A durable unique request prevents charging again even if the project write fails.
            with gateway.db() as c:
                ledger(c)
                existing=c.execute('SELECT state FROM creative_image_requests WHERE owner=? AND project=? AND request=?',(uid,pid,body.request_id)).fetchone()
                if existing:raise HTTPException(409,'该图片请求已有记录，请核对任务结果，不会重复扣费或提交')
                if body.director_video_credits is not None:
                    balance=c.execute('SELECT quota,used FROM users WHERE id=? AND verified=1',(uid,)).fetchone()
                    if not balance or (balance[0]>=0 and balance[0]-balance[1]<1+body.director_video_credits):
                        raise HTTPException(402,'积分不足以完成参考图与成片，尚未提交生成')
                c.execute("INSERT INTO creative_image_requests VALUES(?,?,?,'reserved',1)",(uid,pid,body.request_id))
                changed=c.execute('UPDATE users SET used=used+1 WHERE id=? AND verified=1 AND (quota<0 OR used+1<=quota)',(uid,))
                if changed.rowcount!=1:raise HTTPException(402,'图片生成需要1个平台积分，当前余额不足')
            try:
                store.save(p,uid);store.event(p,'tool','image_requested')
                if task.get('video_approval'):store.event(p,'runner','reference_film_approved')
            except Exception:
                # No worker was scheduled: this is a known unsubmitted request, safe to release.
                with gateway.db() as c:
                    released=c.execute("UPDATE creative_image_requests SET state='not_submitted',credits=0 WHERE owner=? AND project=? AND request=? AND state='reserved'",(uid,pid,body.request_id))
                    if released.rowcount:c.execute('UPDATE users SET used=used-1 WHERE id=?',(uid,))
                raise HTTPException(503,'图片请求未提交，已释放预留积分，请稍后重新操作') from None
            store.RUNNING[pid]=asyncio.create_task(run(pid,uid,task,authorization))
            return store.present(p)
