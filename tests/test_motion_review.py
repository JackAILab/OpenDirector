import pytest

from harness.learning.motion_review import build_motion_review


def test_motion_review_is_bounded_and_non_training():
    result = build_motion_review(
        item='abc123',
        media_sha256='a' * 64,
        analysis_version=1,
        result={
            'product_continuity': 'clear',
            'causal_motion': 'clear',
            'evidence_windows': ['0-5s product enters frame'],
            'provider_payload': {'secret': 'must not be copied'},
        },
    )
    assert result['schema'] == 'visualagent.ad-motion-review.v1'
    assert result['product_continuity'] == 'clear'
    assert 'provider_payload' not in result
    assert result['training_eligible'] is False
    assert len(result['review_sha256']) == 64


def test_motion_review_requires_media_binding():
    with pytest.raises(ValueError):
        build_motion_review(item='abc', media_sha256='bad', analysis_version=1, result={})
