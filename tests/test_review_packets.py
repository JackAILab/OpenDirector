import pytest
from harness.library.review_packets import build_packets


def test_packets_are_bounded_and_keep_reviews_pending():
    q = {'schema': 'visualagent.ad-analysis-review-queue.v1', 'state': 'ready', 'total_pending': 2,
         'items': [
             {'item': 'a', 'media_sha256': 'a' * 64, 'analysis_version': 1, 'duration': 15,
              'audio_present': True, 'missing': ['audio_semantics', 'full_motion']},
             {'item': 'b', 'media_sha256': 'b' * 64, 'analysis_version': None,
              'duration': 10, 'audio_present': False, 'missing': ['analysis']},
         ]}
    out = build_packets(q, 2)
    assert out['schema'] == 'visualagent.ad-media-review-packets.v1'
    assert out['count'] == 2 and out['training_eligible'] is False
    assert len(out['items'][0]['audio_review']['checks']) == 5
    assert out['items'][1]['motion_review']['status'] == 'blocked_by_missing_analysis'
    assert 'private' not in str(out)


def test_packets_reject_invalid_queue_and_overwrite_limit():
    with pytest.raises(ValueError):
        build_packets({}, 1)
    with pytest.raises(ValueError):
        build_packets({'schema': 'visualagent.ad-analysis-review-queue.v1', 'items': []}, 0)


def test_semantic_packets_skip_items_without_structure_analysis():
    q = {'schema': 'visualagent.ad-analysis-review-queue.v1', 'state': 'ready', 'total_pending': 2,
         'items': [
             {'item': 'missing', 'media_sha256': 'a' * 64, 'analysis_version': None,
              'missing': ['analysis']},
             {'item': 'ready', 'media_sha256': 'b' * 64, 'analysis_version': 1,
              'missing': ['audio_semantics', 'full_motion']},
         ]}
    out = build_packets(q, 2, only_semantic=True)
    assert out['only_semantic'] is True
    assert [item['item'] for item in out['items']] == ['ready']
    assert all('analysis' not in item['missing'] for item in out['items'])
