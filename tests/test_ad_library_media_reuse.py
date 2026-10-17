import fcntl
import hashlib
import json
import shutil
import sqlite3

import pytest

from harness.library import store
from harness.tools import reference_media_reuse as reuse

URL = 'https://bv-04.bubblevault.com/reference/mp4/720x480/film.mp4'


def item(name, url=URL):
    return store.ingest({'source_url': 'https://example.org/' + name, 'title': name,
                        'media_status': 'source_link',
                        'creative_structure': {'public_video_url': url}})[0]


def asset(identity, root, content=b'verified registered clip', url=URL):
    folder = root / 'assets' / identity
    folder.mkdir(parents=True)
    sha = hashlib.sha256(content).hexdigest()
    path = folder / (sha + '.mp4')
    path.write_bytes(content)
    (folder / 'source.json').write_text(json.dumps({'media_url': url}))
    (folder / 'poster.jpg').write_bytes(b'poster')
    with store.connection() as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, str(path.relative_to(root)), sha, len(content), 15, 1, 1280, 720, 0))
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    donor = item('donor')
    path = asset(donor, tmp_path)
    target = item('target')
    return tmp_path, donor, target, path


def test_reuse_keeps_separate_reviews_and_records_provenance_without_network(library, monkeypatch):
    root, donor, target, path = library
    import httpx
    monkeypatch.setattr(httpx, 'Client', lambda *a, **kw: pytest.fail('Reuse must not access the network'))
    store.review_item(target, 7, 0, 'selected', {'craft': 4}, ['visual'], 'My own preference')
    before = store.get_item(target, 7)
    with store.connection() as db:
        db.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'ReadTimeout',0)", (target,))
    result = reuse.reuse_cached_media()
    assert result['state'] == 'completed' and result['reused'] == 1
    assert result['network_downloads'] == result['new_video_files'] == result['distinct_videos_added'] == 0
    after = store.get_item(target, 7)
    assert after['review'] == before['review'] and after['revision'] == before['revision']
    assert after['training_eligible'] is False and after['media_status'] == 'local'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(DISTINCT sha256) FROM assets').fetchone()[0] == 1
        assert db.execute('SELECT path FROM assets WHERE item=?', (target,)).fetchone()[0] == str(path.relative_to(root))
        assert db.execute('SELECT source_item FROM media_reuses WHERE item=?', (target,)).fetchone()[0] == donor
        assert tuple(db.execute('SELECT state,attempts FROM media_jobs WHERE item=?', (target,)).fetchone()) == ('completed', 2)
    assert reuse.reuse_cached_media()['reused'] == 0


@pytest.mark.parametrize('fault', ['corrupt', 'source_changed', 'missing_poster', 'symlink'])
def test_invalid_local_evidence_never_creates_an_association(library, fault):
    root, donor, target, path = library
    if fault == 'corrupt':
        path.write_bytes(b'x' * path.stat().st_size)
    elif fault == 'source_changed':
        (path.parent / 'source.json').write_text(json.dumps({'media_url': URL.replace('film.mp4', 'other.mp4')}))
    elif fault == 'missing_poster':
        (path.parent / 'poster.jpg').unlink()
    else:
        external = root / 'external.mp4'
        path.rename(external)
        path.symlink_to(external)
    result = reuse.reuse_cached_media()
    assert result['reused'] == 0 and result['skipped'] == 1
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets WHERE item=?', (target,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM media_reuses').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM media_jobs WHERE item=?', (target,)).fetchone()[0] == 0


def test_conflicting_versions_of_same_locator_are_not_reused(library, monkeypatch):
    root, donor, target, path = library
    # Equal locators split across read pages must still detect all versions.
    monkeypatch.setattr(reuse, 'PLAN_BATCH_SIZE', 1)
    other = item('second-version')
    asset(other, root, b'different registered clip')
    result = reuse.reuse_cached_media()
    assert result['considered'] == result['reused'] == 0


