import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import io
import pytest

spec = importlib.util.spec_from_file_location('restore', Path(__file__).parents[1] / 'scripts/download_assets.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class FakeHub:
    def __init__(self, files):
        self.files, self.calls = files, []

    def download_file(self, repo, kind, path, **kwargs):
        assert kwargs['revision'] == 'pinned'
        self.calls.append(path)
        source = self.files[path]
        if 'local_dir' in kwargs:
            target = kwargs['local_dir'] / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return target
        return source


def test_library_restore_resume_and_database_protection(tmp_path):
    media, db, index = [tmp_path / name for name in ['video', 'db', 'index']]
    media.write_bytes(b'test-media')
    db.write_bytes(b'test-database')
    entry = {'path': 'assets/example.mp4', 'bytes': media.stat().st_size, 'sha256': restore.sha256(media)}
    index.write_text(json.dumps([entry]))
    api = FakeHub({'release/files.json': index, 'release/library.sqlite3': db, 'release/assets/example.mp4': media})
    bundle = {'prefix': 'release/', 'index_sha256': restore.sha256(index), 'database_sha256': restore.sha256(db)}
    dest = tmp_path / 'dest'
    dest.mkdir()
    restore.restore_library(api, 'private/repo', bundle, 'pinned', dest, 2)
    assert (dest / 'assets/library/assets/example.mp4').read_bytes() == b'test-media'
    api.calls.clear()
    restore.restore_library(api, 'private/repo', bundle, 'pinned', dest, 2)
    assert not any(path.endswith('.mp4') for path in api.calls)
    (dest / 'assets/library/library.sqlite3').write_bytes(b'user-edited')
    with pytest.raises(ValueError, match='DB differs'):
        restore.restore_library(api, 'private/repo', bundle, 'pinned', dest, 2)
    assert (dest / 'assets/library/library.sqlite3').read_bytes() == b'user-edited'


def test_archive_escape_rejected(tmp_path):
    archive = tmp_path / 'bad.tar'
    with tarfile.open(archive, 'w') as tar:
        member = tarfile.TarInfo('../outside')
        member.size = 3
        tar.addfile(member, io.BytesIO(b'bad'))
    api = FakeHub({'bad.tar': archive})
    bundle = {'file': 'bad.tar', 'sha256': restore.sha256(archive), 'name': 'showcase'}
    with pytest.raises(ValueError, match='Unsafe asset path'):
        restore.restore_archive(api, 'private/repo', bundle, 'pinned', tmp_path)
    assert not (tmp_path.parent / 'outside').exists()


def test_library_symlink_escape_rejected(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'assets').symlink_to(outside)
    with pytest.raises(ValueError, match='Unsafe asset path'):
        restore.contained(root, 'assets/library')
