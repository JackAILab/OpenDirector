import hashlib
import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from harness.library import store
from harness.tools.reference_media_cache import PartialCache
from tools import cache_ad_reference_media as media


@pytest.fixture
def films(tmp_path, monkeypatch):
    if not Path(media.FFMPEG).is_file():
        pytest.skip('FFmpeg runtime unavailable')
    fixture = tmp_path / 'fixture.mp4'
    subprocess.run([media.FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
        'color=c=green:s=160x90:d=1', '-f', 'lavfi', '-i', 'sine=frequency=600:duration=1',
        '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(fixture)], check=True, capture_output=True)
    content = fixture.read_bytes()
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'library')
    monkeypatch.setattr(media, 'MAX_FILE', len(content) + 256)
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB', '1')
    identities = []
    for number in range(1, 4):
        identity, _ = store.ingest({'source_url': f'https://example.org/film-{number}',
            'title': f'Fixture film {number}', 'media_status': 'source_link',
            'creative_structure': {'public_video_url': f'https://adfest.d-energy.cn/adfest/works2026/F01_{number:03}.mp4'}})
        identities.append(identity)
    return identities, content


def install_transport(monkeypatch, respond):
    original = httpx.Client
    monkeypatch.setattr(media.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))


def test_fast_films_finish_while_first_download_waits_with_only_two_workers(films, monkeypatch):
    identities, content = films
    release_first, first_started = threading.Event(), threading.Event()
    gate = threading.Lock(); active = [0]; peak = [0]; calls = []; commits = []
    store.review_item(identities[1], 88, 0, 'selected', {'craft': 4}, [], 'My own preference')
    original_commit = media.record_asset
    def commit(run_id, asset):
        result = original_commit(run_id, asset)
        commits.append(asset[0])
        if asset[0] != identities[0]:
            with store.connection() as db:
                assert not db.execute('SELECT 1 FROM assets WHERE item=?', (identities[0],)).fetchone()
        if asset[0] == identities[2]:
            release_first.set()
        return result
    monkeypatch.setattr(media, 'record_asset', commit)
    class Stream(httpx.SyncByteStream):
        def __init__(self, slow):
            self.slow = slow
        def __iter__(self):
            with gate:
                active[0] += 1; peak[0] = max(peak[0], active[0])
            try:
                if self.slow:
                    first_started.set()
                    yield content[:10]
                    assert release_first.wait(15), 'Fast work must finish before the slow request is released'
                    yield content[10:]
                else:
                    assert first_started.wait(10)
                    # A second process/entry point must still respect the
                    # global worker lock while this batch has two threads.
                    assert media.run(1, only_item=identities[1])['state'] == 'already_running'
                    yield content
            finally:
                with gate: active[0] -= 1
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, headers={'Content-Length': str(len(content)), 'ETag': '"fixture-v1"'},
            stream=Stream(request.url.path.endswith('001.mp4')))
    install_transport(monkeypatch, respond)
    result = media.run(3, parallelism=2)
    assert result == {'state': 'completed', 'cached': 3, 'failed': 0}
    assert commits == [identities[1], identities[2], identities[0]]
    assert peak[0] == 2 and len(calls) == len(set(calls)) == 3
    with store.connection() as db:
        assets = db.execute('SELECT * FROM assets').fetchall()
        assert len(assets) == 3
        for asset in assets:
            assert asset['audio'] == 1 and asset['duration'] >= .9
            assert hashlib.sha256((store.ROOT / asset['path']).read_bytes()).hexdigest() == asset['sha256']
        assert db.execute('SELECT inserted FROM collection_runs').fetchone()[0] == 3
        assert tuple(db.execute('SELECT state,note FROM reviews').fetchone()) == ('selected', 'My own preference')
        assert all(json.loads(r[0])['training_eligible'] is False for r in db.execute('SELECT data FROM items'))


