"""Bounded, deterministic ripple deletion over a validated edit document.

Uses integer milliseconds, matching EditTiming.rippleDelete in the browser.
Call validate_edit before and after when used by an Agent with a source catalog.
"""
from copy import deepcopy
import math
from harness.tools.creative_edit_timing import schedule


def ripple_delete(spec, index):
    clips = spec.get('clips', [])
    if type(index) is not int or not 0 <= index < len(clips) or not 2 <= len(clips) <= 32:
        raise ValueError('请选择画面片段，且至少保留一个画面')
    def ms(value):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('时间必须为有限数值')
        return math.floor(value * 1000 + .5)
    def sec(value): return value / 1000
    timing = schedule(clips)[index]
    left = ms(timing['at']) + ms(timing['incoming'])
    right = ms(timing['at']) + ms(timing['length']) - ms(timing['outgoing'])
    delta = right - left
    if delta < 0: raise ValueError('转场区间无效，请先核对相邻片段')
    def mapped(value): return value if value <= left else max(left, value - delta)
    result = deepcopy(spec)
    result['clips'].pop(index)
    if index: result['clips'][index-1]['transition'] = {'kind':'cut', 'duration':0}
    receipt = {'start':sec(left), 'end':sec(right), 'removed_seconds':sec(delta), 'cut_words':0,
               'removed_captions':0, 'removed_audio':0, 'removed_rhythm':0, 'split_audio':0,
               'cleared_transitions':int(timing['incoming'] > 0)+int(timing['outgoing'] > 0)}
    for kind in ('captions', 'rhythm'):
        output = []
        for item in spec.get(kind, []):
            start, end = ms(item['start']), ms(item['end'])
            new_start, new_end = mapped(start), mapped(end)
            row = deepcopy(item)
            row.update(start=sec(new_start), end=sec(new_end))
            if kind == 'captions' and item.get('words') and delta:
                words = []
                for word in item['words']:
                    a, b = start + ms(word['start']), start + ms(word['end'])
                    if b <= left or a >= right:
                        words.append(dict(word, start=sec(mapped(a)-new_start), end=sec(mapped(b)-new_start)))
                    elif a < left or b > right:
                        receipt['cut_words'] += 1
                row['words'] = words
                row['text'] = ''.join(w['text'] for w in words).strip()
            if new_end-new_start < 200 or (kind == 'captions' and item.get('words') and not row['words']):
                receipt['removed_'+kind] += 1
            else: output.append(row)
        result[kind] = output
    output = []
    for item in spec.get('audio', []):
        at, source_start, source_end = ms(item['at']), ms(item['start']), ms(item['end'])
        end = at + source_end-source_start
        fragments = [(at, end)] if not delta else [(at, min(end, left)), (max(at, right), end)]
        kept = []
        for a, b in fragments:
            if b-a < 200: continue
            row = deepcopy(item)
            length = b-a
            fade_in = min(ms(item.get('fade_in', 0)) if a == at else 10, length)
            fade_out = min(ms(item.get('fade_out', 0)) if b == end else 10, length-fade_in)
            row.update(at=sec(mapped(a)), start=sec(source_start+a-at), end=sec(source_start+b-at),
                       fade_in=sec(fade_in), fade_out=sec(fade_out))
            kept.append(row)
        receipt['removed_audio'] += int(not kept)
        receipt['split_audio'] += int(len(kept) > 1)
        output.extend(kept)
    if len(output) > 16: raise ValueError('分段后超过 16 条音频，请先整理音轨')
    result['audio'] = output
    timings = schedule(result['clips'])
    result['duration'] = round(timings[-1]['at']+timings[-1]['length'], 3)
    receipt['duration_after'] = result['duration']
    receipt['training_eligible'] = False
    return {'spec':result, 'receipt':receipt}


def ripple_delete_many(spec, indexes):
    """Delete several picture clips in one bounded, undoable edit.

    Indices refer to the original clip list. Processing from right to left
    keeps earlier indices stable while reusing the single-clip clock mapper.
    """
    values = sorted(set(indexes or []), reverse=True)
    clips = spec.get('clips', [])
    if not values or len(values) >= len(clips) or any(
        type(index) is not int or index < 0 or index >= len(clips) for index in values
    ):
        raise ValueError('请选择要删除的画面，且至少保留一个画面')
    current = deepcopy(spec)
    receipts = []
    for index in values:
        result = ripple_delete(current, index)
        current, receipt = result['spec'], result['receipt']
        receipts.append(receipt)
    receipt = {
        'start': min(item['start'] for item in receipts),
        'end': max(item['end'] for item in receipts),
        'removed_seconds': sum(item['removed_seconds'] for item in receipts),
        'cut_words': sum(item['cut_words'] for item in receipts),
        'removed_captions': sum(item['removed_captions'] for item in receipts),
        'removed_audio': sum(item['removed_audio'] for item in receipts),
        'removed_rhythm': sum(item['removed_rhythm'] for item in receipts),
        'split_audio': sum(item['split_audio'] for item in receipts),
        'cleared_transitions': sum(item['cleared_transitions'] for item in receipts),
        'duration_after': current['duration'],
        'training_eligible': False,
    }
    return {'spec': current, 'receipts': receipts, 'receipt': receipt}


def move_many(clips, indexes, direction):
    """Move a contiguous selected block one clip earlier or later."""
    values = sorted(set(indexes or []))
    if not values or any(type(index) is not int or index < 0 or index >= len(clips) for index in values):
        raise ValueError('请选择有效的画面片段和移动方向')
    if direction not in (-1, 1):
        raise ValueError('请选择有效的画面片段和移动方向')
    if any(right != left + 1 for left, right in zip(values, values[1:])):
        raise ValueError('批量移动需选择连续画面片段')
    start, length = values[0], len(values)
    if (direction < 0 and start == 0) or (direction > 0 and start + length == len(clips)):
        return {'clips': deepcopy(clips), 'indexes': values, 'moved': False}
    result = deepcopy(clips)
    block = result[start:start + length]
    del result[start:start + length]
    insert_at = start - 1 if direction < 0 else start + 1
    result[insert_at:insert_at] = block
    return {'clips': result, 'indexes': list(range(insert_at, insert_at + length)), 'moved': True}
