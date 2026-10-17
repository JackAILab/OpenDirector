#!/usr/bin/env python3
"""Validate a blinded plan-review export without revealing condition mappings."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest

VIOLATIONS = {'有', '无', '无法判断'}
TIMELINE = {'是', '否', '无法判断'}
SPECIFICITY = {'通用氛围', '清楚的商品动作', '有合理关系迁移'}


def validate(packet_path: Path, review_path: Path, require_complete=False):
    packet = json.loads(packet_path.read_text())
    review = json.loads(review_path.read_text())
    if packet.get('schema') != 'visualagent.blind-plan-review.v1':
        raise ValueError('invalid_packet_schema')
    if review.get('schema') != 'visualagent.human-plan-review-draft.v1':
        raise ValueError('invalid_review_schema')
    if review.get('packet_sha256') != digest(packet):
        raise ValueError('packet_digest_mismatch')
    if review.get('training_eligible') is not False:
        raise ValueError('training_must_remain_ineligible')
    if require_complete and review.get('review_status') != 'complete':
        raise ValueError('review_not_complete')
    if review.get('review_status') not in {'draft', 'complete'}:
        raise ValueError('invalid_review_status')
    plans = packet.get('plans')
    if not isinstance(plans, list) or not plans:
        raise ValueError('empty_packet')
    labels = [row.get('label') for row in plans]
    if any(not isinstance(label, str) or not label for label in labels) or len(set(labels)) != len(labels):
        raise ValueError('invalid_plan_labels')
    ratings = review.get('ratings')
    if not isinstance(ratings, dict):
        raise ValueError('invalid_ratings')
    expected = {f'{label}_{field}' for label in labels for field in
                ('violation', 'utility', 'timeline_ready', 'creative_specificity', 'evidence')}
    if set(ratings) != expected:
        raise ValueError('rating_keys_mismatch')
    normalized = {}
    for label in labels:
        violation = ratings[f'{label}_violation']
        if violation not in VIOLATIONS:
            raise ValueError(f'{label}_invalid_violation')
        raw_utility = ratings[f'{label}_utility']
        try:
            utility = int(raw_utility)
        except (TypeError, ValueError):
            raise ValueError(f'{label}_invalid_utility')
        if utility < 1 or utility > 5:
            raise ValueError(f'{label}_utility_out_of_range')
        timeline = ratings[f'{label}_timeline_ready']
        if timeline not in TIMELINE:
            raise ValueError(f'{label}_invalid_timeline')
        specificity = ratings[f'{label}_creative_specificity']
        if specificity not in SPECIFICITY:
            raise ValueError(f'{label}_invalid_specificity')
        evidence = ratings[f'{label}_evidence']
        if not isinstance(evidence, str) or len(evidence.strip()) < 8:
            raise ValueError(f'{label}_evidence_too_short')
        normalized[label] = {'violation': violation, 'utility': utility,
                             'timeline_ready': timeline,
                             'creative_specificity': specificity,
                             'evidence': evidence.strip()}
    return {'schema': 'visualagent.validated-plan-review.v1',
            'packet_sha256': digest(packet), 'review_status': review['review_status'],
            'training_eligible': False, 'ratings': normalized}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    result = validate(args.packet, args.review, args.require_complete)
    print(json.dumps({'review_status': result['review_status'],
                      'plan_count': len(result['ratings']),
                      'packet_sha256': result['packet_sha256']}, ensure_ascii=False))
