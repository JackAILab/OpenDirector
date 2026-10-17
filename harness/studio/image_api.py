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
    adjustments: ImageAdjustments = Field(default_factory=ImageAdjustments)
    region: ImageRegion | None = None
    control_parameters: dict | None = None
    transform_draft_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class ImageStart(ImagePreview):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    approved_credits: int = Field(ge=1,le=1)
    input_hash: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')


def install(gateway):
    @gateway.app.get('/creative/image-composer.js',include_in_schema=False)
    def composer_script():return FileResponse(store.ROOT/'tools/agent_studio/image-composer.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @gateway.app.get('/creative/image-adjustments.js',include_in_schema=False)
    def adjustments_script():return FileResponse(store.ROOT/'tools/agent_studio/image-adjustments.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    def prepared(p,body):
        if p['revision']!=body.revision or p['id'] in store.RUNNING or p['state'] in ('running','rendering','planning'):
            raise HTTPException(409,'项目已更新或正在处理，请重新核对生成输入')
        if p.get('creation_mode') in ('image','video') and body.connect_to_director:
            raise HTTPException(422,'手动创作结果保留在画布，不会自动转入 Agent')
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

    @gateway.app.post('/creative/api/projects/{pid}/images/preview')
    async def preview(pid:str,body:ImagePreview,authorization:str|None=Header(None)):
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid);return dict(prepared(p,body),credits=1)

    def ledger(c):
        c.execute('CREATE TABLE IF NOT EXISTS creative_image_requests(owner INTEGER, project TEXT, request TEXT, state TEXT, credits INTEGER, PRIMARY KEY(owner,project,request))')

    async def run(pid,uid,task):
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
                    for key in ('run_id','artifact','qa','stop_requested','film'):p.pop(key,None)
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
        except Exception:
            async with store.lock(pid):
                p=store.load(pid,uid);task=p.get('image_task') or {};draft_id=task.get('transform_draft_id');draft=p.get('image_transform_drafts',{}).get(draft_id) if draft_id else None
                if isinstance(draft,dict) and draft.get('state')=='applied':draft.update(result_state='needs_review')
                p['image_task'].update(state='needs_review',error='图片尚未完成或结果待核对；可能已消耗额度，不会自动重试。')
                p['image_attempts'][-1]=dict(p['image_task']);store.save(p,uid);store.event(p,'tool','image_needs_review')
                with gateway.db() as c:
                    c.execute("UPDATE creative_image_requests SET state='needs_review' WHERE owner=? AND project=? AND request=? AND state='dispatched'",(uid,pid,task['id']))
        finally:store.RUNNING.pop(pid,None)

    @gateway.app.post('/creative/api/projects/{pid}/images')
    async def start(pid: str,body: ImageStart,authorization: str|None=Header(None)):
        account=gateway.require_session(authorization);uid=account['id']
        async with store.lock(pid):
            p=store.load(pid,uid)
            request_body=body.model_dump(exclude={'request_id','approved_credits'})
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
            if body.transform_draft_id:task['transform_draft_id']=body.transform_draft_id
            if body.source_asset:task['source_asset']=body.source_asset
            elif inputs['references'] and inputs['references'][0].get('reference_id'):
                task['reference_id']=p['reference']['id']
                if p['reference'].get('source_asset'):task['reference_asset']=p['reference']['source_asset']
            p.setdefault('image_attempts',[]).append(dict(task));p['image_task']=task;p['revision']+=1;p['updated_at']=time.time()
            # Reservation and debit share ONE database; project persistence is separate.
            # A durable unique request prevents charging again even if the project write fails.
            with gateway.db() as c:
                ledger(c)
                existing=c.execute('SELECT state FROM creative_image_requests WHERE owner=? AND project=? AND request=?',(uid,pid,body.request_id)).fetchone()
                if existing:raise HTTPException(409,'该图片请求已有记录，请核对任务结果，不会重复扣费或提交')
                c.execute("INSERT INTO creative_image_requests VALUES(?,?,?,'reserved',1)",(uid,pid,body.request_id))
                changed=c.execute('UPDATE users SET used=used+1 WHERE id=? AND verified=1 AND (quota<0 OR used+1<=quota)',(uid,))
                if changed.rowcount!=1:raise HTTPException(402,'图片生成需要1个平台积分，当前余额不足')
            try:
                store.save(p,uid);store.event(p,'tool','image_requested')
            except Exception:
                # No worker was scheduled: this is a known unsubmitted request, safe to release.
                with gateway.db() as c:
                    released=c.execute("UPDATE creative_image_requests SET state='not_submitted',credits=0 WHERE owner=? AND project=? AND request=? AND state='reserved'",(uid,pid,body.request_id))
                    if released.rowcount:c.execute('UPDATE users SET used=used-1 WHERE id=?',(uid,))
                raise HTTPException(503,'图片请求未提交，已释放预留积分，请稍后重新操作') from None
            store.RUNNING[pid]=asyncio.create_task(run(pid,uid,task))
            return store.present(p)
