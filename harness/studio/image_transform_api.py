"""Owner-scoped, no-cost image transform previews and reversible drafts."""
import secrets
import time
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from harness.studio import store
from harness.tools.creative_image_inputs import content_hash


class ImageTransformPreview(BaseModel):
    model_config={'extra':'forbid'}
    revision: int
    asset: str = Field(pattern=r'^[a-f0-9]{32}$')
    angle: Literal['保留原角度','正面平视','侧面 45 度','俯视特写','低机位仰视'] = '保留原角度'
    light: Literal['保留原光照','窗边柔光','暖色侧光','冷色轮廓光','影棚柔光'] = '保留原光照'


class ImageTransformSave(ImageTransformPreview):
    preview_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm: Literal['save'] = 'save'


class ImageTransformUndo(BaseModel):
    model_config={'extra':'forbid'}
    revision: int


def _view(record):
    return {key: record[key] for key in (
        'id','asset','base_revision','revision_after','angle','light',
        'preview_hash','state','reversible','training_eligible','undo_revision',
        'result_observation',
    ) if key in record}


def _prepare(project, body):
    if project['revision'] != body.revision or project['id'] in store.RUNNING or project['state'] in ('running','rendering','planning'):
        raise HTTPException(409, '项目已变化或正在处理，请重新预览图片变换')
    asset = project.get('canvas_assets', {}).get(body.asset)
    if not asset or asset.get('kind') != 'image':
        raise HTTPException(422, '请选择属于此项目的图片素材')
    adjustments = {'angle': body.angle, 'light': body.light}
    preview_hash = content_hash({'asset': body.asset, 'asset_sha256': asset.get('sha256',''), 'adjustments': adjustments})
    return asset, adjustments, preview_hash


def install(gateway):
    install_reframe(gateway)
    from harness.studio.image_grid_api import install as install_grid
    install_grid(gateway)
    @gateway.app.post('/creative/api/projects/{pid}/image-transforms/preview')
    async def preview(pid: str, body: ImageTransformPreview, authorization: str | None = Header(None)):
        uid = gateway.require_session(authorization)['id']
        async with store.lock(pid):
            project = store.load(pid, uid)
            asset, adjustments, preview_hash = _prepare(project, body)
            return {
                'revision': project['revision'], 'asset': body.asset,
                'asset_sha256': asset.get('sha256',''), 'adjustments': adjustments,
                'preview_hash': preview_hash, 'preview_only': True, 'reversible': True,
                'training_eligible': False,
                'message': '仅更新画布预览，不保存、不扣积分，也不会调用生成模型',
            }

    @gateway.app.post('/creative/api/projects/{pid}/image-transforms/drafts')
    async def save_draft(pid: str, body: ImageTransformSave, authorization: str | None = Header(None)):
        uid = gateway.require_session(authorization)['id']
        async with store.lock(pid):
            project = store.load(pid, uid)
            asset, adjustments, preview_hash = _prepare(project, body)
            if body.preview_hash != preview_hash:
                raise HTTPException(409, '图片或变换已变化，请重新预览后保存')
            draft_id = secrets.token_hex(16)
            drafts = project.setdefault('image_transform_drafts', {})
            for record in drafts.values():
                if record.get('asset') == body.asset and record.get('state') == 'applied':
                    record['state'] = 'superseded'
                    record['reversible'] = False
            next_revision = project['revision'] + 1
            record = {
                'id': draft_id, 'asset': body.asset,
                'base_revision': project['revision'], 'revision_after': next_revision,
                'asset_sha256': asset.get('sha256',''), 'angle': adjustments['angle'],
                'light': adjustments['light'], 'preview_hash': preview_hash,
                'state': 'applied', 'reversible': True, 'training_eligible': False,
                'created_at': time.time(),
            }
            drafts[draft_id] = record
            for old_id in list(drafts)[:-20]:
                drafts.pop(old_id, None)
            project['revision'] = next_revision
            store.save(project, uid); store.event(project, 'tool', 'image_transform_draft_saved')
            return {'revision': project['revision'], 'draft': _view(record), 'project': store.present(project)}

    @gateway.app.post('/creative/api/projects/{pid}/image-transforms/drafts/{draft_id}/undo')
    async def undo_draft(pid: str, draft_id: str, body: ImageTransformUndo, authorization: str | None = Header(None)):
        if not draft_id or len(draft_id) != 32 or any(c not in '0123456789abcdef' for c in draft_id):
            raise HTTPException(422, '变换草稿标识无效')
        uid = gateway.require_session(authorization)['id']
        async with store.lock(pid):
            project = store.load(pid, uid)
            if project['revision'] != body.revision:
                raise HTTPException(409, '项目已继续编辑，暂不能安全撤销变换草稿')
            record = project.get('image_transform_drafts', {}).get(draft_id)
            if not isinstance(record, dict) or record.get('state') != 'applied' or not record.get('reversible'):
                raise HTTPException(404, '找不到可撤销的图片变换草稿')
            record['state'] = 'undone'; record['reversible'] = False
            record['undo_revision'] = project['revision'] + 1
            project['revision'] += 1
            store.save(project, uid); store.event(project, 'tool', 'image_transform_draft_undone')
            return {'revision': project['revision'], 'draft': _view(record), 'project': store.present(project)}


