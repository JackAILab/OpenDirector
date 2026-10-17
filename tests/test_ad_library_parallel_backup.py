"""Bounded parallel readback must preserve the full restoration contract."""
import hashlib
import json
import sqlite3
import threading

import pytest

from harness.models.reference_backup import ModelScopeBackup
from harness.tools import reference_backup as action


class ReadFixture:
    def __init__(self, root, workers=1):
        self.root = root
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(workers) if workers > 1 else None
        self.calls, self.clients, self.busy = [], [], set()
        self.active = self.maximum = self.asset_calls = 0
        self.corrupt = None
        self.wrong_manifest = False
        root.mkdir()
        with sqlite3.connect(root / 'library.sqlite3') as db:
            db.execute('CREATE TABLE items(id TEXT)')
        self.payloads = {'library.sqlite3': (root / 'library.sqlite3').read_bytes(),
                         'preferences.jsonl': b'', 'items.jsonl': b''}
        self.payloads.update({f'assets/{i:02d}/poster.jpg': bytes([i]) * 16 for i in range(12)})
        self.manifest = {'items': 0, 'files': {
            name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in self.payloads.items()}}

    def transport(self):
        fixture = self
        with self.lock:
            number = len(self.clients)
            self.clients.append(number)

        class Transport:
            def fork_for_readback(self, identity):
                return fixture.transport()

            def download(self, name, identity, directory):
                with fixture.lock:
                    assert number not in fixture.busy, 'transport session shared between threads'
                    fixture.busy.add(number)
                    fixture.calls.append(name)
                    asset = name.startswith('assets/')
                    if asset:
                        fixture.active += 1
                        fixture.maximum = max(fixture.maximum, fixture.active)
                        fixture.asset_calls += 1
                    first_batch = asset and fixture.barrier and fixture.asset_calls <= fixture.barrier.parties
                try:
                    if first_batch:
                        fixture.barrier.wait(timeout=5)
                    if name == 'manifest.json':
                        payload = json.dumps({**fixture.manifest, **({'items': 9} if fixture.wrong_manifest else {})}).encode()
                    else:
                        payload = fixture.payloads[name]
                    if name == fixture.corrupt:
                        payload = b'!' * len(payload)
                    destination = directory / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(payload)
                    return destination
                finally:
                    with fixture.lock:
                        fixture.busy.remove(number)
                        if asset:
                            fixture.active -= 1

        return Transport()


@pytest.mark.parametrize('workers', [2, 4])
def test_parallel_readback_bounded_independent_and_complete(tmp_path, workers):
    fixture = ReadFixture(tmp_path / 'source', workers)
    restore = tmp_path / 'restore'; restore.mkdir()
    progress = []
    result = action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore,
                                 readback_workers=workers, progress=progress.append)
    assert result == 0
    assert fixture.maximum == workers
    assert len(fixture.clients) <= workers + 2  # caller + pinned parent + worker sessions
    assert len(set(fixture.calls)) == len(fixture.calls) == len(fixture.payloads) + 1
    first_asset = next(i for i, name in enumerate(fixture.calls) if name.startswith('assets/'))
    assert 'library.sqlite3' in fixture.calls[:first_asset]
    assert {p['state'] for p in progress} == {'verifying'}
    assert progress[0]['verified_files'] == 0
    assert progress[-1]['verified_files'] == len(fixture.payloads)
    assert progress[-1]['verified_bytes'] == progress[-1]['total_bytes'] == sum(map(len, fixture.payloads.values()))
    assert all((restore / name).read_bytes() == data for name, data in fixture.payloads.items())


def test_parallel_reuse_rechecks_bytes_and_refetches_corrupt_cache(tmp_path):
    fixture = ReadFixture(tmp_path / 'source')
    restore = tmp_path / 'restore'; restore.mkdir()
    transport = fixture.transport()
    action.verify_files(transport, 'snapshot', fixture.manifest, restore, readback_workers=4)
    damaged = 'assets/02/poster.jpg'
    (restore / damaged).write_bytes(b'?' * 16)  # same length, wrong hash
    fixture.calls.clear()
    reused = action.verify_files(transport, 'snapshot', fixture.manifest, restore, reuse=True, readback_workers=4)
    assert fixture.calls == ['manifest.json', damaged]
    assert reused == len(fixture.payloads) - 1
    assert (restore / damaged).read_bytes() == fixture.payloads[damaged]


