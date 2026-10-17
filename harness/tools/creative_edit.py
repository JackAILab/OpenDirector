"""Bounded, multi-source edit document and deterministic HyperFrames export."""
import html
import json
import math
import os
import re
import shutil
import subprocess
from harness.studio import store
from harness.tools.creative_edit_timing import validate_transitions, schedule, automation, visual_tweens
from harness.tools.creative_render import probe
from harness.tools.creative_edit_media import source_path,digest,source_catalog
from harness.tools.creative_captions import appearance, track_visibility, word_alignment


def skill_rhythm(project, duration=None):
    """Build a bounded, editable rhythm guide from the selected Skill steps.

    This is a planning track only. It does not claim that the source film was
    measured frame by frame; users can move the markers before saving.
    """
    skill = project.get('skill') or {}
    steps = [str(value).strip() for value in skill.get('steps') or [] if str(value).strip()]
    checks = [str(value).strip() for value in skill.get('checks') or [] if str(value).strip()]
    if not steps and not checks:
        return []
    total = float(duration if duration is not None else project.get('duration') or 15)
    total = max(0.2, min(60.0, total))
    parsed = []
    for step in steps:
        match = re.search(r'(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*秒\s*[·:：-]\s*(.+)', step)
        if not match:
            continue
        start, end = float(match.group(1)), float(match.group(2))
        if 0 <= start < end <= total:
            parsed.append((start, end, match.group(3).strip()[:160]))
    if not parsed:
        count = min(3, max(1, len(steps)))
        parsed = []
        for index in range(count):
            start = round(total * index / count, 3)
            end = round(total * (index + 1) / count, 3)
            label = (steps[index] if index < len(steps) else f'第 {index + 1} 个节拍')[:160]
            parsed.append((start, end, label))
    return [dict(start=round(start, 3), end=round(end, 3), label=label,
                 step=label, check=(checks[index] if index < len(checks) else '待人工核对')[:160])
            for index, (start, end, label) in enumerate(parsed[:12])]


