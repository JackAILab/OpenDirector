import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

import httpx
import pytest

from harness.library import store
from harness.tools import reference_media_recovery as recovery

FFMPEG = '/opt/visualstation/creative-runtime/bin/ffmpeg'
URL = 'https://bv-04.bubblevault.com/reference/mp4/720x480/film.mp4'


@pytest.fixture
def library(tmp_path, monkeypatch):
    if not Path(FFMPEG).is_file():pytest.skip('FFmpeg unavailable')
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'library')
    identity, _ = store.ingest({'source_url': 'https://example.org/reference', 'title': 'A reference',
        'media_status': 'source_link', 'creative_structure': {'public_video_url': URL}})
    folder = store.ROOT / 'assets' / identity
    folder.mkdir(parents=True)
    staging = folder / 'fixture.mp4'
    subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:d=1',
        '-f', 'lavfi', '-i', 'sine=frequency=600:duration=1', '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(staging)],
        check=True, capture_output=True)
    sha = hashlib.sha256(staging.read_bytes()).hexdigest()
    path = folder / (sha + '.mp4');staging.rename(path)
    subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-i', str(path), '-frames:v', '1', str(folder / 'poster.jpg')], check=True, capture_output=True)
    (folder / 'source.json').write_text(json.dumps({'media_url': URL}))
    with store.connection() as db:
        db.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'OperationalError',?)", (identity, time.time()))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **kw: pytest.fail('Recovery must not access the network'))
    return identity, path


def recover(identity, budget=1024**3):
    return recovery.recover_cached_media(identity, budget=budget)


def test_real_media_registration_is_atomic_and_preserves_identity_preferences_and_attempts(library, monkeypatch):
    identity, path = library
    store.review_item(identity, 23, 0, 'selected', {'craft': 4}, [], 'Human preference')
    with store.connection() as db:
        item_before = tuple(db.execute('SELECT * FROM items').fetchone())
        review_before = tuple(db.execute('SELECT * FROM reviews').fetchone())
    stamp = path.stat().st_mtime_ns
    result = recover(identity)
    assert result['state'] == 'completed' and result['recovered'] == 1
    assert result['network_downloads'] == result['new_video_files'] == 0
    with store.connection() as db:
        asset = db.execute('SELECT * FROM assets').fetchone()
        assert asset['audio'] == 1 and asset['duration'] >= .9 and asset['width'] == 160
        assert asset['sha256'] == path.stem
        assert tuple(db.execute('SELECT state,attempts,error_code FROM media_jobs').fetchone()) == ('completed', 2, '')
        assert tuple(db.execute('SELECT * FROM items').fetchone()) == item_before
        assert tuple(db.execute('SELECT * FROM reviews').fetchone()) == review_before
        assert db.execute('SELECT inserted FROM collection_runs').fetchone()[0] == 1
    monkeypatch.setattr(recovery, '_probe', lambda *a: pytest.fail('An existing asset must not be reprobed'))
    assert recover(identity)['state'] == 'already_registered'
    assert path.stat().st_mtime_ns == stamp


@pytest.mark.parametrize('fault', ['corrupt', 'source_mismatch', 'missing_poster', 'symlink', 'ambiguous'])
def test_bad_local_evidence_never_registers_or_changes_job(library, fault):
    identity, path = library
    if fault == 'corrupt':path.write_bytes(b'corrupt')
    elif fault == 'source_mismatch':(path.parent / 'source.json').write_text(json.dumps({'media_url': URL.replace('film', 'other')}))
    elif fault == 'missing_poster':(path.parent / 'poster.jpg').unlink()
    elif fault == 'symlink':
        outside = store.ROOT / 'outside.mp4';path.rename(outside);path.symlink_to(outside)
    elif fault == 'ambiguous':shutil.copyfile(path, path.parent / ('f'*64 + '.mp4'))
    assert recover(identity)['state'] == 'failed'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0
        assert tuple(db.execute('SELECT state,attempts FROM media_jobs').fetchone()) == ('failed', 2)
        assert db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0] == 0


def test_source_revision_changed_during_probe_is_rejected(library, monkeypatch):
    identity, path = library
    original = recovery._probe
    def change(path):
        result = original(path)
        with store.connection() as db:db.execute('UPDATE items SET revision=revision+1 WHERE id=?', (identity,))
        return result
    monkeypatch.setattr(recovery, '_probe', change)
    assert recover(identity)['state'] == 'failed'
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0


def test_receipt_failure_rolls_back_asset_and_job_changes(library):
    identity, path = library
    with store.connection() as db:
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON collection_runs BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    assert recover(identity)['state'] == 'failed'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0
        assert tuple(db.execute('SELECT state,error_code FROM media_jobs').fetchone()) == ('failed', 'OperationalError')


def test_existing_media_lock_is_respected(library, monkeypatch):
    identity, _ = library
    monkeypatch.setattr(recovery, '_probe', lambda *a: pytest.fail('Live worker must not be inspected'))
    with (store.ROOT / '.media.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert recover(identity)['state'] == 'already_running'


def test_only_database_failure_is_eligible_and_storage_limit_still_applies(library):
    identity, path = library
    assert recover(identity, path.stat().st_size - 1)['state'] == 'storage_limit'
    with store.connection() as db:db.execute("UPDATE media_jobs SET error_code='ReadTimeout'")
    assert recover(identity)['state'] == 'no_eligible_candidate'
    assert recover('f'*24)['state'] == 'no_eligible_candidate'


@pytest.mark.parametrize('identity,budget', [('../outside', 1), ('a'*24, 0), ('a'*24, True)])
def test_invalid_arguments_do_not_create_storage(tmp_path, monkeypatch, identity, budget):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'absent')
    with pytest.raises(ValueError):recovery.recover_cached_media(identity, budget=budget)
    assert not store.ROOT.exists()
