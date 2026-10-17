import pytest
from harness.learning.audio_review import build_audio_review


def test_audio_review_is_bound_and_does_not_persist_transcript_or_payload():
    result = build_audio_review(
        item='item-1', media_sha256='a' * 64, analysis_version=1,
        result={'language': 'zh', 'speech': 'present', 'music': 'present',
                'sound_effects': 'present', 'sync_cues': ['纸张翻动'],
                'transcript': '原始转写不应落盘', 'raw_payload': {'secret': 'x'},
                'reviewer_model': 'local-asr-v1'})
    assert result['speech'] == 'present'
    assert 'transcript' not in result and 'raw_payload' not in result
    assert result['training_eligible'] is False
    assert len(result['review_sha256']) == 64


def test_audio_review_fails_closed_on_unbound_media():
    with pytest.raises(ValueError):
        build_audio_review(item='item-1', media_sha256='bad', analysis_version=1, result={})
