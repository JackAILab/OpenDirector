"""Reuse a verified cached award video across distinct source references.

This action performs no network requests and changes no source metadata,
reviews or training eligibility. Every new association has its own receipt.
"""
from collections import defaultdict
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from harness.library import store
from harness.models.reference_download import PUBLIC_AWARD_HOST, validate_url

SOURCE = '本地视频复用'
MAX_REUSES = 32
MAX_FILE = 320 * 1024 * 1024
# Scan in storage order and retain a bounded page cache across batches, so
# hashed public IDs do not force random shared-disk reads of item payloads.
PLAN_BATCH_SIZE = 256


def _locator(payload):
    try:
        url = json.loads(payload).get('creative_structure', {}).get('public_video_url', '')
        validate_url(url)
        parts = urlsplit(url)
        if (parts.fragment or not PUBLIC_AWARD_HOST.fullmatch(parts.hostname or '')
                or not parts.path.lower().endswith('.mp4')):
            return ''
        return url
    except (ValueError, TypeError, AttributeError):
        return ''


def _planning_batches():
    """Release read locks between pages while reusing the connection cache."""
    with store.connection() as db:
        db.execute('PRAGMA cache_size=-32768')  # At most about 32 MiB of pages.
        upper = db.execute('SELECT MAX(rowid) FROM items').fetchone()[0]
        after = 0
        while upper is not None and after < upper:
            # Public IDs are hashes: walking their index jumps between data
            # pages on the shared disk. The internal rowid follows table
            # storage order without changing public identity or plan ranking.
            # Freeze its upper bound so concurrent inserts cannot extend the
            # scan, even if their public IDs sort before older records.
            # SELECT does not open a Python sqlite3 write transaction. Close
            # its cursor before yielding to release the statement's read lock,
            # allowing collectors to commit without discarding cached pages.
            cursor = db.execute('''SELECT i.rowid AS scan_row,i.id,i.data,i.revision,i.created AS item_created,
                    a.path,a.sha256,a.bytes,a.duration,a.audio,a.width,a.height
                    FROM items i LEFT JOIN assets a ON a.item=i.id
                    WHERE i.rowid>? AND i.rowid<=? ORDER BY i.rowid LIMIT ?''',
                    (after, upper, PLAN_BATCH_SIZE))
            try:
                rows = cursor.fetchall()
            finally:
                cursor.close()
            if not rows:
                break
            after = rows[-1]['scan_row']
            yield rows


def _plans(limit):
    # Pages are observations, not a frozen snapshot. _register checks both
    # source records and their file metadata again in the write transaction.
    groups = defaultdict(list)
    for rows in _planning_batches():
        for row in rows:
            url = _locator(row['data'])
            if url:
                record = dict(row)
                del record['data']
                groups[url].append(record)
    plans = []
    for url, entries in groups.items():
        cached = [row for row in entries if row['sha256']]
        # Conflicting cached versions require separate investigation.
        if not cached or len({row['sha256'] for row in cached}) != 1:
            continue
        donor = min(cached, key=lambda row: (row['item_created'], row['id']))
        for target in entries:
            if not target['sha256']:
                plans.append((target, donor, url))
    plans.sort(key=lambda plan: (plan[0]['item_created'], plan[0]['id']))
    return plans[:limit]


