"""Independent, bounded comparison of a locked 3D trajectory and provider metadata.

This evaluator only compares safe metadata projections.  It never reads raw
provider payloads or coordinates and never turns a metadata match into an
approval or training signal.
"""

from __future__ import annotations

import math


EVALUATOR_ID = 'trajectory_metadata_v1'


def _duration_match(expected, observed):
    if isinstance(expected, bool) or isinstance(observed, bool):
        return None
    if not isinstance(expected, (int, float)) or not isinstance(observed, (int, float)):
        return None
    if not math.isfinite(float(expected)) or not math.isfinite(float(observed)):
        return None
    return abs(float(expected) - float(observed)) <= 0.05


def evaluate_trajectory(expected_rows, observation):
    """Return a safe per-shot Observation for camera metadata.

    The result is deliberately advisory.  A provider can report matching
    hashes while the rendered pixels still diverge, so callers must keep a
    separate human replay gate.
    """
    expected_rows = [row for row in (expected_rows or []) if isinstance(row, dict)][:12]
    observed_rows = [row for row in ((observation or {}).get('shots', []) if isinstance(observation, dict) else [])
                     if isinstance(row, dict)][:12]
    expected = {str(row.get('shot_id'))[:48]: row for row in expected_rows if row.get('shot_id')}
    observed = {}
    for row in observed_rows:
        shot_id = str(row.get('shot_id') or '')[:48]
        if shot_id and shot_id not in observed:
            observed[shot_id] = row

    details = []
    matched_shots = 0
    comparable_shots = 0
    for row in expected_rows:
        shot_id = str(row.get('shot_id') or '')[:48]
        provider = observed.get(shot_id)
        if not provider:
            details.append({'shot_id': shot_id, 'status': 'not_observed', 'score': 0,
                            'matched_fields': 0, 'comparable_fields': 0,
                            'message': '未返回该镜头的结构化元数据。'})
            continue
        comparisons = []
        if row.get('path_sha256') and provider.get('path_sha256'):
            comparisons.append(('path_sha256', row['path_sha256'] == provider['path_sha256']))
        if isinstance(row.get('path_points'), int) and isinstance(provider.get('path_points'), int):
            comparisons.append(('path_points', row['path_points'] == provider['path_points']))
        if isinstance(row.get('path_closed'), bool) and isinstance(provider.get('path_closed'), bool):
            comparisons.append(('path_closed', row['path_closed'] == provider['path_closed']))
        if row.get('path_easing') and provider.get('path_easing'):
            comparisons.append(('path_easing', row['path_easing'] == provider['path_easing']))
        duration = _duration_match(row.get('duration'), provider.get('duration'))
        if duration is not None:
            comparisons.append(('duration', duration))
        comparable = len(comparisons)
        matched = sum(1 for _, result in comparisons if result)
        score = round(matched / comparable, 2) if comparable else 0
        comparable_shots += 1 if comparable else 0
        if comparable and matched == comparable:
            status = 'metadata_match'
            matched_shots += 1
        elif matched and score >= .5:
            status = 'partial_match'
        else:
            status = 'metadata_mismatch' if comparable else 'observed'
        details.append({'shot_id': shot_id, 'status': status, 'score': score,
                        'matched_fields': matched, 'comparable_fields': comparable,
                        'fields': [name for name, result in comparisons if not result],
                        'message': '元数据摘要对照完成，仍需人工回放。'})

    if not observed_rows:
        status = 'not_observed'
        message = '供应商尚未返回结构化 3D 轨迹元数据；请按镜头时码回放。'
    elif matched_shots == len(expected) and len(expected) and all(item['status'] == 'metadata_match' for item in details):
        status = 'metadata_match'
        message = '供应商摘要与当前 3D 轨迹锁一致；仍需人工回放确认画面和运镜。'
    elif any(item['status'] in ('metadata_match', 'partial_match') for item in details):
        status = 'partial_match'
        message = f'供应商摘要中 {matched_shots}/{comparable_shots or len(details)} 个镜头可比或匹配；仍需人工回放。'
    else:
        status = 'metadata_mismatch' if details else 'observed'
        message = '供应商摘要与当前 3D 轨迹锁存在差异；请人工回放后决定是否重拍。'

    extra = sorted(set(observed) - set(expected))[:8]
    return {
        'evaluator': EVALUATOR_ID,
        'version': 1,
        'status': status,
        'matched_shots': matched_shots,
        'comparable_shots': comparable_shots,
        'expected_shots': len(expected_rows),
        'observed_shots': len(observed_rows),
        'extra_shots': extra,
        'shots': details,
        'message': message,
        'requires_human_review': True,
        'training_eligible': False,
    }