def skill_track_plan(project, spec=None, duration=None):
    """Map Skill beats to existing edit tracks without creating media.

    The result is a bounded observation for the editor: it reports which
    picture, caption, and audio items overlap each beat and which tracks the
    Skill appears to require. It never changes the edit or calls a provider.
    """
    spec = spec or {}
    rhythm = list(spec.get('rhythm') or skill_rhythm(project, duration=duration))[:12]
    clips = spec.get('clips') or []
    captions = spec.get('captions') or []
    audio = spec.get('audio') or []
    skill = project.get('skill') or {}
    evidence = [str(value).strip() for value in [*(skill.get('steps') or []), *(skill.get('checks') or [])] if str(value).strip()]
    caption_required = any(re.search(r'字幕|文案|口播|旁白|caption|voice', value, re.I) for value in evidence)
    audio_required = any(re.search(r'声音|音频|旁白|音乐|音效|听感|口播|audio|music|sound', value, re.I) for value in evidence)
    clip_windows = []
    cursor = 0.0
    for item in clips[:32]:
        try:
            length = max(0.0, float(item.get('end')) - float(item.get('start')))
        except (AttributeError, TypeError, ValueError):
            continue
        clip_windows.append((cursor, cursor + length))
        cursor += length

    def overlaps(start, end, item_start, item_end):
        try:
            return float(start) < float(item_end) - .001 and float(end) > float(item_start) + .001
        except (TypeError, ValueError):
            return False

    rows = []
    for index, beat in enumerate(rhythm):
        start, end = float(beat['start']), float(beat['end'])
        picture = [i for i, window in enumerate(clip_windows) if overlaps(start, end, *window)]
        caption = [i for i, item in enumerate(captions[:60]) if overlaps(start, end, item.get('start'), item.get('end'))]
        sound = [i for i, item in enumerate(audio[:16]) if overlaps(start, end, item.get('at'), float(item.get('at', 0)) + float(item.get('end', 0)) - float(item.get('start', 0)))]
        rows.append({
            'id': f'beat-{index + 1}', 'start': round(start, 3), 'end': round(end, 3),
            'label': str(beat.get('label') or f'第 {index + 1} 个节拍')[:160],
            'step': str(beat.get('step') or '')[:160], 'check': str(beat.get('check') or '')[:160],
            'picture_indices': picture, 'caption_indices': caption, 'audio_indices': sound,
            'picture_status': 'covered' if picture else 'missing',
            'caption_status': 'covered' if caption else ('missing' if caption_required else 'not_required'),
            'audio_status': 'covered' if sound else ('missing' if audio_required else 'not_required'),
        })
    caption_collisions = []
    for left_index, left in enumerate(captions[:60]):
        for right_index, right in enumerate(captions[:60][left_index + 1:], left_index + 1):
            if left.get('track', 0) != right.get('track', 0):
                continue
            if overlaps(left.get('start'), left.get('end'), right.get('start'), right.get('end')):
                caption_collisions.append({
                    'kind': 'caption', 'track': int(left.get('track', 0)),
                    'left_index': left_index, 'right_index': right_index,
                })
    audio_overlaps = 0
    for left_index, left in enumerate(audio[:16]):
        left_start = left.get('at')
        left_end = float(left.get('at', 0)) + float(left.get('end', 0)) - float(left.get('start', 0))
        for right in audio[:16][left_index + 1:]:
            right_start = right.get('at')
            right_end = float(right.get('at', 0)) + float(right.get('end', 0)) - float(right.get('start', 0))
            if overlaps(left_start, left_end, right_start, right_end):
                audio_overlaps += 1
    summary = {
        'beats': len(rows),
        'picture_covered': sum(row['picture_status'] == 'covered' for row in rows),
        'caption_required': caption_required,
        'caption_covered': sum(row['caption_status'] == 'covered' for row in rows),
        'audio_required': audio_required,
        'audio_covered': sum(row['audio_status'] == 'covered' for row in rows),
    }
    summary['gaps'] = sum(row['picture_status'] == 'missing' for row in rows)
    summary['gaps'] += sum(row['caption_status'] == 'missing' for row in rows)
    summary['gaps'] += sum(row['audio_status'] == 'missing' for row in rows)
    return {
        'version': 2, 'summary': summary, 'beats': rows,
        'constraints': {
            'status': 'caption_overlap' if caption_collisions else 'clear',
            'caption_collisions': caption_collisions[:12],
            'audio_overlap_count': min(audio_overlaps, 32),
            'requires_manual_review': bool(caption_collisions or audio_overlaps),
        },
        'training_eligible': False,
    }


