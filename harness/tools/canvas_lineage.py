"""Owned asset provenance and bounded, deterministic canvas arrangement.

Provenance is projected from production receipts, never accepted as canvas input.
Input edges still mean director context; derivation edges never authorize a model.
"""
import copy
import math

ROLES = {'product': '商品', 'person': '人物', 'scene': '场景', 'style': '风格', 'story': '脚本', 'reference': '其他参考'}


def layout_observation(project):
    """Return a bounded explanation of the current canvas arrangement.

    The observation is intentionally descriptive: it exposes no file contents,
    provider payloads, or raw trajectory data, and never mutates the project.
    """
    graph = project.get('canvas', {'nodes': [], 'edges': []})
    nodes = [node for node in graph.get('nodes', []) if isinstance(node, dict)]
    auto = project.get('canvas_auto_layout') if isinstance(project.get('canvas_auto_layout'), dict) else {}
    auto_id = auto.get('node_id') if isinstance(auto.get('node_id'), str) else None
    auto_node = next((node for node in nodes if node.get('id') == auto_id), None)
    current = bool(auto_node and auto.get('x') == auto_node.get('x') and auto.get('y') == auto_node.get('y'))

    # Use the same conservative card footprint as the canvas arranger. This is
    # only for a collision count; the UI still lets the user inspect and move
    # cards manually.
    occupied = []
    for node in nodes:
        width = 280
        height = 400 if node.get('kind') in ('image', 'video') else 450
        occupied.append((node, float(node.get('x', 0)), float(node.get('y', 0)), width, height))
    collisions = []
    for index, (left, lx, ly, lw, lh) in enumerate(occupied):
        for right, rx, ry, rw, rh in occupied[index + 1:]:
            if lx < rx + rw + 24 and rx < lx + lw + 24 and ly < ry + rh + 24 and ry < ly + lh + 24:
                collisions.append({'a': str(left.get('id', ''))[:48], 'b': str(right.get('id', ''))[:48]})

    if not nodes:
        mode, reason = 'empty', '画布还没有参考素材'
    elif current:
        mode, reason = 'auto', '按素材来源链路分列，新生成结果靠近其来源并避开已有卡片'
    elif auto_node:
        mode, reason = 'manual_adjusted', '自动排版已完成，之后检测到用户移动过卡片，保留手动位置'
    else:
        mode, reason = 'manual', '当前布局来自用户手动摆放，尚未记录自动排版依据'
    return {
        'schema': 'canvas-layout-observation-v1',
        'mode': mode,
        'reason': reason,
        'node_count': len(nodes),
        'arranged_node_id': auto_id,
        'arranged_node_label': str(auto_node.get('label', ''))[:80] if auto_node else None,
        'collision_count': len(collisions),
        'collisions': collisions[:8],
        'within_bounds': all(abs(float(node.get('x', 0))) <= 9000 and abs(float(node.get('y', 0))) <= 9000 for node in nodes),
        'training_eligible': False,
    }


def lineage(project):
    assets = project.get('canvas_assets', {})
    records = {}
    for aid, asset in assets.items():
        p = asset.get('provenance', {})
        kind = p.get('kind', 'uploaded')
        sources = [s for s in p.get('sources', []) if s in assets and s != aid]
        records[aid] = {'kind': kind, 'sources': sources}
        if kind == 'video_frame' and p.get('source_position') in ('first','last','current'):
            records[aid]['source_position'] = p['source_position']
        if kind == 'video_frame' and isinstance(p.get('source_time'), (int, float)):
            records[aid]['source_time'] = p['source_time']
        if isinstance(p.get('reframe'), dict):
            records[aid]['reframe'] = {k:p['reframe'][k] for k in ('crop','rotation','mirror','source_dimensions','result_dimensions') if k in p['reframe']}
        if isinstance(p.get('grid'), dict):
            records[aid]['grid'] = {k:p['grid'][k] for k in ('rows','columns','row','column','pixel_box','source_dimensions') if k in p['grid']}
        if p.get('region_edit'):records[aid]['region_edit']=p['region_edit']
        if p.get('control_parameters'):
            from harness.tools.creative_image_inputs import normalize_control_parameters
            try:records[aid]['control_parameters']=normalize_control_parameters(p['control_parameters'])
            except ValueError:pass
        if p.get('adjustments'):
            records[aid]['adjustments']={k:p['adjustments'][k] for k in ('angle','light') if k in p['adjustments']}
        if p.get('transform_draft_id'):
            records[aid]['transform_draft_id'] = p['transform_draft_id']
        observation = p.get('transform_alignment')
        if isinstance(observation, dict):
            records[aid]['transform_alignment'] = {
                k: observation[k] for k in (
                    'schema', 'status', 'source_dimensions', 'result_dimensions',
                    'sample_dimensions', 'changed_pixel_ratio',
                    'mean_absolute_error', 'human_review_required', 'training_eligible',
                ) if k in observation
            }
        if p.get('inputs'):
            records[aid]['inputs']=[{k:v for k,v in item.items() if k in ('asset','role','instruction','sha256')}
                                   for item in p['inputs'] if item.get('asset') in sources]
        if p.get('reference_id'): records[aid]['reference_id'] = p['reference_id']
        if kind=='video_edit':
            records[aid]['clips']=[c for c in p.get('clips',[]) if c.get('asset') in sources]
            records[aid]['export_id']=p.get('export_id')
    # Older completed image attempts already contain exact output/source IDs.
    # Do not infer a historical reference from the project's current reference.
    for task in project.get('image_attempts', []):
        aid = task.get('asset')
        if task.get('state') != 'completed' or aid not in assets: continue
        source = task.get('source_asset') or task.get('reference_asset')
        if 'provenance' not in assets[aid]:
            records[aid] = {'kind': 'image_edit' if source or task.get('reference_id') else 'image_generated',
                            'sources': [source] if source in assets and source != aid else []}
            if task.get('adjustments'):
                records[aid]['adjustments']={k:task['adjustments'][k] for k in ('angle','light') if k in task['adjustments']}
            if task.get('transform_draft_id'):
                records[aid]['transform_draft_id'] = task['transform_draft_id']
            if task.get('reference_id'): records[aid]['reference_id'] = task['reference_id']
    return records


