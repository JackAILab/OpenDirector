"""Bounded owner-facing review packet for an edited film.

This is a deterministic checklist. It never calls a provider, labels a film
semantically good, or grants training eligibility.
"""
import hashlib
import json
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_timing import schedule


def _status(ok, detail):
    return {'status': 'passed' if ok else 'needs_check', 'detail': detail}


def _window(start, end, reason):
    return {'start': round(max(0, start), 3), 'end': round(max(start, end), 3), 'reason': reason}


def _content_tasks(clean, timings):
    duration = clean['duration']
    anchors = sorted({0, round(duration / 2, 3), round(max(0, duration - min(.5, duration)), 3)})
    tasks = [
        {'id': 'product_fidelity', 'label': '商品外观与一致性', 'status': 'pending',
         'instruction': '对照商品参考，核对外观、细节、颜色和跨片段身份是否一致。',
         'windows': [_window(at, min(duration, at + min(.8, duration - at)), '首段/中段/末段抽查') for at in anchors]},
        {'id': 'claim_accuracy', 'label': '卖点与事实准确性', 'status': 'pending',
         'instruction': '逐条对照商品资料，核对字幕、口播和画面中的可验证主张。',
         'windows': [_window(c['start'], c['end'], '字幕或口播落点') for c in clean['captions'][:12]] or
                    [_window(0, duration, '全片事实核对') ]},
        {'id': 'motion_continuity', 'label': '画面动作与衔接', 'status': 'pending',
         'instruction': '回放每个片段边界，核对动作因果、商品位置、遮挡和转场是否连续。',
         'windows': [_window(t['at'], min(duration, t['at'] + t['length']), '片段与转场边界') for t in timings[:12]]},
        {'id': 'audio_semantics', 'label': '旁白、音乐与音效', 'status': 'pending',
         'instruction': '完整听音，核对语言、口播内容、音乐/音效、响度和字幕同步；不能由静帧推断。',
         'windows': [_window(0, duration, '完整音轨') ]},
    ]
    return tasks


def build_review(spec, catalog, aspect):
    clean = validate_edit(spec, catalog=catalog)
    timings = schedule(clean['clips'])
    used = [catalog[c['source']] for c in clean['clips']]
    expected_ratio = {'16:9': 16 / 9, '9:16': 9 / 16, '1:1': 1}.get(aspect, 16 / 9)
    ratios = [m['width'] / m['height'] for m in used if m.get('width') and m.get('height')]
    ratio_ok = all(abs(r - expected_ratio) / expected_ratio <= .08 for r in ratios) if ratios else False
    source_ok = all(clean['sources'].get(c['source']) == catalog[c['source']]['sha256'] for c in clean['clips'])
    has_audio = any(catalog[c['source']].get('has_audio') and clean['volume'] > 0 and c['gain'] > 0 and not c['muted'] for c in clean['clips'])
    has_audio = has_audio or any(c['gain'] > 0 and not c['muted'] for c in clean['audio'])
    words_ok = all(not c.get('words') or c['words'][-1]['end'] <= c['end'] - c['start'] + .001 for c in clean['captions'])
    return {
        'schema': 'visualagent.edit-review.v1', 'revision': None,
        'document_sha256': hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'duration': clean['duration'], 'aspect': aspect,
        'technical': {
            'source_integrity': _status(source_ok, '所有画面片段仍绑定当前素材摘要。' if source_ok else '有素材摘要变化，需要重新加入素材。'),
            'canvas_ratio': _status(ratio_ok, '素材画幅与项目画幅在容差内。' if ratio_ok else '素材画幅需要人工确认或重新构图。'),
            'audio_track': _status(has_audio, '存在可听原声或独立音轨。' if has_audio else '当前剪辑没有可用音轨。'),
            'caption_timing': _status(words_ok, '字幕和逐词时间位于成片范围内。' if words_ok else '有逐词时间超出字幕窗口。'),
            'timeline': _status(bool(timings) and abs(timings[-1]['at'] + timings[-1]['length'] - clean['duration']) < .001,
                                f"{len(clean['clips'])} 段画面，时长 {clean['duration']:.2f} 秒。"),
        },
        'content': {
            'product_fidelity': {'status': 'pending', 'detail': '需要完整观看并核对商品外观、细节和连续性。'},
            'claim_accuracy': {'status': 'pending', 'detail': '需要对照商品资料核对口播、字幕和画面事实。'},
            'motion_continuity': {'status': 'pending', 'detail': '需要完整观看动作、镜头衔接和转场。'},
            'audio_semantics': {'status': 'pending', 'detail': '需要完整听音，核对口播、音乐、音效和字幕同步。'},
        },
        'content_tasks': _content_tasks(clean, timings),
        'human': {'full_video_watched': False, 'audio_listened': False, 'product_facts_checked': False},
        'decision': 'pending', 'semantic': 'pending', 'training_eligible': False,
    }