def test_planning_releases_reader_between_pages_and_bounds_new_rows(library, monkeypatch):
    root, donor, target, path = library
    for index in range(7):
        item(f'page-target-{index}')
    # Equal timestamps must not skip rows at a page boundary.
    with store.connection() as db:
        db.execute('UPDATE items SET created=1')
        expected = [row[0] for row in db.execute('SELECT id FROM items ORDER BY rowid')]
    monkeypatch.setattr(reuse, 'PLAN_BATCH_SIZE', 2)
    pages = reuse._planning_batches()
    first = next(pages)
    assert len(first) == 2
    # A separate collector can commit while the plan is only partly read.
    # In DELETE journal mode, an active long reader would block this commit.
    writer = sqlite3.connect(root / 'library.sqlite3', timeout=0.05)
    try:
        writer.execute('BEGIN IMMEDIATE')
        writer.execute('UPDATE items SET revision=revision+1 WHERE id=?', (target,))
        writer.execute('''INSERT INTO items(id,source_url,title,data,created,updated)
            VALUES(?,?,?,?,?,?)''', ('0' * 24, 'https://example.org/new-during-scan',
                                    'new during scan', '{}', 2, 2))
        writer.commit()
    finally:
        writer.close()
    seen = [row['id'] for row in first]
    for page in pages:
        assert 0 < len(page) <= 2
        seen.extend(row['id'] for row in page)
    assert seen == expected


def test_storage_order_scan_handles_deleted_rows_and_keeps_public_ids(library, monkeypatch):
    root, donor, target, path = library
    middle = item('deleted-middle')
    tail = item('last-target')
    with store.connection() as db:
        db.execute('DELETE FROM items WHERE id=?', (middle,))
        expected = [r[0] for r in db.execute('SELECT id FROM items ORDER BY rowid')]
    monkeypatch.setattr(reuse, 'PLAN_BATCH_SIZE', 1)
    rows = [row for page in reuse._planning_batches() for row in page]
    assert [row['id'] for row in rows] == expected
    assert {row['id'] for row in rows} == {donor, target, tail}
    assert all(len(row['id']) == 24 for row in rows)
    assert reuse.reuse_cached_media()['reused'] == 2


def test_paged_plan_keeps_oldest_donor_and_oldest_targets(library, monkeypatch):
    root, donor, target, path = library
    other = item('second-same-version')
    asset(other, root)
    extra = item('second-target')
    with store.connection() as db:
        # Deliberately choose oldest by creation time, not by primary key.
        expected_donor = max(donor, other)
        expected_target = max(target, extra)
        db.execute('UPDATE items SET created=10')
        db.execute('UPDATE items SET created=1 WHERE id IN (?,?)',
                   (expected_donor, expected_target))
    monkeypatch.setattr(reuse, 'PLAN_BATCH_SIZE', 1)
    plans = reuse._plans(1)
    assert len(plans) == 1
    assert plans[0][0]['id'] == expected_target
    assert plans[0][1]['id'] == expected_donor


def test_source_revision_change_after_hashing_is_rejected(library, monkeypatch):
    root, donor, target, path = library
    original = reuse._verified_file
    def change(*args):
        verified = original(*args)
        item('target', URL.replace('film.mp4', 'other.mp4'))
        return verified
    monkeypatch.setattr(reuse, '_verified_file', change)
    assert reuse.reuse_cached_media()['reused'] == 0
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets WHERE item=?', (target,)).fetchone()[0] == 0


def test_provenance_failure_rolls_back_asset_job_and_progress(library):
    root, donor, target, path = library
    with store.connection() as db:
        db.execute("CREATE TRIGGER fail_reuse BEFORE INSERT ON media_reuses BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    result = reuse.reuse_cached_media()
    assert result['reused'] == 0 and result['state'] == 'partial'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets WHERE item=?', (target,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM media_jobs WHERE item=?', (target,)).fetchone()[0] == 0
        assert db.execute('SELECT inserted FROM collection_runs WHERE id=?', (result['id'],)).fetchone()[0] == 0


