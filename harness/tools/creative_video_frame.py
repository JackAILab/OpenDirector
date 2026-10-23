"""Extract one owned video frame without a model call or modifying the source."""
import math
import os
import subprocess
import tempfile
from pathlib import Path
from harness.tools.creative_canvas import asset_directory, next_position, save_asset


def extract_frame(project, aid, at, position="current"):
    asset = project.get('canvas_assets', {}).get(aid)
    if not asset or asset.get('kind') != 'video':
        raise ValueError('请选择当前画布中的视频素材')
    if position not in ('current', 'first', 'last'):
        raise ValueError('请选择当前帧、首帧或尾帧')
    if position == 'first': at = 0
    duration = asset.get('duration')
    if (type(at) not in (int, float) or not math.isfinite(at) or
            not isinstance(duration, (int, float)) or not 0 <= at < duration):
        raise ValueError('取帧时间必须位于视频范围内')
    graph = project.get('canvas', {'nodes': [], 'edges': []})
    if len(graph['nodes']) >= 16 or len(project['canvas_assets']) >= 32:
        raise ValueError('画布素材已达上限，请先整理')
    directory = asset_directory(project, aid).resolve()
    source = (directory / asset['filename']).resolve()
    if source.parent != directory or not source.is_file():
        raise ValueError('视频源文件不可读取')
    try:
        command = [os.environ['CREATIVE_FFMPEG'], '-v', 'error', '-nostdin',
                   '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov']
        scale = "scale='min(3840,iw)':'min(2160,ih)':force_original_aspect_ratio=decrease"
        if position == 'last':
            # Decode the bounded tail and retain its last image, without buffering frames.
            with tempfile.TemporaryDirectory(prefix='creative-frame-') as temporary:
                output = Path(temporary) / 'last.png'
                subprocess.run(command + ['-sseof', str(-min(2, duration)), '-i', str(source),
                    '-an', '-vf', scale, '-update', '1', '-threads', '1', '-y', str(output)],
                    capture_output=True, check=True, timeout=30)
                data = output.read_bytes()
        else:
            result = subprocess.run(command + ['-ss', str(at), '-i', str(source), '-frames:v', '1',
                '-vf', scale, '-f', 'image2pipe', '-vcodec', 'png', '-threads', '1', 'pipe:1'],
                capture_output=True, check=True, timeout=30)
            data = result.stdout
        frame = save_asset(project, data, 'image', preserve_pixels=True)
    except (subprocess.SubprocessError, KeyError, OSError) as exc:
        raise ValueError('视频取帧失败，原视频保持不变') from exc
    frame['provenance'] = {'kind': 'video_frame', 'sources': [aid],
                           'source_position': position, 'training_eligible': False}
    if position != 'last': frame['provenance']['source_time'] = at
    node = dict(id='n' + frame['id'], kind='image', asset=frame['id'],
                label=('视频尾帧' if position == 'last' else '视频首帧' if position == 'first' else f'视频取帧 · {at:.2f}s'), text='', role='reference',
                **next_position(graph, aid))
    project['canvas_assets'][frame['id']] = frame
    project.setdefault('canvas', graph)['nodes'].append(node)
    return frame, node