def skill_material_bindings(project):
    """Suggest existing canvas references for Skill roles without mutating them."""
    skill = project.get('skill') or {}
    graph = project.get('canvas') or {}
    nodes = [node for node in graph.get('nodes', [])
             if isinstance(node, dict) and node.get('kind') in ('image', 'video')]
    evidence = [str(value).strip()[:160] for value in [
        *(skill.get('references') or []), *(skill.get('steps') or []), *(skill.get('checks') or [])
    ] if str(value).strip()]
    role_terms = (
        ('product', re.compile(r'商品|产品|材质|结构|product|material|detail', re.I)),
        ('person', re.compile(r'人物|模特|角色|演员|person|model|talent', re.I)),
        ('scene', re.compile(r'场景|环境|空间|地点|scene|location|environment', re.I)),
        ('style', re.compile(r'风格|色调|光线|氛围|style|lighting|mood', re.I)),
    )
    def detect_role(value):
        return next((name for name, pattern in role_terms if pattern.search(value)), None)

    def candidates(role):
        return [node for node in nodes if node.get('role') == role][:4]

    rows = []
    seen = set()
    for requirement in evidence:
        role = detect_role(requirement)
        if not role or role in seen:
            continue
        seen.add(role)
        matches = candidates(role)
        rows.append({
            'role': role,
            'requirement': requirement,
            'status': 'matched' if matches else 'missing',
            'candidate_node_ids': [str(node.get('id', ''))[:48] for node in matches],
            'candidate_labels': [str(node.get('label', ''))[:80] for node in matches],
            'candidate_source_ids': [f"canvas_{node.get('asset')}" for node in matches
                                     if node.get('kind') == 'video' and isinstance(node.get('asset'), str)],
        })
    shot_rows = []
    for index, beat in enumerate(skill_rhythm(project)[:12]):
        context = ' '.join(str(beat.get(key) or '') for key in ('label', 'step', 'check'))[:480]
        role = detect_role(context)
        matches = candidates(role) if role else []
        shot_rows.append({
            'shot_id': f'beat-{index + 1}',
            'start': beat['start'], 'end': beat['end'],
            'label': str(beat.get('label') or f'第 {index + 1} 个节拍')[:160],
            'role': role or 'unclassified',
            'status': 'matched' if matches else ('missing' if role else 'unclassified'),
            'candidate_node_ids': [str(node.get('id', ''))[:48] for node in matches],
            'candidate_labels': [str(node.get('label', ''))[:80] for node in matches],
            'candidate_source_ids': [f"canvas_{node.get('asset')}" for node in matches
                                     if node.get('kind') == 'video' and isinstance(node.get('asset'), str)],
        })
    return {'version': 2, 'rows': rows[:8], 'shot_bindings': shot_rows,
            'training_eligible': False}


def skill_version_impact(project, spec, latest_skill):
    """Project a newer Skill onto the current edit without changing anything.

    This is a review-only comparison.  It deliberately exposes counts and
    short method excerpts instead of a full private recipe, then compares the
    current multi-track coverage with the coverage implied by the newer
    contract.  Applying a Skill update remains a separate, explicit action.
    """
    current_skill = project.get('skill') or {}
    current_version = int(current_skill.get('version') or 1)
    latest = latest_skill if isinstance(latest_skill, dict) else {}
    latest_version = int(latest.get('version') or current_version)
    fields = ('inputs', 'references', 'steps', 'checks')
    labels = {'inputs': '输入要求', 'references': '参考图职责',
              'steps': '制作步骤', 'checks': '验收门槛'}
    changes = []
    for field in fields:
        before = [str(value).strip()[:160] for value in current_skill.get(field) or [] if str(value).strip()]
        after = [str(value).strip()[:160] for value in latest.get(field) or [] if str(value).strip()]
        if before == after:
            continue
        before_set, after_set = set(before), set(after)
        changes.append({
            'field': field, 'label': labels[field],
            'before_count': len(before), 'after_count': len(after),
            'added': [value for value in after if value not in before_set][:4],
            'removed': [value for value in before if value not in after_set][:4],
        })
    before_project = dict(project, skill=current_skill)
    after_project = dict(project, skill=latest)
    duration = spec.get('duration') or project.get('duration')
    before_rhythm = skill_rhythm(before_project, duration=duration)
    after_rhythm = skill_rhythm(after_project, duration=duration)
    before_plan = skill_track_plan(before_project, spec, duration=duration)
    after_plan = skill_track_plan(after_project, spec, duration=duration)
    before_gaps = int(before_plan.get('summary', {}).get('gaps', 0))
    after_gaps = int(after_plan.get('summary', {}).get('gaps', 0))
    return {
        'version': 1,
        'from_version': current_version,
        'to_version': latest_version,
        'changed_fields': changes[:4],
        'rhythm': {'before': before_rhythm[:12], 'after': after_rhythm[:12]},
        'track_plan': {'before': before_plan.get('summary', {}),
                       'after': after_plan.get('summary', {})},
        'gaps_delta': after_gaps - before_gaps,
        'requires_explicit_confirmation': True,
        'training_eligible': False,
    }