def test_live_download_lock_prevents_reuse_and_receipt_changes(library):
    root, donor, target, path = library
    with (root / '.media.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert reuse.reuse_cached_media()['state'] == 'already_running'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0] == 0


def test_reuse_is_bounded_and_does_not_overwrite_registered_assets(library):
    root, donor, target, path = library
    second = item('target-two')
    result = reuse.reuse_cached_media(limit=1)
    assert result['considered'] == result['reused'] == 1
    result = reuse.reuse_cached_media(limit=1)
    assert result['considered'] == result['reused'] == 1
    assert path.read_bytes() == b'verified registered clip'
    assert reuse.reuse_cached_media()['reused'] == 0


def test_backup_restores_shared_file_associations_and_provenance(library, monkeypatch):
    from harness.tools.reference_backup import backup
    from harness.tools import reference_backup
    root, donor, target, path = library
    assert reuse.reuse_cached_media()['reused'] == 1
    copied = []
    original = reference_backup.copy_checked
    def track(source, *args, **kwargs):
        copied.append(source)
        return original(source, *args, **kwargs)
    monkeypatch.setattr(reference_backup, 'copy_checked', track)

    class Transport:
        def upload(self, folder, identity):
            self.folder = folder

        def download(self, name, identity, directory):
            destination = directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.folder / name, destination)
            return destination

    result = backup(Transport())
    assert result['state'] == 'verified'
    assert copied.count(path) == 1
    assert copied.count(path.parent / 'poster.jpg') == 1
    restore = root / 'restore_checks' / result['snapshot']
    with sqlite3.connect(restore / 'library.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(DISTINCT path) FROM assets').fetchone()[0] == 1
        assert db.execute('SELECT source_item FROM media_reuses WHERE item=?', (target,)).fetchone()[0] == donor
        relative = db.execute('SELECT path FROM assets WHERE item=?', (target,)).fetchone()[0]
        assert (restore / relative).read_bytes() == path.read_bytes()


def test_disk_budgets_and_inventory_count_paths_not_source_rows_or_hashes(library):
    from harness.tools.reference_backup import check_snapshot_space
    from tools.cache_ad_reference_media import recover_candidates
    from tools.inventory_ad_library import inventory
    root, donor, target, path = library
    assert reuse.reuse_cached_media()['reused'] == 1
    # A historical independent copy of the very same bytes still uses disk.
    second = item('separate-file')
    asset(second, root)
    physical_bytes = 2 * path.stat().st_size
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM assets').fetchone()[0] == 3
        assert db.execute('SELECT count(distinct sha256) FROM assets').fetchone()[0] == 1
        assert store.registered_media_bytes(db) == physical_bytes
    assert recover_candidates(1)[1] == physical_bytes
    assert inventory()['media_bytes'] == physical_bytes
    assert check_snapshot_space(True, False) == 2 * ((root / 'library.sqlite3').stat().st_size + physical_bytes) + 512 * 1024**2


def test_shared_path_with_conflicting_checksum_still_fails_backup(library):
    from harness.tools.reference_backup import backup
    root, donor, target, path = library
    reuse.reuse_cached_media()
    with store.connection() as db:
        db.execute('UPDATE assets SET sha256=? WHERE item=?', ('f' * 64, target))
    class NoUpload:
        def upload(self, *args):
            pytest.fail('Inconsistent file identity must never be uploaded')
    with pytest.raises(RuntimeError, match='backup_failed') as failure:
        backup(NoUpload())
    assert str(failure.value.__context__) == 'source_asset_checksum_failed'
    with store.connection() as db:
        assert db.execute('SELECT state FROM backups').fetchone()[0] == 'failed'


@pytest.mark.parametrize('limit', [0, 33, True, 1.5])
def test_invalid_limit_is_rejected_before_work(limit):
    with pytest.raises(ValueError, match='invalid_reuse_limit'):
        reuse.reuse_cached_media(limit)
