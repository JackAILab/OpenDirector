#!/usr/bin/env python3
"""Materialize a privacy-safe, descriptive grammar report from ad analyses.

This is an offline report for director retrieval and curriculum design.  It
does not score creative quality, export source text/media, or create a
training set.  Beat roles are bounded lexical observations over validated
analysis purposes; they are not recovered edits or the original director's
reasoning.
"""
import argparse
import json
import os
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

PHASES = {
    'hook': ('开场', '注意', '悬念', '预期', '疑问', '吸引', 'hook', 'attention', '建立'),
    'proof': ('证明', '结果', '动作', '功能', '任务', '展示', '压力', '完成', '改变', '因果', 'proof', 'task'),
    'reframe': ('反转', '揭示', '重释', '对照', '意外', '解释', 'reframe', 'reveal', '反差'),
    'reaction': ('反应', '情绪', '人物', '群体', '笑', '安心', '惊讶', 'reaction'),
    'close': ('品牌', '落版', '归因', '行动', '收束', 'logo', 'cta', 'close'),
}


def _role(text):
    text = str(text or '').lower()
    for name, terms in PHASES.items():
        if any(term.lower() in text for term in terms):
            return name
    return 'unknown'


def _latest(connection):
    latest = {}
    for row in connection.execute('SELECT item,version,data FROM analyses ORDER BY item,version DESC'):
        if row[0] not in latest:
            latest[row[0]] = json.loads(row[2])
    return latest


def _bucket(value):
    if value < 1 / 3:
        return 'early'
    if value < 2 / 3:
        return 'middle'
    return 'late'


def build(db_path):
    db_path = Path(db_path)
    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=5) as connection:
        latest = _latest(connection)

    role_counts = Counter()
    confidence_counts = Counter()
    phase_counts = Counter()
    phase_items = Counter()
    phase_by_role = defaultdict(Counter)
    phase_by_band = Counter()
    sequence_counts = Counter()
    audio_reviewed = 0
    motion_reviewed = 0
    durations = []
    for analysis in latest.values():
        role = analysis.get('media_role', 'unknown')
        role_counts[role] += 1
        confidence_counts[analysis.get('confidence', 'unknown')] += 1
        audio_reviewed += int(analysis.get('audio_semantics_reviewed') is True)
        motion_reviewed += int(analysis.get('full_motion_reviewed') is True)
        beats = [b for b in analysis.get('beats', []) if isinstance(b, dict)]
        end = max((float(b.get('end', 0)) for b in beats), default=0)
        if end > 0:
            durations.append(end)
        sequence = []
        item_phases = set()
        for beat in beats:
            try:
                start, finish = float(beat['start']), float(beat['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if not 0 <= start < finish or not end:
                continue
            phase = _role(beat.get('purpose'))
            band = _bucket(((start + finish) / 2) / end)
            phase_counts[phase] += 1
            item_phases.add(phase)
            phase_by_role[role][phase] += 1
            phase_by_band[(phase, band)] += 1
            if not sequence or sequence[-1] != phase:
                sequence.append(phase)
        if sequence:
            sequence_counts['→'.join(sequence[:5])] += 1
        for phase in item_phases:
            phase_items[phase] += 1

    total = len(latest)
    def rates(counter):
        return {key: {'count': value, 'rate': round(value / total, 4) if total else 0}
                for key, value in sorted(counter.items())}

    return {
        'schema': 'visualagent.ad-learning-grammar-report.v1',
        'analysis_count': total,
        'roles': dict(sorted(role_counts.items())),
        'confidence': dict(sorted(confidence_counts.items())),
        'beat_phase_coverage': {
            phase: {'beat_count': phase_counts.get(phase, 0),
                    'analysis_count': phase_items.get(phase, 0),
                    'analysis_rate': round(phase_items.get(phase, 0) / total, 4) if total else 0}
            for phase in (*PHASES.keys(), 'unknown')
        },
        'beat_phase_by_normalized_position': {
            phase: {band: phase_by_band[(phase, band)] for band in ('early', 'middle', 'late')}
            for phase in (*PHASES.keys(), 'unknown')
        },
        'beat_phase_by_role': {role: dict(sorted(counter.items()))
                               for role, counter in sorted(phase_by_role.items())},
        'common_phase_sequences': [
            {'sequence': sequence, 'count': count}
            for sequence, count in sequence_counts.most_common(20)
        ],
        'analysis_window_seconds': {
            'median': round(statistics.median(durations), 3) if durations else None,
            'p90': round(statistics.quantiles(durations, n=10)[8], 3) if len(durations) >= 10 else None,
        },
        'review_state': {
            'audio_semantics_reviewed': audio_reviewed,
            'full_motion_reviewed': motion_reviewed,
            'training_eligible': False,
        },
        'director_rules': [
            {'id': 'one_claim_one_task', 'rule': '先确认一个可证实主张，再设计一个观众能看见的任务或压力。'},
            {'id': 'hook_before_explanation', 'rule': '开场先给可读异常、目标或阻力，避免先堆抽象品牌形容词。'},
            {'id': 'proof_before_close', 'rule': '先让动作和结果成立，再做品牌归因与行动号召。'},
            {'id': 'reaction_is_causal', 'rule': '人物或环境反应必须跟随结果，不能用空泛表演替代证明。'},
            {'id': 'native_audio_contract', 'rule': '每个时段同时写画面、动作音、环境声、音乐和旁白；未听审前保持待确认。'},
            {'id': 'reference_is_mechanism_only', 'rule': '只迁移因果结构和提问方式，不复制品牌、人物、文案、构图、镜头序列或原音。'},
        ],
        'limitations': [
            '相位由分析用途文本的有限词汇归类，不是原片剪辑点或导演思维链。',
            '抽样画面和来源元数据不能证明完整运动、声音语义、转化效果或权利状态。',
            '覆盖率不是质量分数；要进入训练仍需独立内容、隐私、权利、授权和人工门禁。',
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError('Refusing to overwrite report')
    report = build(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'analysis_count': report['analysis_count'],
                      'training_eligible': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
