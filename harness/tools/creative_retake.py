"""Freeze one selected clip, quote one visual edit, and verify a new candidate.

Retakes produce ordinary immutable edit assets. They never mutate the original
source or saved timeline. Both UI and Agent clients use these bounded actions.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess

from harness.models.kling_retake import MODEL, spool_root, input_path
from harness.models.video_catalog import quote
from harness.studio import store
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_media import source_catalog, source_path, digest, describe, media_probe, FFMPEG
from harness.tools.creative_video import CreativeVideoTool


def document_digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def directory(pid, jid):
    # IDs here come from owner-scoped records, not path parameters.
    import re
    if not re.fullmatch('[a-f0-9]{16,32}', pid) or not re.fullmatch('[a-f0-9]{32}', jid):
        raise ValueError('重拍任务标识无效')
    return store.DATA / 'retakes' / pid / jid


def _ffmpeg(args):
    subprocess.run([os.getenv('CREATIVE_FFMPEG', FFMPEG), '-v', 'error', '-nostdin', *args],
                   check=True, capture_output=True, timeout=180)


def prepare(project, index, intent):
    sources = source_catalog(project)
    spec = validate_edit(project.get('edit', {}), catalog=sources)
    if type(index) is not int or not 0 <= index < len(spec['clips']):
        raise ValueError('请先选中一个画面片段')
    if not isinstance(intent, str) or not 1 <= len(intent.strip()) <= 1600:
        raise ValueError('请用 1–1600 字说明要修改的画面')
    clip = spec['clips'][index]; source = sources[clip['source']]
    length = round(clip['end'] - clip['start'], 3)
    if not 3 <= length <= 10:
        raise ValueError('局部重拍支持 3–10 秒，请先分割或裁切当前片段')
    if not .3334 <= source['width'] / source['height'] <= 2.999:
        raise ValueError('此素材宽高比暂不支持局部重拍')
    if len(project.get('edit_assets', {})) >= 24:
        raise ValueError('每个项目最多保留 24 个剪辑素材')
    jid = secrets.token_hex(16); folder = directory(project['id'], jid)
    token = secrets.token_hex(32); spool = spool_root() / token
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    spool.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        # Freeze full source for exact, local audio restoration; provider sees no audio.
        original = source_path(project, clip['source'])
        shutil.copyfile(original, folder / 'original.mp4')
        if digest(folder / 'original.mp4') != source['sha256']:
            raise ValueError('原素材发生变化，请重新准备重拍')
        scale = 720 / min(source['width'], source['height'])
        width, height = [round(source[k] * scale / 2) * 2 for k in ('width', 'height')]
        frames = math.floor(length * 30 + .00001)
        _ffmpeg(['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov', '-ss', str(clip['start']), '-i', str(folder / 'original.mp4'), '-map', '0:v:0',
                 '-frames:v', str(frames), '-vf', f'scale={width}:{height},fps=30,setsar=1', '-an',
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p',
                 '-movflags', '+faststart', '-threads', '2', str(spool / 'base.mp4')])
        source_hash = digest(spool / 'base.mp4')
        input_path(token, source_hash)
        seconds = math.ceil(length)
        prompt = ('以视频1为原片段，按下面要求修改画面。保持片段时长、动作时间和未要求更改的商品细节。'
                  '不要加入可读文字、字幕或界面，不生成声音。\n' + intent.strip())
        public = {'id': jid, 'revision': project['revision'], 'state': 'ready', 'clip_index': index,
                  'clip': deepcopy(clip), 'source_sha256': source['sha256'], 'source_title': source['title'],
                  'base_digest': document_digest(spec), 'duration': length, 'input_duration': frames / 30,
                  'input_sha256': source_hash, 'width': width, 'height': height, 'model': MODEL,
                  'intent': intent.strip(), 'credits': quote('kling', MODEL, seconds),
                  'policy': 'retake-visual-v1', 'preserve_audio': source['has_audio'],
                  'training_eligible': False}
        private = {'reference': token, 'prompt': prompt, 'seconds': seconds, 'base_spec': spec}
        (folder / 'input.json').write_text(json.dumps(private, ensure_ascii=False))
        public['parameters_sha256'] = digest(folder / 'input.json')
        public['quote_digest'] = document_digest(public)
        for path in [folder / 'input.json', folder / 'original.mp4', spool / 'base.mp4']:
            path.chmod(0o600)
        return public
    except Exception:
        shutil.rmtree(folder, ignore_errors=True); shutil.rmtree(spool, ignore_errors=True)
        raise


def payload(project, job):
    path = directory(project['id'], job['id']) / 'input.json'
    if digest(path) != job['parameters_sha256']:
        raise ValueError('冻结的重拍要求发生变化')
    private = json.loads(path.read_text())
    input_path(private['reference'], job['input_sha256'])
    return {'provider': 'kling', 'task': 'v2v_edit', 'model': MODEL, 'prompt': private['prompt'],
            'target': {'duration_seconds': private['seconds'], 'short_edge': 720, 'aspect_ratio': 'auto'},
            'conditions': [{'type': 'video', 'role': 'base', 'reference': private['reference'], 'sha256': job['input_sha256']}],
            'enable_audio': False, 'prefer_multi_shots': False}


class CreativeRetakeTool(CreativeVideoTool):
    async def submit_retake(self, project, job):
        return (await self.request('POST', '/v1/videos',
            headers={'Idempotency-Key': 'retake-' + project['id'] + '-' + job['id']}, json=payload(project, job))).json()


def finish_candidate(project, job, raw):
    """No speed change. Only <= 0.12s boundary padding/trim is permitted."""
    folder = directory(project['id'], job['id'])
    original = folder / 'original.mp4'
    if digest(original) != job['source_sha256']:
        raise ValueError('冻结的原片段发生变化')
    probe = media_probe(raw)
    video = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
    if not video:
        raise ValueError('候选没有视频画面')
    actual = float(video.get('duration', probe['format']['duration']))
    if not math.isfinite(actual) or abs(actual - job['duration']) > .12:
        raise ValueError('候选时长与原片段不一致，已保留结果供核对，没有自动变速或重新生成')
    if min(video['width'], video['height']) < 720 or max(video['width'], video['height']) > 2160:
        raise ValueError('候选尺寸未达到本次 720p 要求，已保留结果供核对')
    if abs(video['width'] / video['height'] - job['width'] / job['height']) > .025:
        raise ValueError('候选宽高比发生变化，已保留结果供核对')
    aid = job['id']; output = store.DATA / 'edit-assets' / project['id'] / aid
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = output / 'source.mp4'
    if final.exists():
        # Recovery is a read/verification, never overwrite a previous candidate.
        metadata = json.loads((folder / 'candidate.json').read_text())
        if digest(final) != metadata['sha256']:
            raise ValueError('已保存候选校验失败')
        return metadata
    temporary = output / 'candidate.part.mp4'
    temporary.unlink(missing_ok=True)
    args = ['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov', '-i', str(raw),
            '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov',
            '-ss', str(job['clip']['start']), '-i', str(original), '-map', '0:v:0']
    if job['preserve_audio']:
        args += ['-map', '1:a:0', '-af', 'asetpts=PTS-STARTPTS,apad', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000']
    else:
        args += ['-an']
    args += ['-t', str(job['duration']), '-vf', 'setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.12,setsar=1',
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', '-threads', '2', str(temporary)]
    _ffmpeg(args)
    info = describe(temporary)
    if abs(info['duration'] - job['duration']) > .12 or info['has_audio'] != job['preserve_audio']:
        raise ValueError('候选时长或原声检查未通过')
    provenance = {'kind': 'video_retake', 'job_id': job['id'], 'model': MODEL,
                  'source': job['clip']['source'], 'source_sha256': job['source_sha256'],
                  'source_start': job['clip']['start'], 'source_end': job['clip']['end'],
                  'input_sha256': job['input_sha256'], 'raw_sha256': digest(raw),
                  'audio': 'original' if job['preserve_audio'] else 'none', 'training_eligible': False}
    metadata = dict(info, id=aid, filename='source.mp4', label='重拍候选 · ' + job['source_title'][:60], provenance=provenance)
    # Metadata is written first: a crash can leave a temp MP4, never a final without receipt.
    (folder / 'candidate.json').write_text(json.dumps(metadata, ensure_ascii=False))
    temporary.chmod(0o600); temporary.replace(final)
    return metadata


def candidate_plan(project, job):
    sources = source_catalog(project)
    spec = validate_edit(project['edit'], catalog=sources)
    if document_digest(spec) != job['base_digest']:
        raise ValueError('时间轴已改变，此候选保留为素材；请重新选择插入位置')
    sid = 'edit_' + job['id']
    if job['state'] != 'completed' or sid not in sources:
        raise ValueError('重拍候选尚未通过技术检查')
    spec['sources'][sid] = sources[sid]['sha256']
    spec['clips'][job['clip_index']] = dict(job['clip'], source=sid, start=0, end=job['duration'])
    return validate_edit(spec, catalog=sources)
