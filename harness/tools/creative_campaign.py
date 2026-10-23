"""Bounded chapter actions for an owner-scoped, approved advertising task."""
from copy import deepcopy
from harness.tools.creative_image_inputs import content_hash
from harness.tools.creative_video import film_prompt
from harness.tools.creative_video_inputs import prepare, validate, capabilities
from harness.tools.creative_canvas import save_asset, next_position
from harness.tools.creative_reference import reference_path
from harness.tools.creative_video_frame import extract_frame

MODE = 'chaptered_native'
DURATIONS = (30, 60)


def plan_digest(project):
    return content_hash({k: project.get(k) for k in
        ('model', 'provider', 'aspect', 'duration', 'video_inputs', 'reference')} |
        {'shots': [{k: s.get(k) for k in ('id', 'start', 'duration', 'prompt', 'audio_prompt', 'caption')}
                   for s in project['shots']]})


def validate_plan(project):
    from harness.models.video_catalog import model_spec
    if project.get('generation_mode') != MODE or project.get('creation_mode') != 'agent':
        raise ValueError('请选择 Agent 多章节制作')
    spec = model_spec(project['provider'], project['model'])
    if not spec.get('single_film') or 'references' not in capabilities(spec['id']):
        raise ValueError('多章节制作需要支持商品与衔接图共同参考的有声模型')
    if project['duration'] not in DURATIONS or len(project['shots']) != project['duration'] // 5:
        raise ValueError('多章节广告支持 30 或 60 秒，每章 15 秒')
    film_prompt(project)
    if project.get('video_inputs'):
        validate(project)
        inputs = project['video_inputs']
        if inputs['mode'] not in ('text', 'references') or len(inputs['references']) > 6:
            raise ValueError('请使用最多六张参考图，为章节衔接保留一个参考位置')
    # Reserve room before any paid submission, including legacy product import.
    if not project.get('campaign'):
        count = project['duration'] // 15
        extra = count * 2 + int(bool(project.get('reference') and not project.get('video_inputs')))
        if len(project.get('canvas', {}).get('nodes', [])) + extra > 16 or len(project.get('canvas_assets', {}))+extra>32:
            raise ValueError('画布空间不足，请为章节、衔接帧和成片预留节点空间')


