"""Explicit, bounded copy of a workspace image into an owned generator node."""
from copy import deepcopy
import hashlib
import shutil
import tempfile
from pathlib import Path
from harness.tools.creative_canvas import asset_directory, validate_graph, next_position


def import_reference(parent, child, aid):
    if child.get('manual_parent') != parent['id'] or not any(n['project'] == child['id'] for n in parent.get('manual_nodes', [])):
        raise ValueError('节点不属于当前画布')
    source = parent.get('canvas_assets', {}).get(aid)
    node = next((n for n in parent.get('canvas', {}).get('nodes', []) if n.get('asset') == aid), None)
    if not source or source.get('kind') != 'image' or not node:
        raise ValueError('请选择当前画布中的图片')
    assets = deepcopy(child.get('canvas_assets', {}))
    if aid in assets and assets[aid] != source:
        raise ValueError('素材标识冲突')
    graph = deepcopy(child.get('canvas', {'nodes': [], 'edges': []}))
    if any(n.get('asset') == aid for n in graph['nodes']):
        return False
    if len(assets) >= 32 and aid not in assets:
        raise ValueError('当前节点素材已满')
    assets[aid] = deepcopy(source)
    graph['nodes'].append(dict(id='ref_'+hashlib.sha256(aid.encode()).hexdigest()[:24],kind='image',asset=aid,
                              label=node.get('label') or '画布参考',text='',role=node.get('role','reference'),**next_position(graph)))
    graph = validate_graph(graph, assets)
    source_dir, target = asset_directory(parent, aid), asset_directory(child, aid)
    if not source_dir.is_dir():raise ValueError('参考图片文件不可读取')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent,prefix='.reference-') as staging:
            copied=Path(staging)/'asset';shutil.copytree(source_dir,copied);copied.rename(target)
    child['canvas_assets'],child['canvas']=assets,graph
    # Copying an asset is not approval to use it in a paid model request.
    return True
