"""Fail closed on unsupported edits; this checks contracts, not editorial quality."""
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_observe import observation_metadata


def evaluate_edit_proposal(raw, original, catalog, observations):
    if not isinstance(raw, dict): raise ValueError('剪辑建议格式无效')
    spec = validate_edit(raw.get('spec'), catalog=catalog)
    if spec['volume'] != original['volume'] or spec['audio'] != original['audio']:
        raise ValueError('建议改变了受保护的音轨')
    if [c['text'] for c in spec['captions']] != [c['text'] for c in original['captions']]:
        raise ValueError('建议改变了字幕内容')
    if any(a.get(k)!=b.get(k) for a,b in zip(spec['captions'],original['captions']) for k in ('words','word_highlight')):
        raise ValueError('建议改变了用户的逐词校对或高亮设置')
    if spec['caption_visibility']!=original['caption_visibility'] or [c['appearance'] for c in spec['captions']]!=[c['appearance'] for c in original['captions']]:
        raise ValueError('建议改变了用户选择的字幕显示或样式')
    if any(spec['caption_visibility'][a['track']]!=original['caption_visibility'][b['track']] for a,b in zip(spec['captions'],original['captions'])):
        raise ValueError('建议把字幕移到了显示状态不同的轨道')
    for clip in spec['clips']:
        if not any(c['source']==clip['source'] and c['start']<=clip['start'] and c['end']>=clip['end'] and c['gain']==clip['gain'] and c.get('muted',False)==clip['muted'] for c in original['clips']):
            raise ValueError('建议超出已选素材时间窗或改变了音量/静音')
    summary, reasons = raw.get('summary'), raw.get('reasons')
    if not isinstance(summary,str) or not 1<=len(summary.strip())<=500: raise ValueError('建议摘要无效')
    if not isinstance(reasons,list) or not 1<=len(reasons)<=8: raise ValueError('建议依据无效')
    known = {f['id'] for f in observations};clean=[]
    for item in reasons:
        if not isinstance(item,dict): raise ValueError('建议依据无效')
        text, frames = item.get('text'), item.get('frames')
        if not isinstance(text,str) or not 1<=len(text.strip())<=240: raise ValueError('建议依据过长或为空')
        if not isinstance(frames,list) or len(frames)>24 or any(not isinstance(f,str) or f not in known for f in frames): raise ValueError('建议引用了未知采样')
        clean.append({'text':text.strip(),'frames':frames})
    return {'spec':spec,'summary':summary.strip(),'reasons':clean,
            'observations':[observation_metadata(f) for f in observations],
            'qa':{'contract':'passed','semantic':'pending','human':'pending','training_eligible':False}}