def derivation_edges(graph, records):
    edges = []
    for child in graph.get('nodes', []):
        for aid in records.get(child.get('asset'), {}).get('sources', []):
            for parent in graph.get('nodes', []):
                if parent.get('asset') == aid and parent['id'] != child['id']:
                    edges.append({'source': parent['id'], 'target': child['id'], 'kind': 'derived'})
    return edges


def arrange(graph, records, sizes=None):
    """Return a draft, not a project mutation. Columns follow verified ancestry."""
    result = copy.deepcopy(graph)
    nodes = result['nodes']; sizes = sizes or {}
    if not isinstance(sizes, dict) or len(sizes) > 16: raise ValueError('节点尺寸无效')
    for size in sizes.values():
        if type(size) not in (int, float) or not math.isfinite(size) or not 100 <= size <= 1800:
            raise ValueError('节点高度需在 100–1800 之间')
    incoming = {n['id']: [] for n in nodes}
    for edge in derivation_edges(graph, records): incoming[edge['target']].append(edge['source'])
    levels = {}; roots = {}; order = {n['id']: i for i, n in enumerate(nodes)}
    roles = {n['id']: list(ROLES).index(n.get('role', 'reference')) for n in nodes}
    def visit(nid, stack):
        if nid in levels: return levels[nid]
        if nid in stack: raise ValueError('素材来源存在循环，请核对生成记录')
        parents = incoming[nid]
        levels[nid] = max((visit(p, stack | {nid})+1 for p in parents), default=0)
        roots[nid] = min((roots[p] for p in parents), default=(roles[nid], order[nid]))
        return levels[nid]
    for n in nodes: visit(n['id'], set())
    x = 40
    for level in sorted(set(levels.values())):
        layer = sorted((n for n in nodes if levels[n['id']] == level), key=lambda n: (roots[n['id']], roles[n['id']], order[n['id']]))
        y = 30; count = 0
        for n in layer:
            h = sizes.get(n['id'], 400 if n['kind'] in ('image', 'video') else 450)
            if count == 4 or y+h > 8000: x += 310; y = 30; count = 0
            n.update(x=x, y=y); y += h+54; count += 1
        x += 310
    return result


def auto_place_generated_node(graph, records, node_id, sizes=None):
    """Place one newly generated node without rewriting hand-placed nodes.

    A current source position anchors the suggestion; root nodes use the full
    lineage arrangement. A bounded search below occupied card extents finds
    the next free slot beside the source without legacy editor-sized gaps.  The
    returned graph is a draft and never mutates the caller's graph.
    """
    if not isinstance(node_id, str):
        raise ValueError('生成节点标识无效')
    source = next((n for n in graph.get('nodes', []) if n.get('id') == node_id), None)
    if not source:
        raise ValueError('生成节点不存在')
    sizes = sizes or {}
    suggested = arrange(graph, records, sizes)
    target = next(n for n in suggested['nodes'] if n['id'] == node_id)
    target_h = sizes.get(node_id, 400 if source.get('kind') in ('image', 'video') else 450)
    target_w = 280

    def box(node, x=None, y=None):
        return {
            'x': node.get('x', 0) if x is None else x,
            'y': node.get('y', 0) if y is None else y,
            'w': target_w if node is source else 280,
            'h': target_h if node is source else sizes.get(node['id'], 400 if node.get('kind') in ('image', 'video') else 450),
        }

    def overlaps(candidate, occupied):
        return any(
            candidate['x'] < item['x'] + item['w'] + 24
            and item['x'] < candidate['x'] + candidate['w'] + 24
            and candidate['y'] < item['y'] + item['h'] + 24
            and item['y'] < candidate['y'] + candidate['h'] + 24
            for item in occupied
        )

    occupied = [box(n) for n in graph['nodes'] if n['id'] != node_id]
    parents = [n for n in graph['nodes'] if n['id'] != node_id
               and n.get('asset') in records.get(source.get('asset'), {}).get('sources', [])]
    anchor = max(parents, key=lambda n: (n.get('x', 0), n.get('y', 0))) if parents else None
    base_x = anchor.get('x', 40) + 310 if anchor else target.get('x', 40)
    base_y = anchor.get('y', 30) if anchor else target.get('y', 30)
    candidate = box(source, base_x, base_y)
    if overlaps(candidate, occupied):
        # Pack below occupied card extents, rather than reserving legacy 900px rows.
        rows = sorted({base_y, *(item['y'] + item['h'] + 54 for item in occupied
                                if item['y'] + item['h'] + 54 >= base_y)})
        found = None
        for column in range(30):
            x = base_x + column * 310
            for y in rows:
                if x > 9000 or y > 9000:
                    continue
                candidate = box(source, x, y)
                if not overlaps(candidate, occupied):
                    found = candidate
                    break
            if found:
                candidate = found
                break
        else:
            candidate = box(source, 8500, 8500)

    result = copy.deepcopy(graph)
    next_node = next(n for n in result['nodes'] if n['id'] == node_id)
    next_node.update(x=candidate['x'], y=candidate['y'])
    return result
