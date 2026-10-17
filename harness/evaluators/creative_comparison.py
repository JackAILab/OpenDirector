"""Compare frozen video reviews, never infer creative quality from a render receipt.

This evaluator consumes review observations. It does not invoke a provider,
perform visual judging, grant training approval, or persist reviewer identities.
"""
from __future__ import annotations

import math
import re

AXES = {'product': 30, 'action': 25, 'speech': 20, 'continuity': 15, 'editing': 10}
CRITICAL = ('product', 'action', 'speech')
HEX = re.compile(r'[a-f0-9]{64}')


def _digest(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError('Expected a frozen content SHA256')
    return value


def _contract(case):
    if not isinstance(case, dict):
        raise ValueError('Invalid input contract')
    duration = case.get('duration')
    if type(duration) not in (float, int) or not math.isfinite(duration) or not 1 <= duration <= 120:
        raise ValueError('Invalid target duration')
    if case.get('aspect') not in ('9:16', '16:9', '1:1'):
        raise ValueError('Invalid target aspect')
    refs = case.get('reference_sha256')
    if not isinstance(refs, list) or not refs or any(not isinstance(v, str) for v in refs) or len(refs) != len(set(refs)):
        raise ValueError('Expected distinct frozen references')
    return (_digest(case.get('brief_sha256')), tuple(sorted(_digest(v) for v in refs)), duration, case['aspect'])


def _side(side):
    if not isinstance(side, dict):
        raise ValueError('Invalid comparison side')
    if side.get('state') == 'missing':
        return {'state': 'missing', 'score': None, 'review_ready': False, 'failures': []}
    if side.get('state') not in ('completed', 'failed'):
        raise ValueError('Invalid production state')
    contract = _contract(side.get('contract', {}))
    if side['state'] == 'failed':
        return {'state': 'failed', 'score': None, 'review_ready': False, 'failures': ['production'], 'contract': contract}
    artifact = _digest(side.get('artifact_sha256'))
    model = side.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', model):
        raise ValueError('Invalid model identifier')
    failures = [] if side.get('technical') == 'passed' else ['technical']
    review = side.get('review')
    result = {'state': 'completed', 'score': None, 'review_ready': False,
              'failures': failures, 'contract': contract, 'model': model}
    if review is None:
        return result
    if not isinstance(review, dict):
        raise ValueError('Invalid review observation')
    if _digest(review.get('artifact_sha256')) != artifact:
        raise ValueError('Review belongs to a different video version')
    ratings = review.get('ratings', {})
    if not isinstance(ratings, dict) or set(ratings) - set(AXES):
        raise ValueError('Unknown review dimension')
    total = 0
    for axis, row in ratings.items():
        if not isinstance(row, dict) or type(row.get('score')) is not int or not 0 <= row['score'] <= 4:
            raise ValueError('Review scores must be integers from 0 to 4')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 12:
            raise ValueError('Each score requires timestamped evidence')
        for item in evidence:
            window = item.get('window') if isinstance(item, dict) else None
            if not isinstance(window, list) or len(window) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in window):
                raise ValueError('Invalid evidence time window')
            if not 0 <= window[0] <= window[1] <= contract[2] + .15:
                raise ValueError('Evidence is outside the video duration')
            if not isinstance(item.get('note'), str) or not item['note'].strip() or len(item['note']) > 400:
                raise ValueError('Evidence must describe the observation')
        if axis in CRITICAL and row['score'] < 3:
            failures.append(axis)
        total += row['score'] / 4 * AXES[axis]
    # A partial/self-review remains useful for finding defects, but cannot win.
    ready = set(ratings) == set(AXES) and review.get('independent') is True
    result.update(review_ready=ready, score=round(total, 2) if ready else None)
    return result


def compare_videos(packet):
    """Report one paired case only. No aggregate superiority or approval claims."""
    if not isinstance(packet, dict) or packet.get('schema') != 'visualagent.video-comparison.v1':
        raise ValueError('Unknown comparison schema')
    mode = packet.get('mode', 'matched_model')
    if mode not in ('matched_model', 'end_to_end'):
        raise ValueError('Invalid comparison mode')
    a, b = _side(packet.get('a')), _side(packet.get('b'))
    reasons = []
    if any(s['state'] != 'completed' for s in (a, b)):
        reasons.append('both_completed_videos_required')
    elif a['contract'] != b['contract']:
        reasons.append('input_contract_mismatch')
    elif mode == 'matched_model' and a['model'] != b['model']:
        reasons.append('model_mismatch')
    if any(not s['review_ready'] for s in (a, b)):
        reasons.append('independent_reviews_required')
    if any('technical' in s['failures'] for s in (a, b)):
        reasons.append('technical_checks_required')
    winner = None
    if not reasons:
        passing = [name for name, s in (('a', a), ('b', b)) if not s['failures']]
        if len(passing) == 1:
            winner = passing[0]
        elif len(passing) == 2:
            winner = 'tie' if a['score'] == b['score'] else 'a' if a['score'] > b['score'] else 'b'
        else:
            reasons.append('both_need_changes')
    return {'schema': 'visualagent.video-comparison-result.v1', 'mode': mode,
            'a': {k: a[k] for k in ('state', 'score', 'review_ready', 'failures')},
            'b': {k: b[k] for k in ('state', 'score', 'review_ready', 'failures')},
            'winner': winner, 'reasons': reasons, 'scope': 'single_case',
            'training_eligible': False}
