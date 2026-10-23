"""Split owned video into two new assets; never change or regenerate its source."""
import copy
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from harness.tools.creative_canvas import asset_directory, asset_metadata, next_position, save_asset


def split_audio(project, aid):
    asset = project.get('canvas_assets', {}).get(aid)
    if not asset or asset.get('kind') != 'video':
        raise ValueError('请选择当前画布中的视频素材')
    graph = copy.deepcopy(project.get('canvas', {'nodes': [], 'edges': []}))
    if len(graph['nodes']) > 14 or len(project['canvas_assets']) > 30:
        raise ValueError('分离需要两个空余素材位置，请先整理画布')
    metadata = asset_metadata(project, aid)
    if not metadata.get('has_audio'):
        raise ValueError('当前视频无音轨，无法分离音视频')
    if metadata['duration'] > 60:
        raise ValueError('音视频分离暂支持 60 秒以内的视频')
    directory = asset_directory(project, aid).resolve()
    source = (directory / asset['filename']).resolve()
    if source.parent != directory or not source.is_file():
        raise ValueError('视频源文件不可读取')
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='creative-audio-split-') as temporary:
            muted, audio = Path(temporary)/'muted.mp4', Path(temporary)/'audio.m4a'
            base = [os.environ['CREATIVE_FFMPEG'], '-v', 'error', '-nostdin',
                    '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov', '-i', str(source)]
            subprocess.run(base + ['-map','0:v:0','-c:v','copy','-an','-map_metadata','-1',
                           '-movflags','+faststart',str(muted)], capture_output=True, check=True, timeout=60)
            subprocess.run(base + ['-map','0:a:0','-vn','-c:a','aac','-b:a','192k',
                           '-map_metadata','-1','-movflags','+faststart',str(audio)],
                           capture_output=True, check=True, timeout=60)
            for path, kind in ((muted,'video'),(audio,'audio')):
                if path.stat().st_size > 256*1024*1024: raise ValueError('分离结果超过大小限制')
                result = save_asset(project, path.read_bytes(), kind, max_bytes=256*1024*1024)
                created.append(result)
                result['provenance'] = {'kind':'audio_split','sources':[aid],'training_eligible':False}
        original = next((n for n in graph['nodes'] if n.get('asset')==aid), {})
        title = str(original.get('label') or '视频')[:70]
        nodes = []
        for result, suffix in zip(created, ('无声','音轨')):
            node = dict(id='n'+result['id'],kind=result['kind'],asset=result['id'],label=title+'_'+suffix,
                        text='',role='reference',**next_position(graph,aid))
            graph['nodes'].append(node); nodes.append(node)
    except Exception as exc:
        for result in created: shutil.rmtree(asset_directory(project,result['id']),ignore_errors=True)
        if isinstance(exc,ValueError): raise
        raise ValueError('音视频分离失败，原视频保持不变') from exc
    project['canvas_assets'].update({a['id']:a for a in created})
    project['canvas'] = graph
    return created, nodes