def freeze(project, credits):
    validate_plan(project)
    digest = plan_digest(project)
    if project.get('campaign'):
        if project['campaign']['plan_digest'] != digest:
            raise ValueError('已批准的章节方案发生变化，请重新规划')
        return
    project['campaign'] = {'version': 1, 'plan_digest': digest, 'approved_credits': credits,
        'model': project['model'], 'duration': project['duration'], 'stage': 'queued',
        'training_eligible': False, 'chapters': [
            {'id': f'chapter_{i+1}', 'index': i, 'start': i*15, 'duration': 15, 'state': 'planned'}
            for i in range(project['duration']//15)]}


def add_asset(project, asset, label, sources, kind='video_generated'):
    asset['provenance'] = {'kind': kind, 'run_id': project['run_id'], 'model': project['model'],
                           'sources': sources, 'training_eligible': False}
    project.setdefault('canvas_assets', {})[asset['id']] = asset
    graph = project.setdefault('canvas', {'nodes': [], 'edges': []})
    graph['nodes'].append(dict(id='n'+asset['id'], kind=asset['kind'], asset=asset['id'],
        label=label, text='', role='reference', **next_position(graph, sources[-1] if sources else None)))
    return asset['id']


def bind_inputs(project):
    """Use only explicitly bound inputs; never guess from unrelated canvas images."""
    campaign = project['campaign']
    if 'references' in campaign:
        return
    if project.get('video_inputs'):
        campaign['references'] = [{k: r[k] for k in ('asset', 'role', 'instruction')}
                                  for r in project['video_inputs']['references']]
    elif project.get('reference'):
        asset = save_asset(project, reference_path(project).read_bytes(), 'image')
        aid = add_asset(project, asset, '商品参考', [], 'uploaded')
        campaign['references'] = [dict(asset=aid, role='product', instruction='保持商品几何、材质与颜色')]
    else:
        campaign['references'] = []


def chapter_project(project, chapter):
    view = deepcopy(project)
    start = chapter['start']
    view.update(generation_mode='single_native', duration=15)
    view['shots'] = [dict(s, start=s['start']-start) for s in project['shots'] if start <= s['start'] < start+15]
    refs = deepcopy(project['campaign']['references'])
    if chapter['index']:
        previous = project['campaign']['chapters'][chapter['index']-1]
        if previous['state'] != 'completed' or not previous.get('tail_asset'):
            raise ValueError('上一章尚未验证或缺少衔接帧')
        refs.append(dict(asset=previous['tail_asset'], role='scene',
            instruction='上一章结束画面，仅作开场构图与光色衔接；商品外观仍以商品参考为准'))
    view.pop('reference', None)
    view['video_inputs'] = prepare(view, project['model'], 'references' if refs else 'text', refs)
    return view


def chapter_prompt(view, chapter, total):
    return film_prompt(view) + (f'\nThis is chapter {chapter["index"]+1} of {total}, '
        f'global time {chapter["start"]}–{chapter["start"]+15}s. '
        'Follow the approved overall story and preserve product geometry/material/color. '
        'Previous tail image is a soft continuity reference, not proof of exact continuity. '
        + ('Do not conclude the advertisement or add an end card; hand off naturally to the next chapter.'
           if chapter['index'] < total-1 else 'Complete the approved ending.'))


def materialize_chapter(project, chapter, path):
    if not chapter.get('asset'):
        asset = save_asset(project, path.read_bytes(), 'video', max_bytes=256*1024*1024, max_duration=30)
        chapter['asset'] = add_asset(project, asset, f'第 {chapter["index"]+1} 章 · 15 秒',
                                    [r['asset'] for r in chapter['inputs']['references']])
    if chapter['index'] < len(project['campaign']['chapters'])-1 and not chapter.get('tail_asset'):
        frame, node = extract_frame(project, chapter['asset'], 14.875, 'current')
        node['label'] = f'第 {chapter["index"]+1} 章衔接帧'
        chapter['tail_asset'] = frame['id']


def attach_final(project, path):
    asset = save_asset(project, path.read_bytes(), 'video', max_bytes=256*1024*1024, max_duration=180)
    aid = add_asset(project, asset, f'Agent 成片 · {project["duration"]} 秒',
                    [c['asset'] for c in project['campaign']['chapters']], 'video_edit')
    project['result_asset'] = aid
    return aid


def bind_plan_inputs(project):
    """An explicit image→Director connection with a semantic role authorizes reference binding, not payment."""
    if project.get('video_inputs') or project.get('reference'): return
    graph = project.get('canvas', {})
    linked = {e['source'] for e in graph.get('edges', []) if e.get('target')=='director'}
    refs = [dict(asset=n['asset'], role=n['role'], instruction=n.get('text','')[:240])
            for n in graph.get('nodes', []) if n['id'] in linked and n['kind']=='image'
            and n.get('role') in ('product','person','scene','style')]
    if len(refs)>6: raise ValueError('章节制作最多绑定六张图片参考')
    if refs:
        project['video_inputs'] = prepare(project, project['model'], 'references', refs)
        project['video_inputs_product'] = project.get('brief',{}).get('product','')


def publish_to_workspace(parent, child):
    """Copy the completed graph and its ancestry into the originating workspace."""
    import shutil
    import tempfile
    from pathlib import Path
    from harness.tools.creative_canvas import asset_directory, validate_graph
    if child.get('manual_parent') != parent['id'] or parent.get('director_project') != child['id']:
        raise ValueError('Agent 结果不属于当前工作区')
    ids = {c['asset'] for c in child['campaign']['chapters']} | {child['result_asset']}
    ids.update(c['tail_asset'] for c in child['campaign']['chapters'] if c.get('tail_asset'))
    ids.update(r['asset'] for r in child['campaign']['references'])
    graph = deepcopy(parent.get('canvas', {'nodes': [], 'edges': []}))
    assets = deepcopy(parent.get('canvas_assets', {}))
    for n in child['canvas']['nodes']:
        aid = n.get('asset')
        if aid not in ids: continue
        asset = child['canvas_assets'][aid]
        if aid in assets and assets[aid] != asset: raise ValueError('工作区素材标识冲突')
        assets[aid] = deepcopy(asset)
        if not any(existing.get('asset')==aid for existing in graph['nodes']):
            sources = asset.get('provenance', {}).get('sources', [])
            graph['nodes'].append(dict(n, id='n'+aid, **next_position(graph, sources[-1] if sources else None)))
    graph = validate_graph(graph, assets)
    if len(assets)>32: raise ValueError('工作区素材空间不足，完整结果仍保留在 Agent 项目')
    for aid in ids:
        source, target = asset_directory(child, aid), asset_directory(parent, aid)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent, prefix='.campaign-') as staging:
                copied=Path(staging)/'asset';shutil.copytree(source,copied);copied.rename(target)
    changed = graph != parent.get('canvas') or assets != parent.get('canvas_assets')
    parent.update(canvas=graph, canvas_assets=assets)
    return changed
