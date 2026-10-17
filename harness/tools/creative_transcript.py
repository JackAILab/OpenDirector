"""Owned source speech evidence and source-clock to edit-clock caption projection."""
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from harness.models import creative_speech
from harness.tools.creative_edit_media import describe, source_path, FFMPEG
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_timing import schedule


def normalize_transcript(raw,duration):
    def number(value):
        if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('识别时间戳无效')
        return round(value,3)
    if not isinstance(raw,dict) or not isinstance(raw.get('segments'),list) or len(raw['segments'])>500:raise ValueError('识别结果无效')
    segments=[];words=[];bad=0;count=0
    for s in raw['segments']:
        if not isinstance(s,dict) or not isinstance(s.get('words'),list):raise ValueError('识别词列表无效')
        timed=[]
        for w in s['words']:
            count+=1
            if count>2000:raise ValueError('识别词数超过上限')
            start,end=number(w.get('start')),number(w.get('end'));text=w.get('text');probability=number(w.get('probability'))
            if not isinstance(text,str) or len(text)>120 or not 0<=probability<=1 or not 0<=start<=end<=duration+.1:raise ValueError('识别词无效')
            end=min(end,round(duration,3))
            if end-start<.02 or not re.search(r'[^\W_]',text,re.UNICODE):bad+=1;continue
            if words and start<words[-1]['end']-.02:raise ValueError('识别词时间重叠')
            item=dict(id='w'+str(len(words)),start=start,end=end,text=text,probability=probability)
            words.append(item);timed.append(item)
        if timed:segments.append({'id':'s'+str(len(segments)),'start':timed[0]['start'],'end':timed[-1]['end'],
                                 'text':''.join(w['text'] for w in timed).strip(),'words':[w['id'] for w in timed]})
    if count and bad/count>.2:raise ValueError('识别时间或文字质量不足，请人工校对音频')
    language=raw.get('language');probability=number(raw.get('language_probability'))
    if not isinstance(language,str) or not re.fullmatch('[a-z]{2,3}',language) or not 0<=probability<=1:raise ValueError('识别语言无效')
    return dict(language=language,language_probability=probability,segments=segments,words=words,
                low_confidence=sum(w['probability']<.5 for w in words),review='pending',training_eligible=False)


def transcribe_source(project,sid,sha,language):
    path=source_path(project,sid);meta=describe(path)
    if meta['sha256']!=sha:raise ValueError('源素材已变化')
    if not meta['has_audio']:raise ValueError('素材没有音轨')
    with tempfile.TemporaryDirectory(prefix='visualagent-speech-') as directory:
        wav=Path(directory)/'audio.wav'
        subprocess.run([os.getenv('CREATIVE_FFMPEG',FFMPEG),'-v','error','-nostdin','-protocol_whitelist','file,pipe',
                        '-i',str(path),'-map','0:a:0','-t','120','-vn','-ar','16000','-ac','1',str(wav)],
                       capture_output=True,check=True,timeout=45)
        raw=creative_speech.transcribe(wav,language)
    result=normalize_transcript(raw,meta['duration'])
    if describe(path)['sha256']!=sha:raise ValueError('分析期间源素材已变化')
    result['sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result


def evidence_for(project,spec):
    """Only completed observations tied to the exact current media hash reach Agent."""
    evidence={}
    for job in project.get('edit_transcriptions',{}).values():
        sid=job['source']
        if job['state']=='completed' and spec['sources'].get(sid)==job['source_sha256']:
            evidence[sid]={'model':job['model'],'request_id':job['id'],'review':job['result']['review'],
                           'segments':job['result']['segments'],'words':job['result']['words']}
    return evidence


def speech_findings(spec,evidence):
    findings=[]
    for i,(c,timing) in enumerate(zip(spec['clips'],schedule(spec['clips']))):
        words=evidence.get(c['source'],{}).get('words',[])
        for edge in ('start','end'):
            hit=next((w for w in words if w['start']+.025<c[edge]<w['end']-.025),None)
            if hit:findings.append(dict(kind='word_cut',clip=i,source=c['source'],time=c[edge],text=hit['text'].strip()))
        if timing['outgoing']:
            next_clip=spec['clips'][i+1];other=evidence.get(next_clip['source'],{}).get('words',[])
            if any(w['end']>c['end']-timing['outgoing'] and w['start']<c['end'] for w in words) and any(w['end']>next_clip['start'] and w['start']<next_clip['start']+timing['outgoing'] for w in other):
                findings.append(dict(kind='speech_overlap',clip=i,source=c['source'],time=c['end'],text='转场区间两段都有识别口播'))
    return findings[:64]


def caption_plan(project,spec,catalog):
    clean=validate_edit(spec,catalog=catalog);evidence=evidence_for(project,clean)
    if not evidence:raise ValueError('请先识别时间轴所用素材的口播')
    generated=[];omitted=0;upgraded=[]
    for c,timing in zip(clean['clips'],schedule(clean['clips'])):
        obs=evidence.get(c['source'])
        if not obs:continue
        by_id={w['id']:w for w in obs['words']}
        for segment in obs['segments']:
            inside=[]
            for wid in segment['words']:
                w=by_id[wid]
                if w['end']<=c['start'] or w['start']>=c['end']:continue
                if w['start']<c['start'] or w['end']>c['end']:omitted+=1;continue
                inside.append(w)
            groups=[];group=[]
            for word in inside:
                if group and (word['end']-group[0]['start']>3.5 or len(''.join(w['text'] for w in group))+len(word['text'])>42):groups.append(group);group=[]
                group.append(word)
            if group:groups.append(group)
            for group in groups:
                start=round(timing['at']+group[0]['start']-c['start'],3);end=round(timing['at']+group[-1]['end']-c['start'],3)
                if end-start<.2:omitted+=len(group);continue
                text=''.join(w['text'] for w in group).strip()
                existing=clean['captions']+generated
                match=next((v for v in existing if v['start']==start and v['end']==end and v['text']==text),None)
                if match is not None and match.get('words'):continue
                tracks=sorted(range(3),key=lambda tr:not clean['caption_visibility'][tr])
                track=next((tr for tr in tracks if not any(v['track']==tr and start<v['end'] and end>v['start'] for v in existing)),None)
                if track is None and match is None:raise ValueError('现有三层字幕在口播时段均被占用，请先整理字幕')
                words=[]
                for w in group:
                    local_start=round(w['start']-group[0]['start'],3)
                    # ASR permits 20 ms rounding overlap; retain the prior word's end.
                    if words:local_start=max(local_start,words[-1]['end'])
                    words.append(dict(text=w['text'],start=local_start,end=round(w['end']-group[0]['start'],3)))
                words[0]['text']=words[0]['text'].lstrip();words[-1]['text']=words[-1]['text'].rstrip()
                if match is not None:
                    match.update(words=words,word_highlight=True)
                    upgraded.append(clean['captions'].index(match));continue
                generated.append(dict(start=start,end=end,text=text,track=track,words=words,word_highlight=True,appearance={'preset':'plain','size':'medium','motion':'none'}))
    if not generated and not upgraded:raise ValueError('没有可加入的完整口播字幕，可能已加入或切点截断了识别词')
    first_index=min(upgraded) if upgraded else len(clean['captions'])
    clean['captions']+=generated
    return {'spec':validate_edit(clean,catalog=catalog),'added':len(generated),'upgraded':len(upgraded),'first_index':first_index,'omitted_words':omitted,
            'findings':speech_findings(clean,evidence),'review':'pending'}