def initial_edit(project,sha=None,catalog=None):
    if catalog is None:
        catalog={'primary':{'sha256':sha,'kind':'video','duration':project['duration'],'has_audio':True}}
    first=next((s for s,m in catalog.items() if m['kind']=='video'),None)
    raw=first=='primary' and project.get('generation_mode')=='single_native' and project.get('film',{}).get('state')=='completed'
    return {'version':2,'sources':{s:m['sha256'] for s,m in catalog.items()},
            'source_sha256':catalog.get('primary',{}).get('sha256'),
            'clips':[{'source':first,'start':0,'end':min(60,catalog[first]['duration']),'gain':1}] if first else [],
            'captions':[{'start':s['start'],'end':s['start']+s['duration'],'text':s['caption'],'track':0}
                        for s in project.get('shots',[]) if raw and s.get('caption')], 'audio':[], 'volume':1}


def validate_edit(spec,source_duration=None,sha=None,*,catalog=None):
    def number(value):
        if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('时间和音量必须是有限数值')
        return round(value,3)
    def gain(value):
        n=number(value)
        if not 0<=n<=1: raise ValueError('音量需在 0–100% 之间')
        return n
    def muted(item):
        value=item.get('muted',False)
        if type(value) is not bool: raise ValueError('静音状态必须为布尔值')
        return value
    if not isinstance(spec,dict): raise ValueError('编辑文档无效')
    if catalog is None: catalog={'primary':{'duration':source_duration,'sha256':sha,'kind':'video','has_audio':True}}
    bindings=spec.get('sources',{'primary':spec.get('source_sha256')})
    if not isinstance(bindings,dict): raise ValueError('素材绑定无效')
    used={}
    def source(c,kind):
        sid=c.get('source','primary')
        if not isinstance(sid,str): raise ValueError('素材标识无效')
        meta=catalog.get(sid)
        if not meta or (kind=='video' and meta['kind']!='video') or (kind=='audio' and not meta['has_audio']):
            raise ValueError('素材不属于此项目或不支持该轨道')
        if bindings.get(sid)!=meta['sha256']: raise ValueError('源素材已变化，请重新载入素材后编辑')
        used[sid]=meta['sha256'];return sid,meta
    def window(c,limit):
        if not isinstance(c,dict): raise ValueError('片段无效')
        start,end=number(c.get('start')),number(c.get('end'))
        if not 0<=start<end<=limit+.01 or end-start<.2: raise ValueError('片段需在素材内，至少 0.2 秒')
        return start,end
    clips=spec.get('clips',[])
    if not isinstance(clips,list) or not 1<=len(clips)<=32: raise ValueError('保留 1–32 个视频片段')
    clean=[]
    for c in clips:
        if not isinstance(c,dict): raise ValueError('视频片段无效')
        sid,meta=source(c,'video');start,end=window(c,meta['duration'])
        clean.append(dict(source=sid,start=start,end=end,gain=gain(c.get('gain',1)),muted=muted(c),transition=c.get('transition',{'kind':'cut','duration':0})))
    validate_transitions(clean)
    timings=schedule(clean)
    duration=round(timings[-1]['at']+timings[-1]['length'],3)
    if duration>60: raise ValueError('编辑成片最长 60 秒')
    captions=spec.get('captions',[])
    if not isinstance(captions,list) or len(captions)>60: raise ValueError('最多 60 段字幕')
    texts=[]
    for c in captions:
        start,end=window(c,duration);text=c.get('text','');track=c.get('track',0)
        if not isinstance(text,str) or not 1<=len(text.strip())<=120: raise ValueError('每段字幕为 1–120 字')
        if type(track) is not int or not 0<=track<=2: raise ValueError('请选择三个字幕轨道之一')
        if any(t['track']==track and start<t['end']-.001 and end>t['start']+.001 for t in texts):
            raise ValueError('同一字幕轨道不能重叠，请调整时间或移到另一轨')
        texts.append(dict(start=start,end=end,text=text.strip(),track=track,appearance=appearance(c.get('appearance')),**word_alignment(dict(c,start=start,end=end))))
    audio=spec.get('audio',[])
    if not isinstance(audio,list) or len(audio)>16: raise ValueError('最多 16 段独立音频')
    sounds=[]
    for c in audio:
        if not isinstance(c,dict): raise ValueError('音频片段无效')
        sid,meta=source(c,'audio');start,end=window(c,meta['duration']);at=number(c.get('at'));length=end-start
        if not 0<=at or at+length>duration+.01: raise ValueError('音频片段需位于成片时间范围内')
        fade_in,fade_out=number(c.get('fade_in',0)),number(c.get('fade_out',0))
        if min(fade_in,fade_out)<0 or fade_in+fade_out>length: raise ValueError('音频淡入淡出时间超过片段时长')
        sounds.append(dict(source=sid,start=start,end=end,at=at,gain=gain(c.get('gain',.3)),muted=muted(c),fade_in=fade_in,fade_out=fade_out))
    rhythm=spec.get('rhythm',[])
    if rhythm is None: rhythm=[]
    if not isinstance(rhythm,list) or len(rhythm)>12: raise ValueError('Skill 节奏轨最多 12 个节拍')
    clean_rhythm=[]
    for item in rhythm:
        if not isinstance(item,dict): raise ValueError('Skill 节奏项无效')
        start,end=window(item,duration)
        label=str(item.get('label','')).strip()
        step=str(item.get('step','')).strip()
        check=str(item.get('check','')).strip()
        if not 1<=len(label)<=160 or len(step)>160 or len(check)>160: raise ValueError('Skill 节奏说明长度无效')
        clean_rhythm.append(dict(start=start,end=end,label=label,step=step[:160],check=check[:160]))
    return dict(version=5,sources=used,source_sha256=used.get('primary'),clips=clean,captions=texts,caption_visibility=track_visibility(spec.get('caption_visibility')),audio=sounds,rhythm=clean_rhythm,volume=gain(spec.get('volume',1)),duration=duration)


