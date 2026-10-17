import json
from pathlib import Path

import pytest

from harness.library import backup_progress as progress


IDENTITY = '20261014T220000Z-1234abcd'


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv('AD_LIBRARY_PROGRESS_ROOT', str(tmp_path / 'receipts'))
    monkeypatch.setattr(progress.time, 'time', lambda: 1000)
    event = {'snapshot': IDENTITY, 'state': 'preparing', 'phase': 'learning_evidence',
             'processed_analysis_versions': 2, 'total_analysis_versions': 3,
             'copied_learning_files': 27, 'copied_learning_bytes': 4096}
    return tmp_path / 'library', event


def test_progress_is_private_bounded_and_bound_to_library_and_current_state(fixture):
    root, event = fixture
    progress.write_progress(root, {**event, 'private_note': 'must not escape',
                                   'credential': 'not-a-real-secret', 'path': '/private/source'})
    path = progress._path(root, IDENTITY)
    assert path.stat().st_mode & 0o777 == 0o600
    assert 'must not escape' not in path.read_text() and '/private/source' not in path.read_text()
    result = progress.read_progress(root, IDENTITY, 'preparing')
    assert result['processed_analysis_versions'] == 2
    assert result['copied_learning_files'] == 27
    assert result['stale'] is False
    assert progress.read_progress(root, IDENTITY, 'preparing', now=1121)['stale'] is True
    assert progress.read_progress(root.parent / 'another-library', IDENTITY, 'preparing') is None
    for state in ('uploading', 'verifying', 'verified', 'failed', 'interrupted'):
        assert progress.read_progress(root, IDENTITY, state) is None


def test_verification_replaces_preparation_without_claiming_final_success(fixture):
    root, event = fixture
    progress.write_progress(root, event)
    progress.write_progress(root, {'snapshot': IDENTITY, 'state': 'verifying',
                                  'verified_files': 4, 'total_files': 4,
                                  'verified_learning_files': 16, 'total_learning_files': 20})
    assert progress.read_progress(root, IDENTITY, 'preparing') is None
    result = progress.read_progress(root, IDENTITY, 'verifying')
    assert result['verified_files'] == 4 and result['verified_learning_files'] == 16
    assert 'copied_learning_files' not in result and 'phase' not in result
    assert progress.read_progress(root, IDENTITY, 'verified') is None


@pytest.mark.parametrize('change', [
    {'processed_analysis_versions': 4}, {'processed_analysis_versions': True},
    {'copied_learning_files': -1}, {'copied_learning_bytes': 2**53},
    {'phase': '/private/path'}, {'snapshot': '../elsewhere'}, {'state': 'verified'},
])
def test_invalid_measurement_cannot_replace_last_valid_receipt(fixture, change):
    root, event = fixture
    progress.write_progress(root, event)
    before = progress._path(root, IDENTITY).read_bytes()
    progress.write_progress(root, {**event, **change})
    assert progress._path(root, IDENTITY).read_bytes() == before


@pytest.mark.parametrize('payload', [
    b'{', b'[]', b'x' * 8193,
    json.dumps({'state': 'preparing', 'phase': 'metadata', 'observed_at': 1031}).encode(),
    json.dumps({'state': 'preparing', 'phase': 'metadata', 'observed_at': float('nan')}).encode(),
    json.dumps({'state': 'preparing', 'phase': 'metadata', 'observed_at': 1000,
                'processed_analysis_versions': 1}).encode(),
])
def test_malformed_receipt_does_not_break_status(fixture, payload):
    root, event = fixture
    progress.write_progress(root, event)
    progress._path(root, IDENTITY).write_bytes(payload)
    assert progress.read_progress(root, IDENTITY, 'preparing') is None


def test_failed_atomic_publish_keeps_last_receipt_and_removes_partial(fixture, monkeypatch):
    root, event = fixture
    progress.write_progress(root, event)
    before = progress._path(root, IDENTITY).read_bytes()
    def fail(*args):
        raise OSError('private storage error')
    monkeypatch.setattr(Path, 'replace', fail)
    progress.write_progress(root, {**event, 'processed_analysis_versions': 3})
    assert progress._path(root, IDENTITY).read_bytes() == before
    assert not list(progress._path(root, IDENTITY).parent.glob('*.part'))
