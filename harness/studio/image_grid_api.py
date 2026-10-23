"""Owner-scoped, idempotent image grid slicing with canvas lineage."""
import asyncio
import secrets
import shutil
import time
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field, StrictInt
from harness.studio import store
from harness.tools.creative_image_inputs import content_hash
from harness.tools.creative_canvas import save_asset, asset_directory, next_position
from harness.tools.canvas_lineage import lineage, auto_place_generated_node
from harness.tools.image_grid import split_grid


class ImageGrid(BaseModel):
    model_config = {'extra':'forbid'}
    revision: int
    asset: str = Field(pattern=r'^[a-f0-9]{32}$')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    rows: StrictInt = Field(ge=2, le=3)
    columns: StrictInt = Field(ge=2, le=3)


def install(gateway):
    @gateway.app.post('/creative/api/projects/{pid}/image-grid')
    async def image_grid(pid: str, body: ImageGrid, authorization: str | None = Header(None)):
        uid = gateway.require_session(authorization)['id']
        async with store.lock(pid):
            project = store.load(pid, uid)
            fingerprint = content_hash(body.model_dump(exclude={'revision','request_id'}))
            previous = project.get('image_grids', {}).get(body.request_id)
            if previous:
                if previous['request_hash'] != fingerprint:
                    raise HTTPException(409, '同一切分请求的参数已变化')
                return {'project':store.present(project), 'edit':previous}
            if project['revision'] != body.revision or pid in store.RUNNING or project['state'] in ('running','rendering','planning') or project.get('image_task', {}).get('state') == 'running':
                raise HTTPException(409, '项目已变化或正在处理，请重新打开宫格切分')
            count = body.rows * body.columns
            if len(project.get('canvas_assets', {}))+count > 32 or len(project.get('canvas', {}).get('nodes', []))+count > 16:
                raise HTTPException(422, '画布空间不足，请先整理素材或选择较少宫格（最多 16 个素材节点）')
            created = []
            try:
                tiles, receipt = await asyncio.to_thread(split_grid, project, body.asset, body.rows, body.columns)
                for raw, tile in tiles:
                    asset = await asyncio.to_thread(save_asset, project, raw, 'image', preserve_pixels=True)
                    created.append(asset)
                    asset['provenance'] = {'kind':'image_grid', 'sources':[body.asset], 'grid':{**receipt, **tile}}
            except Exception as exc:
                for asset in created:
                    shutil.rmtree(asset_directory(project, asset['id']), ignore_errors=True)
                if isinstance(exc, (ValueError, OSError)):
                    raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else '无法读取图片来源，请重新上传') from None
                raise
            graph = project.setdefault('canvas', {'nodes':[], 'edges':[]})
            source = next((n for n in graph['nodes'] if n.get('asset') == body.asset), {})
            for asset in created:
                project.setdefault('canvas_assets', {})[asset['id']] = asset
                grid = asset['provenance']['grid']; nid = 'n'+secrets.token_hex(16)
                graph['nodes'].append({'id':nid, 'asset':asset['id'], 'kind':'image', 'role':source.get('role','reference'),
                    'label':source.get('label','图片')[:50]+f" · 宫格 {grid['row']}-{grid['column']}", 'text':'', **next_position(graph, body.asset)})
                graph = auto_place_generated_node(graph, lineage(project), nid)
                project['canvas'] = graph
            project['revision'] += 1
            node = next(n for n in graph['nodes'] if n['asset'] == created[0]['id'])
            project['canvas_auto_layout'] = {'mode':'image-grid','node_id':node['id'],'asset':node['asset'],'x':node['x'],'y':node['y'],'revision':project['revision']}
            receipt.update(id=body.request_id, source_asset=body.asset, result_assets=[a['id'] for a in created], request_hash=fingerprint, revision_after=project['revision'])
            project.setdefault('image_grids', {})[body.request_id] = receipt
            project['updated_at'] = time.time()
            store.save(project, uid); store.event(project, 'tool', 'image_grid_split')
            return {'project':store.present(project), 'edit':receipt}
