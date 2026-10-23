"""Attach a verified deliverable to its owner canvas without regenerating media."""
from pathlib import Path
import secrets
import hashlib
from harness.tools.creative_canvas import save_asset
from harness.studio import store

MAX_GENERATED_VIDEO_BYTES = 256 * 1024 * 1024


def attach_result(project, owner, path: Path):
    artifact = str(path.resolve().relative_to(store.DATA.resolve()))
    if path.stat().st_size > MAX_GENERATED_VIDEO_BYTES:
        raise RuntimeError('生成视频超过 256 MB，源视频已保留，画布导入待处理')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    latest = store.load(project['id'], owner)
    assets = latest.setdefault('canvas_assets', {})
    existing = next((a for a in assets.values()
                     if a.get('provenance', {}).get('run_id') == project['run_id']
                     and a.get('provenance', {}).get('kind') == 'video_generated'
                     and a.get('sha256') == digest), None)
    graph = latest.setdefault('canvas', {'nodes': [], 'edges': []})
    asset = existing or save_asset(project, raw, 'video',
                                   max_bytes=MAX_GENERATED_VIDEO_BYTES, max_duration=180)
    if not existing:
        asset['provenance'] = {'kind': 'video_generated', 'run_id': project['run_id'],
                               'model': project['model'], 'training_eligible': False,
                               'sources': [r['asset'] for r in (project.get('video_inputs') or {}).get('references', []) if r.get('asset')]}
        assets[asset['id']] = asset
    if not any(n.get('asset') == asset['id'] for n in graph['nodes']):
        nid = 'n' + secrets.token_hex(12)
        x = max((n.get('x', 0) + 380 for n in graph['nodes']), default=40)
        graph['nodes'].append({'id': nid, 'kind': 'video', 'asset': asset['id'],
                               'role': 'reference', 'label': '生成的视频', 'text': '', 'x': x, 'y': 40})
    project['canvas_assets'] = assets
    project['canvas'] = graph
    project['result_asset'] = asset['id']
    project['result_artifact'] = artifact
    return asset['id']