def test_one_source_failure_does_not_cancel_or_retry_other_downloads(films, monkeypatch):
    identities, content = films
    calls = []
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(503 if request.url.path.endswith('001.mp4') else 200, content=content)
    install_transport(monkeypatch, respond)
    assert media.run(3, parallelism=2) == {'state': 'partial', 'cached': 2, 'failed': 1}
    assert len(calls) == len(set(calls)) == 3
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 2
        assert db.execute('SELECT state FROM media_jobs WHERE item=?', (identities[0],)).fetchone()[0] == 'failed'
        assert db.execute('SELECT inserted FROM collection_runs').fetchone()[0] == 2


def test_inflight_final_files_reserve_capacity_before_another_launch(films, monkeypatch):
    identities, content = films
    monkeypatch.setattr(media, 'library_budget', lambda: 2 * media.MAX_FILE)
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=content))
    result = media.run(3, parallelism=2)
    assert result == {'state': 'storage_limit', 'cached': 2, 'failed': 0}
    with store.connection() as db:
        assert store.registered_media_bytes(db) <= 2 * media.MAX_FILE
        assert not db.execute('SELECT 1 FROM media_jobs WHERE item=?', (identities[2],)).fetchone()
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 2


def test_low_disk_space_drains_active_work_and_preserves_pending_items(films, monkeypatch):
    identities, content = films
    threshold = media.MIN_FREE + 2 * media.MAX_FILE
    free = iter([threshold, threshold, 0, 0])
    monkeypatch.setattr(media.shutil, 'disk_usage', lambda path: SimpleNamespace(free=next(free)))
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=content))
    result = media.run(3, parallelism=2)
    assert result == {'state': 'disk_space_limit', 'cached': 1, 'failed': 0}
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM media_jobs').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 1


@pytest.mark.parametrize('empty_active', [True, False])
def test_prefix_eviction_cannot_delete_an_active_worker(tmp_path, empty_active):
    cache = PartialCache(tmp_path)
    active = cache.root / ('a'*24); active.mkdir(parents=True)
    if not empty_active:
        (active / 'source.mp4').write_bytes(b'active')
    stale = cache.root / ('b'*24); stale.mkdir()
    (stale / 'source.mp4').write_bytes(b'stale!')
    target = cache.reserve('c'*24, 8, 16, protected={'a'*24, 'c'*24})
    assert target is not None and active.is_dir() and not stale.exists()
    if not empty_active:
        assert (active / 'source.mp4').read_bytes() == b'active'
    # Even an empty active directory reserves a complete file allowance.
    assert cache.reserve('d'*24, 8, 8, protected={'a'*24}) is None
    assert active.is_dir()


@pytest.mark.parametrize('value', [0, 3, True, '2'])
def test_invalid_parallelism_never_starts_work(tmp_path, monkeypatch, value):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'absent')
    with pytest.raises(ValueError, match='invalid_media_parallelism'):
        media.run(2, parallelism=value)
    assert not store.ROOT.exists()


def test_cli_parallelism_is_explicit_and_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(media, 'run', lambda *args, **kwargs: calls.append((args, kwargs)) or {'state': 'completed'})
    for field in ('MAX_FILE', 'MIN_FREE', 'DOWNLOAD_TIMEOUT'):
        monkeypatch.setattr(media, field, getattr(media, field))
    assert media.main(['--limit', '8', '--parallelism', '2']) == 0
    assert calls == [((8, False), {'parallelism': 2})]
    with pytest.raises(SystemExit):
        media.main(['--parallelism', '3'])
    assert len(calls) == 1


@pytest.mark.parametrize('configured,expected', [('2', 2), ('1', 1), ('0', 1), ('unbounded', 1)])
def test_service_parallelism_setting_is_bounded_and_cli_can_reduce_it(monkeypatch, configured, expected):
    calls = []
    monkeypatch.setenv('AD_LIBRARY_MEDIA_PARALLELISM', configured)
    monkeypatch.setattr(media, 'run', lambda *a, **kw: calls.append(kw.get('parallelism', 1)) or {'state': 'completed'})
    for field in ('MAX_FILE', 'MIN_FREE', 'DOWNLOAD_TIMEOUT'):
        monkeypatch.setattr(media, field, getattr(media, field))
    assert media.main(['--limit', '8']) == 0
    assert media.main(['--limit', '8', '--parallelism', '1']) == 0
    assert calls == [expected, 1]
