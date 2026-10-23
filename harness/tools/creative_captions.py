"""Bounded caption presentation. No CSS, HTML, fonts or external assets as input."""
import math

DEFAULT_APPEARANCE = {'preset':'box','size':'medium','motion':'none'}
OPTIONS = {'preset':{'plain','box','accent'},'size':{'small','medium','large'},'motion':{'none','fade','rise'},'align':{'left','center','right'}}


def appearance(value=None):
    if value is None:return dict(DEFAULT_APPEARANCE)
    if not isinstance(value,dict) or set(value)-set(OPTIONS):raise ValueError('字幕样式字段无效')
    result=dict(DEFAULT_APPEARANCE,**value)
    if any(k in result and (not isinstance(result[k],str) or result[k] not in values) for k,values in OPTIONS.items()):
        raise ValueError('请选择支持的字幕样式、字号和入场方式')
    return result


def track_visibility(value=None):
    if value is None:return [True,True,True]
    if not isinstance(value,list) or len(value)!=3 or any(type(v) is not bool for v in value):
        raise ValueError('字幕轨道显示设置需为三个开关')
    return list(value)


def word_alignment(caption):
    """Word times are relative to the sentence, so moving it preserves cadence.

    These are editable draft timings, not a new speech observation or approval.
    Plain text is never assigned guessed word timestamps.
    """
    words=caption.get('words')
    highlight=caption.get('word_highlight',False)
    if type(highlight) is not bool:raise ValueError('逐词高亮需为开关')
    if words is None:
        if highlight:raise ValueError('请先从口播识别生成逐词时间')
        return {}
    if not isinstance(words,list) or not 1<=len(words)<=120:raise ValueError('每句需有 1–120 个识别词')
    clean=[];previous=0;length=round(caption['end']-caption['start'],3)
    for word in words:
        if not isinstance(word,dict):raise ValueError('逐词字幕格式无效')
        text=word.get('text');values=[word.get(k) for k in ('start','end')]
        if any(type(n) not in (int,float) or not math.isfinite(n) for n in values):raise ValueError('逐词时间必须是有限数值')
        start,end=(round(n,3) for n in values)
        if not isinstance(text,str) or not text.strip() or len(text)>120:raise ValueError('每个词需有文字')
        if not 0<=start<end<=length or start<previous or round(end-start,3)<.02:raise ValueError('逐词时间需按顺序位于句内、不重叠，至少 0.02 秒')
        clean.append(dict(text=text,start=start,end=end));previous=end
    if ''.join(w['text'] for w in clean).strip()!=caption['text'].strip():raise ValueError('逐词文字与整句不一致，请在逐词校对中修改')
    return {'words':clean,'word_highlight':highlight}
