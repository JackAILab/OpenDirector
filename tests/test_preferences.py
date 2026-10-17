from harness.learning.preferences import build_pairs
import pytest


def record(sample, family, score, eligible=True):
    return {'sample_id': sample, 'family_id': family, 'quality_mean_score': score,
            'quality_min_score': 3, 'training_eligible': eligible,
            'partition': 'train', 'plan': {'brief': {'product': '产品'}},
            'creator_token': 'must-not-escape'}


def test_build_pairs_uses_same_family_and_score_gap():
    pairs=build_pairs([record('a'*64,'f'*64,4.8), record('b'*64,'f'*64,3.9),
                       record('c'*64,'e'*64,5.0), record('d'*64,'f'*64,4.6)], min_gap=.8)
    assert len(pairs)==1
    pair=pairs[0]
    assert pair['winner']['sample_id']=='a'*64 and pair['loser']['sample_id']=='b'*64
    assert pair['score_gap']==0.9 and pair['training_eligible'] is False
    assert 'creator_token' not in pair['winner']


def test_build_pairs_skips_ineligible_and_missing_scores():
    assert build_pairs([record('a'*64,'f'*64,4.8,False), record('b'*64,'f'*64,None)])==[]


@pytest.mark.parametrize('score',[float('nan'),float('inf'),float('-inf'),0,6,True])
def test_invalid_quality_cannot_form_preference(score):
    assert build_pairs([record('a'*64,'f'*64,score),record('b'*64,'f'*64,3)])==[]


def test_cross_partition_family_is_rejected():
    first=record('a'*64,'f'*64,5);second=record('b'*64,'f'*64,3)
    second['partition']='test'
    assert build_pairs([first,second])==[]


def test_duplicate_sample_never_becomes_its_own_preference():
    first=record('a'*64,'f'*64,5)
    assert len(build_pairs([first,dict(first),record('b'*64,'f'*64,3)]))==1
    assert build_pairs([first,record('a'*64,'f'*64,3)])==[]
