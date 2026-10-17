"""Bounded offline publication of reference skills; no model calls or preference writes."""
from collections import Counter, defaultdict, deque
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from harness.core.reference_skills import compile_skill, checksum, skill_markdown
from harness.library import store


def _read(path):
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    return closing(db)


def candidates():
    """Close each read between pages; never hold a full-library JSON join on FUSE."""
    with _read(store.ROOT / 'library.sqlite3') as db:
        assets = {r['item']: dict(r) for r in db.execute('SELECT * FROM assets').fetchall()}
    latest, cursor = {}, 0
    path = store.ROOT / 'learning/analyses.sqlite3'
    with _read(path) as db:
        upper = db.execute('SELECT COALESCE(MAX(rowid),0) FROM analyses').fetchone()[0]
    while cursor < upper:
        with _read(path) as db:
            rows = db.execute('SELECT rowid,* FROM analyses WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT 128',
                              (cursor, upper)).fetchall()
        if not rows:
            break
        cursor = rows[-1]['rowid']
        for row in rows:
            asset = assets.get(row['item'])
            if not asset or asset['sha256'] != row['media_sha256']:
                continue
            old = latest.get(row['item'])
            if old is None or row['version'] > old['version']:
                latest[row['item']] = dict(row)
    pool = []
    ids = sorted(latest)
    for start in range(0, len(ids), 32):
        chosen = ids[start:start+32]
        with _read(store.ROOT / 'library.sqlite3') as db:
            rows = db.execute('SELECT id,title,brand,source_url,data,revision FROM items WHERE id IN (' +
                              ','.join('?' for _ in chosen) + ')', chosen).fetchall()
        for row in rows:
            asset, entry = assets[row['id']], latest[row['id']]
            if not asset['audio'] or not 15 <= asset['duration'] <= 240:
                continue
            try:
                data, analysis = json.loads(row['data']), json.loads(entry['data'])
                if not data.get('quality_evidence') or not data.get('source_name'):
                    continue
                structure = data.get('creative_structure') or {}
                if not isinstance(structure, dict):
                    continue
                record = {**dict(row), **{k: asset[k] for k in ('sha256', 'duration', 'audio')},
                          'source_name': data['source_name'], 'analysis_version': entry['version'],
                          'source_section': structure.get('section', ''),
                          'analysis_source_revision': entry['source_revision']}
                recipe = compile_skill(record, analysis)
            except (ValueError, KeyError, TypeError):
                continue
            pool.append({'recipe': recipe, 'asset': asset})
    return pool


def select(pool, limit, minimum_sources=3):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('invalid_skill_limit')
    buckets = defaultdict(list)
    for entry in pool:
        recipe = entry['recipe']
        buckets[(recipe['reference_case']['source_name'], recipe['category'])].append(entry)
    for key in buckets:
        buckets[key].sort(key=lambda e: (
            e['recipe']['reference_case']['confidence'] != 'high',
            e['recipe']['reference_case']['duration'] > 65,
            e['asset']['bytes'], e['recipe']['id']))
    # Round-robin by source first, then by mechanism within each source.
    sources = defaultdict(list)
    for source, category in sorted(buckets):
        sources[source].append(deque(buckets[source, category]))
    def film_key(recipe):
        case = recipe['reference_case']
        clean = lambda value: re.sub(r'[^\w]', '', value).casefold()
        brand, title = clean(case.get('brand', '')), clean(case['title'])
        if brand and title.startswith(brand) and len(title) > len(brand):
            title = title[len(brand):]
        return brand, title
    selected, hashes, principles, films = [], set(), set(), set()
    while len(selected) < limit:
        progressed = False
        for source in sorted(sources):
            groups = sources[source]
            entry = None
            for _ in range(len(groups)):
                bucket = groups.pop(0)
                groups.append(bucket)
                while bucket:
                    candidate = bucket.popleft()
                    recipe = candidate['recipe']
                    if (recipe['reference_case']['media_sha256'] not in hashes
                            and recipe['description'] not in principles and film_key(recipe) not in films):
                        entry = candidate
                        break
                if entry:
                    break
            if entry:
                selected.append(entry)
                hashes.add(entry['recipe']['reference_case']['media_sha256'])
                principles.add(entry['recipe']['description'])
                films.add(film_key(entry['recipe']))
                progressed = True
            if len(selected) == limit:
                break
        if not progressed:
            break
    if len(selected) < limit or len({x['recipe']['reference_case']['source_name'] for x in selected}) < minimum_sources:
        raise ValueError('insufficient_distinct_reference_skills')
    return selected


