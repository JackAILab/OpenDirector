import copy
import pytest
from harness.evaluators.creative_comparison import AXES, compare_videos


def side(score=3):
    return {'state': 'completed', 'model': 'kling-video-v3_0_omni',
            'artifact_sha256': 'a'*64, 'technical': 'passed',
            'contract': {'brief_sha256': 'b'*64, 'reference_sha256': ['c'*64], 'duration': 15, 'aspect': '9:16'},
            'review': {'artifact_sha256': 'a'*64, 'independent': True,
                       'ratings': {k: {'score': score, 'evidence': [{'window': [5, 9], 'note': 'Observed full action'}]} for k in AXES}}}


def packet():
    return {'schema': 'visualagent.video-comparison.v1', 'mode': 'matched_model', 'a': side(4), 'b': side(3)}


def test_missing_video_or_self_review_cannot_win():
    p = packet();p['b'] = {'state': 'missing'}
    assert compare_videos(p)['winner'] is None
    p = packet();p['a']['review']['independent'] = False
    assert compare_videos(p)['a']['score'] is None
    assert compare_videos(p)['winner'] is None
    p = packet();p['a'].pop('review')
    assert compare_videos(p)['winner'] is None


def test_failed_critical_action_cannot_be_hidden_by_high_average():
    p = packet();p['a']['review']['ratings']['action']['score'] = 2
    r = compare_videos(p)
    assert r['a']['score'] > r['b']['score']
    assert r['winner'] == 'b' and r['a']['failures'] == ['action']
    assert r['training_eligible'] is False and r['scope'] == 'single_case'


def test_review_is_bound_to_media_and_evidence_is_required():
    p = packet();p['a']['review']['artifact_sha256'] = 'd'*64
    with pytest.raises(ValueError):compare_videos(p)
    for bad in ([], [{'window': [0, 16], 'note': 'outside'}], [{'window': [float('nan'), 1], 'note': 'invalid'}]):
        p = packet();p['a']['review']['ratings']['action']['evidence'] = bad
        with pytest.raises(ValueError):compare_videos(p)


def test_matching_contract_and_explicit_model_comparison():
    p = packet();p['b']['contract']['reference_sha256'] = ['e'*64]
    assert compare_videos(p)['reasons'] == ['input_contract_mismatch']
    p = packet();p['b']['model'] = 'kling-v3'
    assert compare_videos(p)['reasons'] == ['model_mismatch']
    p['mode'] = 'end_to_end'
    assert compare_videos(p)['winner'] == 'a'


def test_failures_and_partial_reviews_are_retained_without_score():
    p = packet();p['b']['state'] = 'failed'
    assert compare_videos(p)['b']['failures'] == ['production']
    p = packet();p['a']['review']['ratings'].pop('editing')
    assert compare_videos(p)['a']['score'] is None
    p = packet();p['b']['technical'] = 'pending'
    assert compare_videos(p)['winner'] is None
    p = packet();before = copy.deepcopy(p)
    assert compare_videos(p)['winner'] == 'a'
    assert p == before
