"""Copy a completed, owned child result into its parent's editable asset graph."""
from copy import deepcopy
import hashlib
import shutil
import tempfile
from pathlib import Path
from harness.tools.creative_canvas import asset_directory, validate_graph, next_position


def import_result(parent, child):
    if child.get('manual_parent') != parent['id'] or not any(n['project'] == child['id'] for n in parent.get('manual_nodes', [])):
        raise ValueError('结果不属于当前画布')
    task = child.get('image_task', {})
    if child.get('creation_mode') == 'image' or (child.get('creation_mode') == 'agent' and task.get('state') == 'completed' and not (child.get('state') == 'completed' and child.get('result_artifact') == child.get('artifact') and child.get('result_asset'))):
        aid = task.get('asset') if task.get('state') == 'completed' else None
    else:
        aid = child.get('result_asset') if child.get('state') == 'completed' and child.get('result_artifact') == child.get('artifact') else None
    source = child.get('canvas_assets', {}).get(aid)
    if not aid or not source:
        raise ValueError('生成结果尚未就绪')
    assets = deepcopy(parent.get('canvas_assets', {}))
    if aid in assets and assets[aid] != source:
        raise ValueError('素材标识冲突')
    assets[aid] = deepcopy(source)
    graph = deepcopy(parent.get('canvas', {'nodes': [], 'edges': []}))
    nid = 'result_' + hashlib.sha256((child['id'] + ':' + aid).encode()).hexdigest()[:24]
    existing = next((n for n in graph['nodes'] if n.get('asset') == aid), None)
    if existing:
        return existing, False
    occupied = deepcopy(graph)
    occupied['nodes'] += [{'x':parent.get('manual_position',{}).get('x',40),'y':parent.get('manual_position',{}).get('y',40)}]
    occupied['nodes'] += [{'x':n.get('x',660+(i%3)*580),'y':n.get('y',40+(i//3)*620)} for i,n in enumerate(parent.get('manual_nodes',[]))]
    node = dict(id=nid, kind=source['kind'], asset=aid, label='生成结果 · ' + ('图片' if source['kind'] == 'image' else '视频'), text='', role='reference', **next_position(occupied))
    graph['nodes'].append(node)
    graph = validate_graph(graph, assets)
    source_dir, target = asset_directory(child, aid), asset_directory(parent, aid)
    if not source_dir.is_dir():
        raise ValueError('结果文件不可读取')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix='.result-') as staging:
            temporary = Path(staging) / 'asset'
            shutil.copytree(source_dir, temporary)
            temporary.rename(target)
    parent['canvas_assets'], parent['canvas'] = assets, graph
    # Deliberately unconnected: importing for editing does not change model inputs.
    return node, True