def _verify(entry):
    asset = entry['asset']
    root = (store.ROOT / 'assets').resolve()
    path = store.ROOT / asset['path']
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('reference_media_unavailable')
    before = path.stat()
    if before.st_size != asset['bytes']:
        raise ValueError('reference_media_changed')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    after = path.stat()
    if (digest.hexdigest() != asset['sha256'] or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        raise ValueError('reference_media_changed')


def _atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(4))
    try:
        with temporary.open('x') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def restore_release(identity, runtime_directory, database=None):
    """Rebuild the local catalog from an explicitly selected backed-up release."""
    if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}', identity):
        raise ValueError('invalid_skill_release')
    with _read(database or store.ROOT / 'library.sqlite3') as db:
        row = db.execute('SELECT manifest FROM reference_skill_releases WHERE id=?', (identity,)).fetchone()
    if not row:
        raise ValueError('skill_release_not_found')
    publication = json.loads(row[0])
    recipes = publication.get('skills', [])
    if (publication.get('schema') != 'visualagent.reference-skill-catalog.v1'
            or publication.get('release') != identity or not 1 <= len(recipes) <= 500
            or len({r['id'] for r in recipes}) != len(recipes)
            or checksum({k:v for k,v in publication.items() if k != 'catalog_hash'}) != publication.get('catalog_hash')):
        raise ValueError('invalid_skill_release')
    for recipe in recipes:
        if (recipe.get('source') != 'reference' or recipe.get('training_eligible') is not False
                or checksum({k:v for k,v in recipe.items() if k != 'content_hash'}) != recipe.get('content_hash')):
            raise ValueError('invalid_skill_release')
    _atomic(Path(runtime_directory) / 'catalog.json', json.dumps(publication, ensure_ascii=False, indent=2) + '\n')
    return {'state': 'restored', 'release': identity, 'skills': len(recipes), 'model_calls': 0}


def publish(entries, runtime_directory, progress=None):
    """Verify exact files, retain immutable versions, then activate one local catalog."""
    if not entries or len(entries) > 500:
        raise ValueError('invalid_skill_selection')
    root = store.ROOT / 'skills'
    root.mkdir(exist_ok=True)
    with (root / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for index, entry in enumerate(entries):
            _verify(entry)
            if progress and (index == 0 or (index+1) % 10 == 0 or index+1 == len(entries)):
                progress({'state': 'verifying_sources', 'verified': index+1, 'total': len(entries)})
        release = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4)
        folder = root / 'releases' / release
        folder.mkdir(parents=True)
        recipes = []
        with store.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS reference_skill_versions(
                id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,created REAL NOT NULL,
                PRIMARY KEY(id,version))''')
            db.execute('''CREATE TABLE IF NOT EXISTS reference_skill_releases(
                id TEXT PRIMARY KEY,manifest TEXT NOT NULL,created REAL NOT NULL)''')
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for entry in entries:
                recipe = dict(entry['recipe'])
                case = recipe['reference_case']
                current = db.execute('SELECT i.revision,a.sha256,a.path,a.bytes FROM items i JOIN assets a ON i.id=a.item WHERE i.id=?',
                                     (case['id'],)).fetchone()
                if (not current or current['revision'] != case['source_revision']
                        or current['sha256'] != case['media_sha256']
                        or current['path'] != entry['asset']['path'] or current['bytes'] != entry['asset']['bytes']):
                    raise ValueError('reference_evidence_changed')
                old = db.execute('SELECT version,data FROM reference_skill_versions WHERE id=? ORDER BY version DESC LIMIT 1',
                                 (recipe['id'],)).fetchone()
                without_version = lambda value: {k:v for k,v in value.items() if k not in ('version','content_hash')}
                if old and without_version(json.loads(old['data'])) == without_version(recipe):
                    recipe = json.loads(old['data'])
                else:
                    recipe['version'] = old['version']+1 if old else 1
                    recipe.pop('content_hash', None)
                    recipe['content_hash'] = checksum(recipe)
                    db.execute('INSERT INTO reference_skill_versions VALUES(?,?,?,?)',
                               (recipe['id'], recipe['version'], json.dumps(recipe, ensure_ascii=False), time.time()))
                recipes.append(recipe)
            publication = {'schema': 'visualagent.reference-skill-catalog.v1', 'release': release,
                           'skills': recipes, 'source_counts': dict(Counter(s['reference_case']['source_name'] for s in recipes)),
                           'category_counts': dict(Counter(s['category'] for s in recipes)),
                           'training_eligible': False}
            publication['catalog_hash'] = checksum(publication)
            db.execute('INSERT INTO reference_skill_releases VALUES(?,?,?)',
                       (release, json.dumps(publication, ensure_ascii=False), time.time()))
        # Public outputs contain only compiled methods and allowlisted source evidence.
        for recipe in recipes:
            destination = folder / recipe['id']
            destination.mkdir()
            (destination / 'SKILL.md').write_text(skill_markdown(recipe))
            (destination / 'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + '\n')
        content = json.dumps(publication, ensure_ascii=False, indent=2) + '\n'
        (folder / 'catalog.json').write_text(content)
        _atomic(Path(runtime_directory) / 'catalog.json', content)
        _atomic(root / 'current.json', json.dumps({'release': release, 'catalog_hash': publication['catalog_hash']}) + '\n')
        return {'state': 'published', 'release': release, 'skills': len(recipes),
                'sources': publication['source_counts'], 'categories': publication['category_counts'],
                'training_eligible': False, 'model_calls': 0}
