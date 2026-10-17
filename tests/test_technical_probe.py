from harness.library.technical_probe import summarize_probe
from harness.library.technical_probe import probe_file


def test_probe_summary_keeps_stream_facts_and_pending_semantics():
    result = summarize_probe({'format': {'duration': '15.5'}, 'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080, 'avg_frame_rate': '30/1'},
        {'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '44100', 'channels': 2},
    ]})
    assert result['duration_seconds'] == 15.5
    assert result['video']['frame_rate'] == 30.0
    assert result['audio']['present'] is True
    assert result['semantic_review'] == 'pending'
    assert result['training_eligible'] is False


def test_probe_summary_rejects_missing_streams():
    try:
        summarize_probe({})
    except ValueError as exc:
        assert 'streams' in str(exc)
    else:
        raise AssertionError('missing streams should fail closed')


def test_probe_rejects_wrong_media_hash_before_invoking_provider(tmp_path):
    media = tmp_path / 'media.mp4'
    media.write_bytes(b'changed media')
    result = probe_file(media, 'a' * 64)
    assert result['status'] == 'hash_mismatch'
    assert result['training_eligible'] is False
