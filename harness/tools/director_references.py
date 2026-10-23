"""Explicit, owned image → Director → video input binding; no model calls."""
from copy import deepcopy
import secrets
from harness.tools.creative_canvas import next_position, validate_graph
from harness.tools.creative_video_inputs import capabilities, prepare


def check_available(project):
    if project.get('creation_mode') != 'agent':
        raise ValueError('请在 Agent 项目中添加参考图')
    if project.get('film', {}).get('state') not in (None, 'planned', 'completed', 'failed'):
        raise ValueError('原视频任务尚未结束，请先恢复查询')
    if project.get('campaign') and project.get('state') != 'completed':
        raise ValueError('已有章节任务，请先完成当前制作')
    current = project.get('video_inputs', {})
    caps = capabilities(project['model'])
    if current.get('mode') in ('first_frame', 'first_last') and current.get('references'):
        raise ValueError('已有首尾帧，请在视频参考设置中明确调整，不能自动替换')
    if project.get('reference') and not current.get('references'):
        raise ValueError('已有商品参考，请先在视频参考设置中确认输入，不能自动替换')
    count = len(current.get('references', []))
    limit = min(6, caps.get('references', caps.get('first_frame', 0)))
    if count >= limit:
        raise ValueError('当前视频模型的参考位已满或不支持图片，请先调整视频参考设置')


def attach(project, references):
    """Validate everything before replacing the graph/selection. Preserve question answers."""
    check_available(project)
    existing = [{k: r[k] for k in ('asset', 'role', 'instruction')}
                for r in project.get('video_inputs', {}).get('references', [])]
    ids = {r['asset'] for r in existing}
    additions = [r for r in references if r['asset'] not in ids]
    if len({r['asset'] for r in additions}) != len(additions):
        raise ValueError('参考图片不能重复')
    combined = existing + additions
    if len(combined) > 6:
        raise ValueError('最多绑定六张参考图，请先整理现有参考')
    mode = 'references' if 'references' in capabilities(project['model']) else 'first_frame'
    inputs = prepare(project, project['model'], mode, combined)
    graph = deepcopy(project.get('canvas', {'nodes': [], 'edges': []}))
    for ref in additions:
        node = next((n for n in graph['nodes'] if n.get('asset') == ref['asset']), None)
        if node is None:
            node = dict(id='n'+secrets.token_hex(16), kind='image', asset=ref['asset'],
                        label='Agent 参考图', text='', role=ref['role'], **next_position(graph))
            graph['nodes'].append(node)
        node.update(role=ref['role'], text=ref['instruction'])
        edge = {'source': node['id'], 'target': 'director'}
        if edge not in graph['edges']: graph['edges'].append(edge)
    graph = validate_graph(graph, project['canvas_assets'])
    project.update(canvas=graph, video_inputs=inputs,
                   video_inputs_product=project.get('brief', {}).get('product', ''),
                   video_inputs_needs_review=False)
    return inputs
