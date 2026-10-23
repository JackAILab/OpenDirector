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
    changed = import_assets(parent, child, [aid])
    return next(n for n in parent['canvas']['nodes'] if n.get('asset') == aid), changed


def import_assets(parent, child, requested):
    """Copy result ancestry, preserving existing positions and generation inputs."""
    if child.get('manual_parent') != parent['id'] or not any(n['project'] == child['id'] for n in parent.get('manual_nodes', [])):
        raise ValueError('结果不属于当前画布')
    assets = deepcopy(parent.get('canvas_assets', {}))
    graph = deepcopy(parent.get('canvas', {'nodes': [], 'edges': []}))
    ordered, visiting, visited = [], set(), set()
    def visit(aid):
        if aid in visiting: raise ValueError('素材来源存在循环')
        if aid in visited: return
        source = child.get('canvas_assets', {}).get(aid) or assets.get(aid)
        if not source: raise ValueError('素材来源缺失，结果保留在 Agent 项目')
        visiting.add(aid)
        if len(visiting)+len(visited)>32: raise ValueError('素材来源数量超限')
        for ancestor in source.get('provenance', {}).get('sources', []): visit(ancestor)
        visiting.remove(aid);visited.add(aid);ordered.append((aid, source))
        if len(ordered)>32: raise ValueError('素材来源数量超限')
    for aid in requested: visit(aid)
    occupied = deepcopy(graph)
    occupied['nodes'] += [{'x':parent.get('manual_position',{}).get('x',40),'y':parent.get('manual_position',{}).get('y',40)}]
    occupied['nodes'] += [{'x':n.get('x',660+(i%3)*580),'y':n.get('y',40+(i//3)*620)} for i,n in enumerate(parent.get('manual_nodes',[]))]
    for aid, source in ordered:
        if aid in assets and assets[aid] != source: raise ValueError('素材标识冲突')
        assets[aid] = deepcopy(source)
        if any(n.get('asset') == aid for n in graph['nodes']): continue
        original = next((n for n in child.get('canvas',{}).get('nodes',[]) if n.get('asset') == aid), {})
        sources = source.get('provenance',{}).get('sources',[])
        node = dict(id='result_'+hashlib.sha256((child['id']+':'+aid).encode()).hexdigest()[:24],
                    kind=source['kind'], asset=aid, label=original.get('label') or '生成结果 · '+('图片' if source['kind']=='image' else '视频'),
                    text=original.get('text',''), role=original.get('role','reference'),
                    **next_position(occupied, sources[-1] if sources else None))
        graph['nodes'].append(node);occupied['nodes'].append(node)
    graph = validate_graph(graph, assets)
    if len(assets)>32: raise ValueError('画布素材空间不足')
    # Validate before copying. Existing shared ancestors are immutable and reused.
    for aid, source in ordered:
        source_dir, target = asset_directory(child, aid), asset_directory(parent, aid)
        if target.exists(): continue
        if not source_dir.is_dir(): raise ValueError('结果文件不可读取')
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix='.result-') as staging:
            temporary = Path(staging)/'asset';shutil.copytree(source_dir, temporary)
            try: temporary.rename(target)
            except FileExistsError:
                if not target.is_dir(): raise
    changed = assets != parent.get('canvas_assets',{}) or graph != parent.get('canvas',{})
    parent['canvas_assets'], parent['canvas'] = assets, graph
    # Provenance draws source lines; importing does not alter model input edges.
    return changed