def _stamp(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _verified_file(donor, url, checked):
    root = store.ROOT.resolve()
    relative = Path(donor['path'])
    if (relative.is_absolute() or len(relative.parts) != 3 or relative.parts[0] != 'assets'
            or not re.fullmatch(r'[0-9a-f]{24}', relative.parts[1])
            or not re.fullmatch(r'[0-9a-f]{64}', donor['sha256'])
            or relative.name != donor['sha256'] + '.mp4'
            or not 0 < donor['bytes'] <= MAX_FILE
            or not math.isfinite(donor['duration']) or donor['duration'] <= 0
            or donor['audio'] not in (0, 1) or donor['width'] <= 0 or donor['height'] <= 0):
        raise ValueError('invalid_reuse_asset')
    path = root / relative
    source = path.parent / 'source.json'
    poster = path.parent / 'poster.jpg'
    for file in (path, source, poster):
        if file.is_symlink() or file.resolve() != file or not file.is_file():
            raise ValueError('invalid_reuse_path')
    if source.stat().st_size > 4096 or json.loads(source.read_text()).get('media_url') != url:
        raise ValueError('reuse_source_mismatch')
    before = _stamp(path)
    if before[2] != donor['bytes']:
        raise ValueError('reuse_checksum_mismatch')
    key = (str(path), before)
    if key not in checked:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        checked[key] = digest.hexdigest()
    if checked[key] != donor['sha256'] or _stamp(path) != before:
        raise ValueError('reuse_checksum_mismatch')
    return path, before


def _register(run_id, target, donor, url, path, stamp):
    if _stamp(path) != stamp:
        raise ValueError('reuse_asset_changed')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT data,revision FROM items WHERE id=?', (target['id'],)).fetchone()
        existing = db.execute('SELECT * FROM assets WHERE item=?', (target['id'],)).fetchone()
        if existing:
            return False
        source = db.execute('SELECT i.data,a.* FROM items i JOIN assets a ON a.item=i.id WHERE i.id=?', (donor['id'],)).fetchone()
        if (not current or current['revision'] != target['revision'] or _locator(current['data']) != url
                or not source or _locator(source['data']) != url
                or any(source[key] != donor[key] for key in ('path','sha256','bytes','duration','audio','width','height'))):
            raise ValueError('reuse_source_changed')
        now = time.time()
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                   (target['id'], donor['path'], donor['sha256'], donor['bytes'], donor['duration'],
                    donor['audio'], donor['width'], donor['height'], now))
        db.execute('INSERT INTO media_reuses VALUES(?,?,?,?)', (target['id'], donor['id'], donor['sha256'], now))
        # A local association is not a new network attempt. Preserve any
        # existing attempt counter rather than incrementing or resetting it.
        db.execute('''INSERT INTO media_jobs VALUES(?,'completed',0,'',?)
            ON CONFLICT(item) DO UPDATE SET state='completed',error_code='',updated=excluded.updated''',
                   (target['id'], now))
        db.execute('UPDATE collection_runs SET inserted=inserted+1 WHERE id=?', (run_id,))
    return True


def reuse_cached_media(limit=MAX_REUSES):
    if type(limit) is not int or not 1 <= limit <= MAX_REUSES:
        raise ValueError('invalid_reuse_limit')
    store.ROOT.mkdir(parents=True, exist_ok=True)
    with (store.ROOT / '.media.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'reused': 0, 'network_downloads': 0}
        with store.connection() as db:
            db.execute("UPDATE collection_runs SET state='interrupted',finished=?,error_code='worker_restarted' WHERE source=? AND state='running'", (time.time(), SOURCE))
            if not db.execute('SELECT 1 FROM assets LIMIT 1').fetchone():
                return {'state': 'completed', 'considered': 0, 'reused': 0, 'skipped': 0, 'network_downloads': 0}
        plans = _plans(limit)
        identity, done, skipped, checked = secrets.token_hex(12), 0, 0, {}
        with store.connection() as db:
            db.execute('INSERT INTO collection_runs(id,source,started,state,discovered) VALUES(?,?,?,?,?)',
                       (identity, SOURCE, time.time(), 'running', len(plans)))
        for target, donor, url in plans:
            try:
                path, stamp = _verified_file(donor, url, checked)
                done += int(_register(identity, target, donor, url, path, stamp))
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                skipped += 1
        state = 'partial' if skipped else 'completed'
        with store.connection() as db:
            db.execute('UPDATE collection_runs SET state=?,finished=?,error_code=? WHERE id=?',
                       (state, time.time(), 'media_reuse_unavailable' if skipped else '', identity))
        return {'id': identity, 'state': state, 'considered': len(plans), 'reused': done,
                'skipped': skipped, 'network_downloads': 0, 'new_video_files': 0,
                'distinct_videos_added': 0}
