"""Build private preference-pair candidates from exact-reviewed records."""
import itertools
import math
import re


def _public_record(record):
    """Keep only sanitized creative content and anonymous split bindings."""
    return {key: record[key] for key in
            ('sample_id', 'partition', 'family_id', 'plan', 'trajectory',
             'quality_mean_score', 'quality_min_score') if key in record}


def build_pairs(records, min_gap=0.5):
    if not isinstance(records, list):
        raise ValueError('Candidate records must be a list')
    if not isinstance(min_gap, (int, float)) or isinstance(min_gap, bool) or not math.isfinite(min_gap) or min_gap <= 0:
        raise ValueError('Invalid preference score gap')
    groups={}; seen={}; invalid_families=set()
    for record in records:
        if not isinstance(record, dict) or record.get('training_eligible') is not True:
            continue
        family=record.get('family_id');score=record.get('quality_mean_score')
        sample=record.get('sample_id');partition=record.get('partition')
        if (not isinstance(family, str) or not re.fullmatch(r'[a-f0-9]{64}', family)
                or not isinstance(sample, str) or not re.fullmatch(r'[a-f0-9]{64}', sample)
                or partition not in ('train','validation','test')
                or type(score) not in (int,float) or not math.isfinite(score) or not 1<=score<=5):
            continue
        if sample in seen:
            if record != seen[sample]:
                invalid_families.update((family,seen[sample]['family_id']))
            continue
        seen[sample]=record
        groups.setdefault(family, []).append(record)
    pairs=[]
    for family,items in groups.items():
        if family in invalid_families or len({item['partition'] for item in items}) != 1:
            continue
        for first,second in itertools.combinations(items, 2):
            left=float(first['quality_mean_score']);right=float(second['quality_mean_score'])
            if abs(left-right) < min_gap:continue
            winner,loser=(first,second) if left>right else (second,first)
            pairs.append({'family_id':family,'winner':_public_record(winner),'loser':_public_record(loser),
                          'score_gap':round(abs(left-right),2),'training_eligible':False,
                          'review_status':'pending_preference_review'})
    return sorted(pairs,key=lambda pair:(pair['family_id'],pair['winner']['sample_id'],pair['loser']['sample_id']))
