"""Best-effort local progress receipts; the backup database owns final state."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time


_PHASES = {'metadata', 'assets', 'learning_database', 'learning_evidence',
           'learning_bundle', 'learning_snapshot_ready'}
_COUNTS = {
    'preparing': ('processed_analysis_versions', 'total_analysis_versions',
                  'copied_learning_files', 'copied_learning_bytes'),
    'verifying': ('verified_files', 'total_files', 'verified_bytes', 'total_bytes',
                  'verified_learning_files', 'total_learning_files'),
}


def _path(library_root, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', identity):
        raise ValueError('invalid_snapshot_identity')
    root = Path(os.getenv('AD_LIBRARY_PROGRESS_ROOT',
        '/var/lib/visualstation-local/creative/learning/backup-progress'))
    library = hashlib.sha256(os.fsencode(Path(library_root).absolute())).hexdigest()[:24]
    return root / f'{library}-{identity}.json'


def _project(event):
    state = event.get('state')
    if state not in _COUNTS:
        raise ValueError('invalid_progress_state')
    result = {'state': state}
    if state == 'preparing':
        if event.get('phase') not in _PHASES:
            raise ValueError('invalid_progress_phase')
        result['phase'] = event['phase']
    for name in _COUNTS[state]:
        if name in event:
            value = event[name]
            if type(value) is not int or not 0 <= value <= 2**53 - 1:
                raise ValueError('invalid_progress_count')
            result[name] = value
    for done, total in [('processed_analysis_versions', 'total_analysis_versions'),
                        ('verified_files', 'total_files'), ('verified_bytes', 'total_bytes'),
                        ('verified_learning_files', 'total_learning_files')]:
        if done in result and (total not in result or result[done] > result[total]):
            raise ValueError('invalid_progress_count')
    return result


def write_progress(library_root, event):
    """Allowlist and atomically publish measurements without blocking backup success."""
    temporary = None
    try:
        path = _path(library_root, event.get('snapshot'))
        payload = {**_project(event), 'observed_at': time.time()}
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.part', delete=False) as out:
            temporary = Path(out.name)
            json.dump(payload, out)
            out.write('\n')
        temporary.replace(path)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def read_progress(library_root, identity, state, *, now=None):
    """Ignore missing/old-state receipts; expose measured counts, never completion."""
    if state not in _COUNTS:
        return None
    try:
        path = _path(library_root, identity)
        with path.open('rb') as source:
            content = source.read(8193)
        if len(content) > 8192:
            return None
        event = json.loads(content)
        if event.get('state') != state:
            return None
        result = _project(event)
        observed = event.get('observed_at')
        current = time.time() if now is None else now
        if (type(observed) not in (int, float) or not math.isfinite(observed)
                or observed <= 0 or observed > current + 30):
            return None
        result.pop('state')
        return {**result, 'observed_at': observed, 'stale': current - observed > 120}
    except (OSError, ValueError, TypeError, AttributeError):
        return None
