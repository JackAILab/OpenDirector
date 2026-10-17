import fcntl
import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from harness.library import store
from tools import cache_ad_reference_media as media


def entry(name):
    return store.ingest({'source_url': 'https://example.org/' + name, 'title': name,
        'media_status': 'source_link', 'ad_type': 'ADFEST Film Lotus / VIRAL FILM',
        'creative_structure': {'public_video_url': 'https://adfest.d-energy.cn/adfest/works2026/F13_001.mp4'}})[0]


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'library')
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB', '1')
    old, target = entry('old pending reference'), entry('explicitly selected reference')
    return old, target


def test_exact_selection_never_falls_through_or_reads_all_source_payloads(library):
    old, target = library
    with store.connection() as db:
        queries = []; db.set_trace_callback(queries.append)
        assert [r['id'] for r in media.select_candidates(db, 12, only_item=target)] == [target]
        assert media.select_candidates(db, 12, only_item='f'*24) == []
        assert not any('SELECT id,ad_type FROM items' in q for q in queries)
        assert db.execute('SELECT COUNT(*) FROM media_jobs').fetchone()[0] == 0


def test_registered_assets_and_cooldown_are_not_bypassed(library):
    _, target = library
    with store.connection() as db:
        db.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'download_timeout',?)", (target, time.time()))
        assert media.select_candidates(db, 1, only_item=target) == []
        assert media.select_candidates(db, 1, True, only_item=target) == []
        db.execute("UPDATE media_jobs SET error_code='media_limit' WHERE item=?", (target,))
        assert [r['id'] for r in media.select_candidates(db, 1, True, only_item=target)] == [target]
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
            (target, 'assets/'+target+'/existing.mp4', 'a'*64, 100, 15, 1, 640, 360, 0))
        assert media.select_candidates(db, 1, True, only_item=target) == []


def test_active_media_worker_is_not_recovered_or_interrupted(library):
    _, target = library
    with store.connection() as db:
        db.execute("INSERT INTO media_jobs VALUES(?,'downloading',1,'',?)", (target, time.time()))
    with (store.ROOT / '.media.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert media.run(1, only_item=target) == {'state': 'already_running'}
    with store.connection() as db:
        assert db.execute('SELECT state FROM media_jobs WHERE item=?', (target,)).fetchone()[0] == 'downloading'


@pytest.mark.parametrize('identity', ['../private', 'a'*23, 'g'*24, 123, ''])
def test_invalid_identity_cannot_touch_storage(tmp_path, monkeypatch, identity):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'not-created')
    with pytest.raises(ValueError, match='invalid_reference_identity'):
        media.run(1, only_item=identity)
    assert not store.ROOT.exists()


def test_unknown_target_never_downloads_another_item(library, monkeypatch):
    monkeypatch.setattr(media.httpx, 'Client', lambda **kw: pytest.fail('No network call expected'))
    assert media.run(1, only_item='f'*24) == {'state': 'no_eligible_candidate', 'cached': 0, 'failed': 0}
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM media_jobs').fetchone()[0] == 0


def test_target_cache_runs_real_codec_pipeline_and_preserves_human_review(library, tmp_path, monkeypatch):
    if not Path(media.FFMPEG).is_file():
        pytest.skip('FFmpeg runtime unavailable')
    old, target = library
    fixture = tmp_path / 'fixture.mp4'
    subprocess.run([media.FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
        'color=c=blue:s=160x90:d=1', '-f', 'lavfi', '-i', 'sine=frequency=500:duration=1',
        '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(fixture)], check=True, capture_output=True)
    content = fixture.read_bytes(); calls = []
    store.review_item(target, 88, 0, 'selected', {'craft': 4}, ['user tag'], 'preserve my choice')
    original = httpx.Client
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=content)
    monkeypatch.setattr(media.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    assert media.run(1, only_item=target) == {'state': 'completed', 'cached': 1, 'failed': 0}
    with store.connection() as db:
        asset = db.execute('SELECT * FROM assets WHERE item=?', (target,)).fetchone()
        assert asset['audio'] == 1 and asset['duration'] >= 0.9
        assert hashlib.sha256((store.ROOT / asset['path']).read_bytes()).hexdigest() == asset['sha256']
        assert not db.execute('SELECT 1 FROM assets WHERE item=?', (old,)).fetchone()
        assert not db.execute('SELECT 1 FROM media_jobs WHERE item=?', (old,)).fetchone()
        assert tuple(db.execute('SELECT state,note FROM reviews WHERE item=?', (target,)).fetchone()) == ('selected', 'preserve my choice')
        assert json.loads(db.execute('SELECT data FROM items WHERE id=?', (target,)).fetchone()[0])['training_eligible'] is False
    assert media.run(1, only_item=target)['state'] == 'no_eligible_candidate'
    assert calls == ['/adfest/works2026/F13_001.mp4']


def test_target_cli_is_exclusive_and_preserves_batch_exit_behavior(monkeypatch):
    calls = []
    monkeypatch.setattr(media, 'run', lambda *a, **kw: calls.append((a, kw)) or {'state': 'partial'})
    for field in ('MAX_FILE', 'MIN_FREE', 'DOWNLOAD_TIMEOUT'):
        monkeypatch.setattr(media, field, getattr(media, field))
    with pytest.raises(SystemExit) as exc:
        media.main(['--item', 'a'*24, '--limit', '2'])
    assert exc.value.code == 2 and calls == []
    assert media.main(['--item', 'a'*24]) == 1
    assert calls[-1] == ((1, False), {'only_item': 'a'*24})
    assert media.main(['--limit', '8']) == 0
    assert calls[-1] == ((8, False), {})
