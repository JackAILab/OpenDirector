"""Compile the approved single-clock timeline to a HyperFrames deliverable."""
import html
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FFPROBE = os.getenv('CREATIVE_FFPROBE', '/tmp/visualagent-fftools/node_modules/ffprobe-static/bin/linux/x64/ffprobe')


def probe(path):
    result = subprocess.run([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def render(project, directory):
    if (directory/'final.mp4').exists(): raise FileExistsError('refusing to overwrite a rendered artifact')
    width, height = {'16:9': (1280,720), '9:16': (720,1280), '1:1': (720,720)}[project['aspect']]
    shutil.copyfile(ROOT/'tools/asset_studio/public/fonts/studio-chinese.woff2', directory/'font.woff2')
    gsap = Path(os.environ['CREATIVE_GSAP'])
    shutil.copyfile(gsap, directory/'gsap.min.js')
    clips = []
    audio_expected = False
    native = project.get('generation_mode')=='single_native'
    if native:
        verify_native_audio(directory/'film.mp4', project['duration'])
        audio_expected = True
        clips.append(f'<video id="film" class="clip footage" src="film.mp4" data-start="0" data-duration="{project["duration"]}" data-track-index="0" data-has-audio="true" playsinline></video>')
    for i, shot in enumerate(project['shots']):
        start, duration = shot['start'], shot['duration']
        if not native:
            meta = probe(directory/(shot['id']+'.mp4'))
            if float(meta['format']['duration']) < shot['duration']-.15: raise RuntimeError('源视频时长不足，停止合成。')
            has_source_audio = any(s['codec_type']=='audio' for s in meta['streams'])
            audio_expected |= has_source_audio
            audio_attr = 'data-has-audio="true"' if has_source_audio else 'muted'
            clips.append(f'<video id="video-{i}" class="clip footage" src="{shot["id"]}.mp4" data-start="{start}" data-duration="{duration}" data-track-index="0" {audio_attr} playsinline></video>')
        # Empty subtitles must not add a gradient or decorative rule to clean footage.
        if not shot.get('caption', '').strip():
            continue
        caption = html.escape(shot['caption']).replace('\n', '<br>')
        clips.append(f'<section id="copy-{i}" class="clip copy" data-start="{start}" data-duration="{duration}" data-track-index="1"><h1>{caption}</h1><div class="rule"></div></section>')
    source = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Creative timeline</title><script src="gsap.min.js"></script><style>
@font-face{{font-family:Studio;src:url(font.woff2)}}*{{box-sizing:border-box}}body{{margin:0;background:#101311;color:white;font-family:Studio,sans-serif}}#root{{position:relative;width:{width}px;height:{height}px;overflow:hidden}}.clip{{position:absolute}}.footage{{inset:0;width:100%;height:100%;object-fit:cover}}.copy{{left:0;bottom:0;width:100%;padding:80px 48px 50px;background:linear-gradient(transparent,rgba(0,0,0,.88));}}h1{{font-size:{40 if width>height else 44}px;line-height:1.3;max-width:90%;margin:16px 0;overflow-wrap:anywhere}}.label{{font-size:15px;letter-spacing:3px;color:#d9e8df}}.rule{{width:60px;height:4px;background:#d8ecab}}
</style></head><body><div id="root" data-composition-id="ad" data-width="{width}" data-height="{height}" data-duration="{project['duration']}">{''.join(clips)}</div><script>const tl=gsap.timeline({{paused:true}});tl.to({{}},{{duration:{project['duration']}}});window.__timelines['ad']=tl;</script></body></html>'''
    (directory/'index.html').write_text(source)
    (directory/'hyperframes.json').write_text(json.dumps({'compositions':[{'id':'ad','name':'Creative ad','entry':'index.html','width':width,'height':height,'duration':project['duration'],'fps':24}]}))
    cli = os.environ['CREATIVE_HYPERFRAMES']
    env = dict(os.environ, HYPERFRAMES_FFMPEG_PATH=os.environ['CREATIVE_FFMPEG'], HYPERFRAMES_FFPROBE_PATH=FFPROBE)
    for command in ([cli,'check'], [cli,'render','--output',str(directory/'final.mp4'),'--fps','24','--quality','high','--workers','2']):
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True, timeout=1800)
        if result.returncode:
            (directory/'render-error.log').write_bytes(result.stdout+result.stderr)
            raise RuntimeError('时间轴合成检查未通过，已保留素材，未交付未经检查的成片。')
    output = probe(directory/'final.mp4')
    if abs(float(output['format']['duration'])-project['duration'])>.2: raise RuntimeError('成片时长检查失败。')
    video = next((s for s in output['streams'] if s['codec_type']=='video'), None)
    if not video or (video['width'],video['height']) != (width,height): raise RuntimeError('成片画幅检查失败。')
    has_audio = any(s['codec_type']=='audio' for s in output['streams'])
    if audio_expected and not has_audio: raise RuntimeError('源音轨未保留，停止交付。')
    if native: verify_native_audio(directory/'final.mp4', project['duration'])
    return {'generation_mode':project.get('generation_mode','legacy_segments'),'technical':'passed','duration':project['duration'],'width':width,'height':height,'audio':has_audio,'semantic':'pending','human':'pending','training_eligible':False}


def verify_native_audio(path, duration):
    """Require actual video/audio duration and audible signal, not just an enable flag."""
    import re
    import math
    meta=probe(path)
    video=next((s for s in meta['streams'] if s['codec_type']=='video'),None)
    audio=next((s for s in meta['streams'] if s['codec_type']=='audio'),None)
    if not video or float(video.get('duration',meta['format']['duration'])) < duration-.08:
        raise RuntimeError('整片画面时长不足，不能交付。')
    if not audio or float(audio.get('duration',meta['format']['duration'])) < duration-.15:
        raise RuntimeError('整片缺少完整音轨，不能作为有声广告交付。')
    result=subprocess.run([os.environ['CREATIVE_FFMPEG'],'-hide_banner','-i',str(path),'-map','0:a:0','-af','volumedetect','-vn','-f','null','-'],capture_output=True,text=True,timeout=120)
    match=re.search(r'mean_volume:\s*(-?[\d.]+|[-+]?inf) dB',result.stderr)
    mean=float(match.group(1)) if match else float('-inf')
    if result.returncode or not math.isfinite(mean) or mean < -55:
        raise RuntimeError('音轨静音或响度过低，需审阅后重新制作；不会自动重新生成。')
    return {'duration':float(meta['format']['duration']),'audio':True,'mean_volume_db':mean,'semantic':'pending'}


def verify_manual_video(path, duration):
    """Verify the model output without imposing the Agent's soundtrack policy."""
    import math
    meta=probe(path)
    video=next((s for s in meta['streams'] if s['codec_type']=='video'),None)
    actual=float(meta['format']['duration'])
    if not video or not math.isfinite(actual) or actual<duration-.15:
        raise RuntimeError('生成视频画面或时长不完整，结果保留待检查')
    return {'duration':actual,'width':video['width'],'height':video['height'],
            'audio':any(s['codec_type']=='audio' for s in meta['streams']),
            'technical':'passed','semantic':'pending','human':'pending','training_eligible':False}