class ImageReframe(BaseModel):
    model_config = {'extra': 'forbid'}
    revision: int
    asset: str = Field(pattern=r'^[a-f0-9]{32}$')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    crop: tuple[float, float, float, float]
    rotation: Literal[0, 90, 180, 270] = 0
    mirror: bool = False


def install_reframe(gateway):
    @gateway.app.post('/creative/api/projects/{pid}/image-reframe')
    async def save_reframe(pid: str, body: ImageReframe, authorization: str | None = Header(None)):
        import asyncio
        from harness.tools.image_reframe import reframe
        from harness.tools.creative_canvas import save_asset, next_position
        from harness.tools.canvas_lineage import lineage, auto_place_generated_node
        uid = gateway.require_session(authorization)['id']
        async with store.lock(pid):
            project = store.load(pid, uid)
            fingerprint = content_hash(body.model_dump(exclude={'revision','request_id'}))
            previous = project.get('image_reframes', {}).get(body.request_id)
            if previous:
                if previous['request_hash'] != fingerprint:
                    raise HTTPException(409, '同一保存请求的裁剪参数已变化')
                return {'project': store.present(project), 'edit': previous}
            if project['revision'] != body.revision or pid in store.RUNNING or project['state'] in ('running','rendering','planning') or project.get('image_task', {}).get('state') == 'running':
                raise HTTPException(409, '项目已变化或正在处理，请重新打开图片裁剪')
            if len(project.get('canvas_assets', {})) >= 32 or len(project.get('canvas', {}).get('nodes', [])) >= 16:
                raise HTTPException(422, '画布或素材数量已达上限，请先整理素材')
            try:
                raw, receipt = await asyncio.to_thread(reframe, project, body.asset, body.crop, body.rotation, body.mirror)
                asset = await asyncio.to_thread(save_asset, project, raw, 'image')
            except (ValueError, OSError) as exc:
                raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else '无法读取图片来源，请重新上传') from None
            asset['provenance'] = {'kind':'image_reframe', 'sources':[body.asset], 'reframe':receipt}
            project.setdefault('canvas_assets', {})[asset['id']] = asset
            graph = project.setdefault('canvas', {'nodes':[], 'edges':[]})
            source = next((n for n in graph['nodes'] if n.get('asset') == body.asset), {})
            nid = 'n'+secrets.token_hex(16)
            graph['nodes'].append({'id':nid,'asset':asset['id'],'kind':'image','role':source.get('role','reference'),
                'label':(source.get('label','图片')[:65]+' · 裁剪版本'),'text':'',**next_position(graph, body.asset)})
            project['canvas'] = auto_place_generated_node(graph, lineage(project), nid)
            node = next(n for n in project['canvas']['nodes'] if n['id'] == nid)
            project['revision'] += 1
            project['canvas_auto_layout'] = {'mode':'image-reframe','node_id':nid,'asset':asset['id'],'x':node['x'],'y':node['y'],'revision':project['revision']}
            receipt.update(id=body.request_id, source_asset=body.asset, result_asset=asset['id'], request_hash=fingerprint, revision_after=project['revision'])
            project.setdefault('image_reframes', {})[body.request_id] = receipt
            project['updated_at'] = time.time()
            store.save(project, uid); store.event(project, 'tool', 'image_reframed')
            return {'project':store.present(project), 'edit':receipt}
