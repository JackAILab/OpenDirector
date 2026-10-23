"""Restore versioned private assets without overwriting local edits or databases."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def contained(root: Path, relative: str) -> Path:
    path = Path(relative)
    target = root / path
    if path.is_absolute() or '..' in path.parts or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Unsafe asset path: {relative}')
    return target


def download(api, dataset, remote, revision, digest, **kwargs) -> Path:
    path = Path(api.download_file(dataset, 'dataset', remote, revision=revision,
                                 expected_sha256=digest, **kwargs))
    if sha256(path) != digest:
        raise ValueError(f'Checksum mismatch: {remote}')
    return path


def restore_library(api, dataset, bundle, revision, root, workers):
    prefix = bundle['prefix']
    index = download(api, dataset, prefix + 'files.json', revision, bundle['index_sha256'])
    database = download(api, dataset, prefix + 'library.sqlite3', revision, bundle['database_sha256'])
    entries = json.loads(index.read_text())
    target = contained(root, 'assets/library')
    target.mkdir(parents=True, exist_ok=True)
    dbtarget = contained(target, 'library.sqlite3')
    if dbtarget.exists() and sha256(dbtarget) != bundle['database_sha256']:
        raise ValueError('Existing library DB differs; restore into a fresh destination')
    needed, seen = [], set()
    for entry in entries:
        if entry['path'] in seen:
            raise ValueError('Duplicate path in library manifest')
        seen.add(entry['path'])
        dest = contained(target, entry['path'])
        if dest.exists():
            if not dest.is_file() or sha256(dest) != entry['sha256']:
                raise ValueError(f'Existing library file differs: {dest}')
        else:
            needed.append(entry)
    temporary = contained(root, '.opendirector-downloads')

    def restore(entry):
        source = download(api, dataset, prefix + entry['path'], revision, entry['sha256'],
                          local_dir=temporary)
        if source.stat().st_size != entry['bytes']:
            raise ValueError('Media size mismatch: ' + entry['path'])
        dest = contained(target, entry['path'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, dest)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for count, _ in enumerate(pool.map(restore, needed), 1):
            if count % 20 == 0 or count == len(needed):
                print(f'Library files restored: {count}/{len(needed)}', flush=True)
    if not dbtarget.exists():
        shutil.copy2(database, dbtarget)
    print(f'Restored library: {len(entries)} media files')


def restore_archive(api, dataset, bundle, revision, root):
    archive = download(api, dataset, bundle['file'], revision, bundle['sha256'])
    with tempfile.TemporaryDirectory(dir=root, prefix='.asset-restore-') as temp:
        staging = Path(temp)
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            regular = {member.name for member in members if member.isfile()}
            for member in members:
                contained(staging, member.name)
                if not (member.isfile() or member.isdir() or
                        (member.islnk() and member.linkname in regular)):
                    raise ValueError('Unsafe archive member')
            tar.extractall(staging, filter='data')
        files = [path for path in staging.rglob('*') if path.is_file()]
        for path in files:
            dest = contained(root, str(path.relative_to(staging)))
            if dest.exists() and (not dest.is_file() or sha256(dest) != sha256(path)):
                raise ValueError(f'Existing file differs; restore to a fresh directory: {dest}')
        for path in files:
            dest = contained(root, str(path.relative_to(staging)))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.move(path, dest)
    print(f'Restored {bundle["name"]}: {len(files)} files')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', choices=['showcase', 'library', 'learning', 'all'], default='showcase')
    parser.add_argument('--revision', help='Explicit override; hashes are still verified')
    parser.add_argument('--destination', type=Path, default=ROOT)
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'assets.lock.json').read_text())
    bundles = [b for b in lock['bundles'] if args.bundle == 'all' or b['name'] == args.bundle]
    if not bundles:
        parser.error('This release has no matching bundle')
    from modelscope_hub.api import HubApi
    api = HubApi(token=os.environ.get('MODELSCOPE_API_TOKEN'))
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for bundle in bundles:
        revision = args.revision or bundle.get('revision') or lock['revision']
        if bundle.get('kind') == 'library-tree':
            restore_library(api, lock['dataset'], bundle, revision, root, args.workers)
        else:
            restore_archive(api, lock['dataset'], bundle, revision, root)


if __name__ == '__main__':
    main()