def render_edit(project,spec,directory):
    catalog=source_catalog(project);spec=validate_edit(spec,catalog=catalog)
    first=catalog[spec['clips'][0]['source']]
    width,height={'16:9':(1280,720),'9:16':(720,1280),'1:1':(720,720)}.get(project.get('aspect'),(first['width'],first['height']))
    duration=spec['duration'];directory.mkdir(parents=True,exist_ok=False)
    filenames={}
    for i,sid in enumerate(spec['sources']):
        source=source_path(project,sid);name=f'source-{i}'+('.mp4' if catalog[sid]['kind']=='video' else '.m4a')
        shutil.copyfile(source,directory/name);filenames[sid]=name
    shutil.copyfile(store.ROOT/'tools/asset_studio/public/fonts/studio-chinese.woff2',directory/'font.woff2')
    shutil.copyfile(os.environ['CREATIVE_GSAP'],directory/'gsap.min.js')
    shutil.copyfile(store.ROOT/'tools/agent_studio/editor-captions.js',directory/'captions.js')
    layers=[];audio_expected=False;timings=schedule(spec['clips'])
    for i,(c,timing) in enumerate(zip(spec['clips'],timings)):
        length=timing['length'];cursor=timing['at'];src=filenames[c['source']];volume=0 if c['muted'] else spec['volume']*c['gain']
        layers.append(f'<div id="visual-{i}" class="visual"><video id="picture-{i}" class="clip footage" src="{src}" data-start="{cursor}" data-duration="{length}" data-media-start="{c["start"]}" data-track-index="{i%2}" muted playsinline></video></div>')
        if catalog[c['source']]['has_audio'] and volume>0:
            audio_expected=True
            envelope=automation(length,volume,timing['incoming'],timing['outgoing'])
            layers.append(f'<audio id="sound-{i}" class="clip" src="{src}" data-start="{cursor}" data-duration="{length}" data-media-start="{c["start"]}" data-track-index="{2+i%2}" data-volume="{volume}"{envelope}></audio>')
    for i,c in enumerate(spec['audio']):
        length=c['end']-c['start'];g=0 if c['muted'] else c['gain']
        if not g: continue
        audio_expected=True
        envelope=automation(length,g,c['fade_in'],c['fade_out'])
        layers.append(f'<audio id="extra-{i}" class="clip" src="{filenames[c["source"]]}" data-start="{c["at"]}" data-duration="{length}" data-media-start="{c["start"]}" data-track-index="{4+i}" data-volume="{g}"{envelope}></audio>')
    for i,c in enumerate(spec['captions']):
        if spec['caption_visibility'][c['track']]:
            content=''.join(f'<span data-word-index="{j}">{html.escape(w["text"])}</span>' for j,w in enumerate(c['words'])) if c.get('words') else html.escape(c['text'])
            layers.append(f'<div id="caption-{i}" class="clip caption" data-start="{c["start"]}" data-duration="{c["end"]-c["start"]}" data-track-index="{20+c["track"]}"><span class="caption-effect">{content}</span></div>')
    # Only validated presentation/timing goes into executable JSON; text is escaped in HTML above.
    presentation=[{k:c[k] for k in ('start','end','track','appearance')} for c in spec['captions']]
    for c,p in zip(spec['captions'],presentation):
        if c.get('words'):p.update(word_highlight=c['word_highlight'],words=[{k:w[k] for k in ('start','end')} for w in c['words']])
    text=f'''<!doctype html><html><head><meta charset="utf-8"><script src="gsap.min.js"></script><style>
@font-face{{font-family:Studio;src:url(font.woff2)}}*{{box-sizing:border-box}}body{{margin:0;background:#111}}#root{{width:100%;height:100%;position:relative;overflow:hidden;background:#080808}}.visual{{position:absolute;inset:0;pointer-events:none}}.footage{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#080808}}
</style><script src="captions.js"></script></head><body><div id="root" data-composition-id="edit" data-width="{width}" data-height="{height}" data-duration="{duration}">{''.join(layers)}</div><script>const tl=gsap.timeline({{paused:true}});{visual_tweens(spec['clips'],timings)}EditCaptions.mountTimeline(tl,{json.dumps(presentation)},{width},{height});window.__timelines=window.__timelines||{{}};window.__timelines['edit']=tl;</script></body></html>'''
    (directory/'index.html').write_text(text);(directory/'edit.json').write_text(json.dumps(spec,ensure_ascii=False))
    (directory/'hyperframes.json').write_text(json.dumps({'compositions':[{'id':'edit','name':'Creative edit','entry':'index.html','width':width,'height':height,'duration':duration,'fps':24}]}))
    cli=os.environ['CREATIVE_HYPERFRAMES'];env=dict(os.environ,HYPERFRAMES_FFMPEG_PATH=os.environ['CREATIVE_FFMPEG'])
    if os.getenv('CREATIVE_FFPROBE'): env['HYPERFRAMES_FFPROBE_PATH']=os.environ['CREATIVE_FFPROBE']
    for args in ([cli,'check'],[cli,'render','--output',str(directory/'final.mp4'),'--fps','24','--quality','high','--workers','2']):
        result=subprocess.run(args,cwd=directory,env=env,capture_output=True,timeout=1800)
        if result.returncode:
            (directory/'render-error.log').write_bytes(result.stdout+result.stderr)
            raise RuntimeError('剪辑渲染未通过检查，源素材与草稿均保留')
    result=probe(directory/'final.mp4');out_video=next(s for s in result['streams'] if s['codec_type']=='video')
    if abs(float(result['format']['duration'])-duration)>.2 or (out_video['width'],out_video['height'])!=(width,height): raise RuntimeError('导出时长或画幅检查失败')
    audio=any(s['codec_type']=='audio' for s in result['streams'])
    if audio_expected and not audio: raise RuntimeError('导出未保留所选音轨')
    return {'technical':'passed','duration':duration,'audio':audio,'sources':len(spec['sources']),'semantic':'pending','human':'pending','training_eligible':False}