@pytest.mark.parametrize('failure', ['manifest', 'core'])
def test_parallel_rejects_bad_metadata_before_any_media(tmp_path, failure):
    fixture = ReadFixture(tmp_path / 'source')
    fixture.wrong_manifest = failure == 'manifest'
    fixture.corrupt = 'library.sqlite3' if failure == 'core' else None
    restore = tmp_path / 'restore'; restore.mkdir()
    with pytest.raises(RuntimeError, match='remote_manifest_mismatch|remote_checksum_mismatch'):
        action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore, readback_workers=4)
    assert not any(name.startswith('assets/') for name in fixture.calls)


def test_parallel_failure_does_not_schedule_more_than_inflight_batch(tmp_path):
    fixture = ReadFixture(tmp_path / 'source', workers=4)
    # All first-batch files fail, regardless of completion order.
    fixture.payloads.update({name: b'!' * len(data) for name, data in fixture.payloads.items()
                             if name.startswith('assets/')})
    restore = tmp_path / 'restore'; restore.mkdir()
    progress = []
    with pytest.raises(RuntimeError, match='remote_checksum_mismatch'):
        action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore,
                            readback_workers=4, progress=progress.append)
    assert fixture.asset_calls == 4
    assert fixture.active == 0
    assert progress[-1]['verified_files'] < progress[-1]['total_files']
    assert all(p['state'] == 'verifying' for p in progress)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'assets/./image', 'assets//image'])
def test_parallel_rejects_aliased_paths_before_dispatch(tmp_path, name):
    fixture = ReadFixture(tmp_path / 'source')
    fixture.manifest['files'][name] = {'bytes': 1, 'sha256': '0' * 64}
    restore = tmp_path / 'restore'; restore.mkdir()
    with pytest.raises(RuntimeError, match='invalid_snapshot_manifest'):
        action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore, readback_workers=4)
    assert fixture.calls == ['manifest.json']


def test_parallel_refuses_existing_symlink_before_download(tmp_path):
    fixture = ReadFixture(tmp_path / 'source')
    restore = tmp_path / 'restore'; restore.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (restore / 'assets').symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match='invalid_restore_path'):
        action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore, readback_workers=4)
    assert not any(name.startswith('assets/') for name in fixture.calls)
    assert not list(outside.iterdir())


@pytest.mark.parametrize('workers', [False, 0, 5, 1.5, '2'])
def test_invalid_parallel_limits_fail_before_io(tmp_path, workers):
    with pytest.raises(RuntimeError, match='invalid_readback_workers'):
        action.verify_files(object(), 'snapshot', {}, tmp_path, readback_workers=workers)


def test_parallel_requires_forkable_transport(tmp_path):
    with pytest.raises(RuntimeError, match='parallel_readback_unsupported'):
        action.verify_files(object(), 'snapshot', {}, tmp_path, readback_workers=2)


def test_workers_keep_commit_pin_and_do_not_share_provider_session(tmp_path):
    identity = '20261008T000000Z-abcdef01'
    root = ModelScopeBackup(tmp_path / 'pins')
    root.record_revision(identity, 'a' * 40)
    root.api = object()
    parent = root.fork_for_readback(identity)
    root.record_revision(identity, 'b' * 40)
    worker = parent.fork_for_readback(identity)
    assert root.revision_for(identity) == 'b' * 40
    assert parent.revision_for(identity) == worker.revision_for(identity) == 'a' * 40
    assert not hasattr(parent, 'api') and not hasattr(worker, 'api')
    with pytest.raises(RuntimeError, match='invalid_remote_revision'):
        ModelScopeBackup().fork_for_readback(identity)


def test_progress_failure_cannot_skip_integrity_checks(tmp_path):
    fixture = ReadFixture(tmp_path / 'source')
    restore = tmp_path / 'restore'; restore.mkdir()
    def broken_callback(progress):
        raise BrokenPipeError('private consumer detail')
    assert action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore,
                               readback_workers=4, progress=broken_callback) == 0
    fixture.corrupt = 'library.sqlite3'
    with pytest.raises(RuntimeError, match='remote_checksum_mismatch'):
        action.verify_files(fixture.transport(), 'snapshot', fixture.manifest, restore,
                            readback_workers=4, progress=broken_callback)
