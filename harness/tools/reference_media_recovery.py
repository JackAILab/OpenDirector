"""Register one intact final cache file after a failed local database commit.

This explicit maintenance action never downloads media or changes preferences.
It shares the media worker lock and accepts only a known database-failure job.
"""
import fcntl
import json
import math
import re
import secrets
import sqlite3
import subprocess
import time

from harness.library import store
from harness.models.reference_download import validate_url
from harness.tools.reference_media_reuse import MAX_FILE, _verified_file, _stamp

FFPROBE = '/opt/visualstation/creative-runtime/bin/ffprobe'
SOURCE = '本地缓存登记恢复'


def _probe(path):
    payload = json.loads(subprocess.check_output([FFPROBE, '-v', 'error',
        '-protocol_whitelist', 'file', '-f', 'mov',
        '-show_streams', '-show_format', '-of', 'json', str(path)],
        stderr=subprocess.DEVNULL, timeout=30))
    video = next(s for s in payload['streams'] if s['codec_type'] == 'video')
    duration = float(payload['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid_local_media')
    return {'duration': duration, 'audio': int(any(s['codec_type'] == 'audio' for s in payload['streams'])),
            'width': video['width'], 'height': video['height']}


def recover_cached_media(identity, *, budget):
    if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{24}', identity):
        raise ValueError('invalid_reference_identity')
    if type(budget) is not int or not 0 < budget <= 200 * 1024**3:
        raise ValueError('invalid_library_budget')
    baseline = {'recovered': 0, 'network_downloads': 0, 'new_video_files': 0}
    if not (store.ROOT / 'library.sqlite3').is_file():
        return {'state': 'no_eligible_candidate', **baseline}
    with (store.ROOT / '.media.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', **baseline}
        try:
            with store.connection() as db:
                if db.execute('SELECT 1 FROM assets WHERE item=?', (identity,)).fetchone():
                    return {'state': 'already_registered', **baseline}
                row = db.execute('''SELECT i.data,i.revision,j.state,j.error_code,j.attempts,j.updated
                    FROM items i JOIN media_jobs j ON j.item=i.id WHERE i.id=?''', (identity,)).fetchone()
                if not row or row['state'] != 'failed' or row['error_code'] != 'OperationalError':
                    return {'state': 'no_eligible_candidate', **baseline}
                row = dict(row)
            data = json.loads(row['data'])
            url = data.get('creative_structure', {}).get('public_video_url', '')
            validate_url(url)
            root = store.ROOT.resolve()
            folder = root / 'assets' / identity
            if folder.is_symlink() or folder.resolve() != folder:
                raise ValueError('invalid_local_media_path')
            files = [p for p in folder.glob('*.mp4') if re.fullmatch(r'[0-9a-f]{64}\.mp4', p.name)]
            if len(files) != 1:
                raise ValueError('local_media_missing_or_ambiguous')
            path = files[0]
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE:
                raise ValueError('invalid_local_media_path')
            before = _stamp(path)
            asset = {'path': str(path.relative_to(root)), 'sha256': path.stem,
                     'bytes': before[2], **_probe(path)}
            checked_path, stamp = _verified_file(asset, url, {})
            if stamp != before:
                raise ValueError('local_media_changed')
            run_id, now = secrets.token_hex(12), time.time()
            with store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('''SELECT i.data,i.revision,j.state,j.error_code,j.attempts,j.updated
                    FROM items i JOIN media_jobs j ON j.item=i.id WHERE i.id=?''', (identity,)).fetchone()
                if (not current or dict(current) != row or _stamp(checked_path) != stamp
                        or db.execute('SELECT 1 FROM assets WHERE item=?', (identity,)).fetchone()):
                    raise ValueError('local_recovery_source_changed')
                if store.registered_media_bytes(db) + asset['bytes'] > budget:
                    return {'state': 'storage_limit', **baseline}
                db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                    (identity, asset['path'], asset['sha256'], asset['bytes'], asset['duration'],
                     asset['audio'], asset['width'], asset['height'], now))
                # This repairs a local registration, not another network attempt.
                db.execute("UPDATE media_jobs SET state='completed',error_code='',updated=? WHERE item=?", (now, identity))
                db.execute('''INSERT INTO collection_runs
                    (id,source,started,finished,state,discovered,inserted,error_code)
                    VALUES(?,?,?,?,?,?,?,?)''', (run_id, SOURCE, now, now, 'completed', 1, 1, ''))
            return {'state': 'completed', **baseline, 'recovered': 1, 'receipt': run_id}
        except sqlite3.Error:
            return {'state': 'failed', **baseline, 'error_code': 'database_unavailable'}
        except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
            return {'state': 'failed', **baseline, 'error_code': 'local_evidence_unverified'}
