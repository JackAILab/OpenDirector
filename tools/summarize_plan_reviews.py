#!/usr/bin/env python3
"""Aggregate validated blinded plan reviews without exposing mappings or evidence text."""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from tools.validate_plan_review import validate


def summarize(pairs, require_complete=True):
    packet_count = 0
    plan_count = 0
    seen_reviews = set()
    complete_records = 0
    violations = Counter()
    timelines = Counter()
    specificities = Counter()
    utilities = []
    packet_hashes = []
    errors = []
    for packet_path, review_path in pairs:
        try:
            result = validate(packet_path, review_path, require_complete=require_complete)
            review_hash = digest(json.loads(review_path.read_text()))
            if review_hash in seen_reviews:
                errors.append({'packet': packet_path.name, 'error': 'duplicate_review'})
                continue
            seen_reviews.add(review_hash)
            complete_records += result['review_status'] == 'complete'
            packet_count += 1
            packet_hashes.append(result['packet_sha256'])
            ratings = result['ratings']
            plan_count += len(ratings)
            for row in ratings.values():
                violations[row['violation']] += 1
                timelines[row['timeline_ready']] += 1
                specificities[row['creative_specificity']] += 1
                utilities.append(row['utility'])
        except Exception as exc:
            errors.append({'packet': packet_path.name, 'error': type(exc).__name__})
    output = {
        'schema': 'visualagent.plan-review-aggregate.v2',
        'packet_count': len(set(packet_hashes)),
        'review_record_count': packet_count,
        'validated_complete_records': complete_records,
        'plan_count': plan_count,
        'review_status': 'complete' if packet_count and not errors and require_complete else ('partial' if packet_count else 'pending'),
        'violations': dict(sorted(violations.items())),
        'timeline_ready': dict(sorted(timelines.items())),
        'creative_specificity': dict(sorted(specificities.items())),
        'utility': {'n': len(utilities), 'mean': round(sum(utilities) / len(utilities), 4) if utilities else None,
                    'min': min(utilities) if utilities else None, 'max': max(utilities) if utilities else None},
        'packet_sha256': sorted(set(packet_hashes)),
        'errors': errors,
        'independent_review_completed': 0,
        'independence_status': 'not_verified',
        'training_eligible': False,
    }
    output['aggregate_sha256'] = digest({k: v for k, v in output.items() if k != 'aggregate_sha256'})
    return output


def parse_pair(value):
    packet, review = value.split('=', 1)
    return Path(packet), Path(review)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair', action='append', type=parse_pair, required=True,
                   metavar='PACKET=REVIEW')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--allow-draft', action='store_true')
    args = p.parse_args()
    result = summarize(args.pair, require_complete=not args.allow_draft)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('packet_count', 'plan_count', 'review_status', 'errors', 'training_eligible')}, ensure_ascii=False))
