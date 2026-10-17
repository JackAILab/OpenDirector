"""Bounded, revision-checked enrichment of browsing labels; no model calls."""
from collections import Counter
import fcntl
import json
import time

from harness.library import store
from harness.library.taxonomy import classified_metadata


def enrich_industries(*, apply=False, max_records=10000, progress=None):
    if type(max_records) is not int or not 1 <= max_records <= 50000:
        raise ValueError('max_records must be 1-50000')
    store.ROOT.mkdir(parents=True, exist_ok=True)
    scanned = changed = 0
    counts = Counter()
    last = ''
    complete = False
    with (store.ROOT / '.collector.lock').open('a') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running', 'scanned': 0, 'changed': 0}
        while scanned < max_records:
            with store.connection() as db:
                rows = db.execute('''SELECT id,source_url,data,revision FROM items
                    WHERE id>? ORDER BY id LIMIT ?''',
                    (last, min(64, max_records - scanned))).fetchall()
            if not rows:
                complete = True
                break
            changes = []
            for row in rows:
                scanned += 1
                original = json.loads(row['data'])
                result = classified_metadata(row['source_url'], original)
                if result != original:
                    counts[result['industry']] += 1
                    changes.append((result['industry'], json.dumps(result, ensure_ascii=False, sort_keys=True),
                                    time.time(), row['id'], row['revision']))
            # Never hold a read lock while upgrading on the shared filesystem.
            if apply and changes:
                with store.connection() as db:
                    for change in changes:
                        if db.execute('''UPDATE items SET industry=?,data=?,updated=?,revision=revision+1
                            WHERE id=? AND revision=?''', change).rowcount != 1:
                            raise RuntimeError('source_revision_changed')
            changed += len(changes)
            last = rows[-1]['id']
            if progress and scanned % 256 == 0:
                progress({'state': 'running', 'applied': apply, 'scanned': scanned, 'changed': changed})
    return {'state': 'completed' if complete else 'limit_reached', 'applied': apply,
            'scanned': scanned, 'changed': changed, 'industries': dict(counts),
            'human_reviews_changed': False, 'training_eligibility_changed': False}
