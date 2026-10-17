"""Snapshot explicitly connected workspace references into the linked Director run."""
from copy import deepcopy
import hashlib
import shutil
import tempfile
from pathlib import Path
from harness.tools.creative_canvas import asset_directory, validate_graph


def sync_context(parent, child):
    if child.get('manual_parent') != parent['id'] or parent.get('director_project') != child['id']:
        raise ValueError('Director 不属于当前工作区')
    graph = parent.get('canvas', {'nodes': [], 'edges': []})
    linked = {e['source'] for e in graph.get('edges', []) if e.get('target') == 'director'}
    previous = set(child.get('workspace_context_nodes', []))
    current = child.get('canvas', {'nodes': [], 'edges': []})
    nodes = [deepcopy(n) for n in current['nodes'] if n['id'] not in previous]
    edges = [deepcopy(e) for e in current['edges'] if e['source'] not in previous]
    assets = deepcopy(child.get('canvas_assets', {}))
    imports, copies = [], []
    for original in graph.get('nodes', []):
        if original['id'] not in linked:
            continue
        node = deepcopy(original)
        node['id'] = 'ws_' + hashlib.sha256((parent['id'] + ':' + original['id']).encode()).hexdigest()[:24]
        if any(n['id'] == node['id'] for n in nodes):
            raise ValueError('工作区参考节点冲突')
        if node['kind'] != 'text':
            aid = node['asset']
            source = parent.get('canvas_assets', {}).get(aid)
            if not source:
                raise ValueError('工作区参考素材不存在')
            if aid in assets and assets[aid] != source:
                raise ValueError('工作区参考素材冲突')
            assets[aid] = deepcopy(source)
            copies.append((asset_directory(parent, aid), asset_directory(child, aid)))
        node.update(x=40, y=30 + 400 * len(imports))
        imports.append(node['id']); nodes.append(node)
        edges.append({'source': node['id'], 'target': 'director'})
    result = validate_graph({'nodes': nodes, 'edges': edges,
                             'groups': [{**g, 'members': [n for n in g.get('members', []) if n not in previous]}
                                        for g in current.get('groups', [])
                                        if sum(n not in previous for n in g.get('members', [])) >= 2]}, assets)
    # Immutable project-local assets keep historical message snapshots readable.
    for source, target in copies:
        if not source.is_dir():
            raise ValueError('工作区参考文件不可读取')
    for source, target in copies:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent, prefix=".context-") as staging:
                temporary = Path(staging) / "asset"
                shutil.copytree(source, temporary)
                temporary.rename(target)
    child['canvas'] = result
    child['canvas_assets'] = assets
    child['workspace_context_nodes'] = imports
