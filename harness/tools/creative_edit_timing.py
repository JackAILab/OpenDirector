"""Edit clock contract shared by validation, preview and deterministic export."""
import html
import json
import math


def transition_duration(clip):
    transition = clip.get('transition') or {}
    return transition.get('duration', 0) if transition.get('kind') in ('dissolve', 'fade_black') else 0


def schedule(clips):
    cursor = 0
    result = []
    for i, clip in enumerate(clips):
        length = round(clip['end'] - clip['start'], 3)
        result.append(dict(index=i, at=round(cursor, 3), length=length,
                           incoming=transition_duration(clips[i-1]) if i else 0,
                           outgoing=transition_duration(clip)))
        cursor += length - transition_duration(clip)
    return result


def validate_transitions(clips):
    for i, clip in enumerate(clips):
        value = clip.get('transition', {'kind': 'cut', 'duration': 0})
        if not isinstance(value, dict) or value.get('kind') not in ('cut', 'dissolve', 'fade_black'):
            raise ValueError('转场请选择直接切换、叠化或淡黑')
        duration = value.get('duration', 0)
        if type(duration) not in (int, float) or not math.isfinite(duration):
            raise ValueError('转场时长必须是有限数值')
        duration = round(duration, 3)
        if value['kind'] == 'cut':
            if duration != 0: raise ValueError('直接切换的转场时长应为 0')
        else:
            if i == len(clips)-1: raise ValueError('最后一个片段没有后续转场')
            limit = min(2, (clip['end']-clip['start'])/2, (clips[i+1]['end']-clips[i+1]['start'])/2)
            if not .05 <= duration <= limit + .00001:
                raise ValueError('转场为 0.05–2 秒，且不能超过任一相邻片段时长的一半')
        clip['transition'] = dict(kind=value['kind'], duration=duration)


def automation(length, gain, fade_in=0, fade_out=0):
    if not fade_in and not fade_out: return ''
    points = [{'t': 0, 'v': 0 if fade_in else gain}]
    if fade_in: points.append({'t': fade_in, 'v': gain})
    if length-fade_out > points[-1]['t']: points.append({'t': round(length-fade_out, 3), 'v': gain})
    if fade_out: points.append({'t': length, 'v': 0})
    value = {'version': 1, 'lanes': [{'target': 'volume', 'points': points}]}
    return ' data-automation="' + html.escape(json.dumps(value), quote=True) + '"'


def visual_tweens(clips, timings):
    """Incoming dissolve over opaque outgoing picture avoids an unintended black dip."""
    result = []
    for i, timing in enumerate(timings):
        target = f'#visual-{i}'
        incoming = timing['incoming']
        if incoming:
            black = clips[i-1]['transition']['kind'] == 'fade_black'
            start = timing['at'] + (incoming/2 if black else 0)
            length = incoming/2 if black else incoming
            result.append(f'tl.set("{target}",{{opacity:0}},0).to("{target}",{{opacity:1,duration:{length},ease:"none"}},{start});')
        if timing['outgoing'] and clips[i]['transition']['kind'] == 'fade_black':
            start = timing['at'] + timing['length'] - timing['outgoing']
            result.append(f'tl.to("{target}",{{opacity:0,duration:{timing["outgoing"]/2},ease:"none"}},{start});')
    return ''.join(result)
