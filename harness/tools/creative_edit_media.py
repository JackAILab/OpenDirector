"""Owned local edit media, upload normalization and bounded audio analysis."""
import array
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from harness.studio import store
from harness.tools.creative_render import FFPROBE

MAX_EDIT_UPLOAD = 60 * 1024 * 1024
FFMPEG = '/tmp/visualagent-fftools/node_modules/ffmpeg-static/ffmpeg'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def media_probe(path):
    r=subprocess.run([os.getenv('CREATIVE_FFPROBE',FFPROBE),'-v','error','-protocol_whitelist','file,pipe',
        '-format_whitelist','mov,matroska,webm,wav,mp3,ogg,flac,aac','-show_streams','-show_format','-of','json',str(path)],
        capture_output=True,check=True,timeout=30)
    return json.loads(r.stdout)


def primary_path(project):
    if project.get('generation_mode')=='single_native' and project.get('film',{}).get('state')=='completed':
        path=store.DATA/'artifacts'/project['run_id']/'film.mp4'
    elif project.get('artifact'): path=store.DATA/project['artifact']
    else: raise ValueError('尚无生成视频，可先导入剪辑素材')
    return checked_path(path)


def checked_path(path):
    if not path.resolve().is_relative_to(store.DATA.resolve()) or not path.is_file():
        raise ValueError('源素材暂不可读取')
    return path


def source_path(project,sid='primary'):
    if sid=='primary': return primary_path(project)
    if not isinstance(sid,str) or not re.fullmatch(r'(canvas|edit)_[a-f0-9]{32}',sid): raise ValueError('剪辑素材标识无效')
    family,aid=sid.split('_',1)
    if family=='canvas':
        meta=project.get('canvas_assets',{}).get(aid)
        if not meta or meta.get('kind') not in ('video','audio'): raise ValueError('媒体素材不属于此项目')
        return checked_path(store.DATA/'canvas'/project['id']/aid/meta['filename'])
    meta=project.get('edit_assets',{}).get(aid)
    if not meta: raise ValueError('剪辑素材不属于此项目')
    return checked_path(store.DATA/'edit-assets'/project['id']/aid/meta['filename'])


@lru_cache(maxsize=128)
def _describe(path,mtime,size):
    path=Path(path);meta=media_probe(path);streams=meta['streams']
    video=next((s for s in streams if s['codec_type']=='video'),None)
    duration=float(meta['format']['duration'])
    if not math.isfinite(duration) or not .2<=duration<=120: raise ValueError('素材时长需在 0.2–120 秒之间')
    return {'sha256':digest(path),'duration':duration,'kind':'video' if video else 'audio',
            'has_audio':any(s['codec_type']=='audio' for s in streams),
            'width':int(video['width']) if video else 0,'height':int(video['height']) if video else 0}


def describe(path):
    stat=path.stat();return dict(_describe(str(path.resolve()),stat.st_mtime_ns,stat.st_size))


def source_catalog(project):
    choices=[]
    try: choices.append(('primary','生成原片',primary_path(project)))
    except ValueError: pass
    for aid,asset in project.get('canvas_assets',{}).items():
        if asset.get('kind') in ('video','audio'):
            choices.append(('canvas_'+aid,('画布音轨 ' if asset['kind']=='audio' else '画布视频 ')+aid[:6],source_path(project,'canvas_'+aid)))
    for aid,asset in project.get('edit_assets',{}).items():
        choices.append(('edit_'+aid,asset['label'],source_path(project,'edit_'+aid)))
    result={}
    for sid,title,path in choices:
        result[sid]=dict(describe(path),id=sid,title=title)
        if sid.startswith('canvas_'):
            origin = project.get('canvas_assets', {}).get(sid[7:], {}).get('provenance', {})
            export_id = origin.get('export_id')
            if origin.get('kind') == 'video_edit' and isinstance(export_id, str) and re.fullmatch('[a-f0-9]{32}', export_id):
                result[sid]['edit_export_id'] = export_id
    return result


def save_upload(project,raw,kind,label):
    if kind not in ('video','audio') or not raw or len(raw)>MAX_EDIT_UPLOAD: raise ValueError('请选择 60 MB 以内的视频或音频')
    aid=secrets.token_hex(16);directory=store.DATA/'edit-assets'/project['id']/aid
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    try:
        upload=directory/'upload.bin';upload.write_bytes(raw)
        meta=media_probe(upload);duration=float(meta['format']['duration']);streams=meta['streams']
        if not math.isfinite(duration) or not .2<=duration<=120: raise ValueError('素材时长需在 0.2–120 秒之间')
        video=next((s for s in streams if s['codec_type']=='video'),None);has_audio=any(s['codec_type']=='audio' for s in streams)
        if kind=='video' and (not video or video['width']*video['height']>8_400_000): raise ValueError('请选择 4K 以内的视频')
        if kind=='audio' and not has_audio: raise ValueError('文件没有可用音轨')
        filename='source.mp4' if kind=='video' else 'source.m4a'
        args=[os.getenv('CREATIVE_FFMPEG',FFMPEG),'-v','error','-nostdin','-protocol_whitelist','file,pipe',
              '-format_whitelist','mov,matroska,webm,wav,mp3,ogg,flac,aac','-i',str(upload),'-t','120']
        if kind=='video':
            args+=['-map','0:v:0','-map','0:a:0?','-vf',"scale=w='min(1920,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                   '-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p']
        else: args+=['-map','0:a:0','-vn']
        args+=['-c:a','aac','-b:a','192k','-ac','2','-ar','48000','-movflags','+faststart','-threads','2',str(directory/filename)]
        subprocess.run(args,capture_output=True,check=True,timeout=240)
        info=describe(directory/filename)
        for path in directory.iterdir(): path.chmod(0o600)
        return dict(info,id=aid,filename=filename,label=label.strip()[:80] or ('视频素材' if kind=='video' else '音频素材'))
    except Exception as exc:
        shutil.rmtree(directory)
        if isinstance(exc,ValueError): raise
        raise ValueError('无法读取素材，请使用常规视频、WAV、MP3 或 M4A') from exc


def waveform(project,sid):
    path=source_path(project,sid);meta=describe(path)
    directory=store.DATA/'edit-analysis'/project['id'];directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    cached=directory/(meta['sha256']+'.json')
    if cached.is_file(): return json.loads(cached.read_text())
    peaks=[]
    if meta['has_audio']:
        r=subprocess.run([os.getenv('CREATIVE_FFMPEG',FFMPEG),'-v','error','-nostdin','-protocol_whitelist','file,pipe',
            '-i',str(path),'-map','0:a:0','-t','120','-ac','1','-ar','8000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=45)
        pcm=array.array('f');pcm.frombytes(r.stdout)
        if sys.byteorder!='little': pcm.byteswap()
        count=min(1200,max(1,len(pcm)//80));step=max(1,math.ceil(len(pcm)/count))
        peaks=[round(min(1,max(abs(x) for x in pcm[i:i+step])),4) for i in range(0,len(pcm),step)]
    result={'sha256':meta['sha256'],'duration':meta['duration'],'has_audio':meta['has_audio'],'peaks':peaks}
    temp=directory/(secrets.token_hex(12)+'.tmp');temp.write_text(json.dumps(result));temp.chmod(0o600);temp.replace(cached)
    return result
