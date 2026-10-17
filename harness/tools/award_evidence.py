"""Bounded correction of source award labels; human reviews are never modified."""
import copy
import fcntl
import json
import time
from urllib.parse import urlsplit

from harness.library import store
from harness.models.reference_sources.award_evidence import award_evidence_kind


def same_source(left, right):
    try:
        return store.canonical_url(left) == store.canonical_url(right)
    except (TypeError, ValueError, AttributeError):
        return False


def corrected_evidence(source_url, data):
    if urlsplit(source_url).hostname not in ('awards.ciclopefestival.com', 'www.cresta-awards.com'):
        return data
    structure = data.get('creative_structure', {})
    if 'award' not in structure:
        return data
    kind = award_evidence_kind(structure['award'])
    if kind == 'award_winner':
        return data
    result = copy.deepcopy(data)
    for evidence in result.get('quality_evidence', []):
        if evidence.get('kind') == 'award_winner' and same_source(evidence.get('source_url'), source_url):
            evidence['kind'] = kind
            if not str(structure['award'] or '').strip():
                evidence['text'] = evidence.get('text', '').replace(' · winner · ', ' · 奖项级别待核实 · ')
    result['source_name'] = result.get('source_name', '').replace('官方获奖片', '官方案例')
    result['summary'] = result.get('summary', '').replace('获奖条目', '案例')
    return result


def repair_award_evidence(*, apply=False, batch_size=32, progress=None):
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError('batch_size must be 1-100')
    scanned = changed = 0
    last = ''
    with (store.ROOT / '.collector.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            with store.connection() as db:
                rows = db.execute('''SELECT id,source_url,data,revision FROM items
                    WHERE id>? AND (ad_type LIKE 'CICLOPE · %' OR ad_type LIKE 'Cresta · %')
                    ORDER BY id LIMIT ?''', (last, batch_size)).fetchall()
            if not rows:
                break
            # Finish the read before any write so network-disk reads cannot
            # retain a shared SQLite lock while waiting for an upgrade.
            changes = []
            for row in rows:
                scanned += 1
                data = json.loads(row['data'])
                updated = corrected_evidence(row['source_url'], data)
                if updated != data:
                    changes.append((json.dumps(updated, ensure_ascii=False, sort_keys=True),
                                    time.time(), row['id'], row['revision']))
            if apply and changes:
                with store.connection() as db:
                    for change in changes:
                        if db.execute('''UPDATE items SET data=?,updated=?,revision=revision+1
                            WHERE id=? AND revision=?''', change).rowcount != 1:
                            raise RuntimeError('source_revision_changed')
            changed += len(changes)
            last = rows[-1]['id']
            if progress:
                progress({'state': 'running', 'applied': apply, 'scanned': scanned,
                          'corrected' if apply else 'would_correct': changed})
    return {'state': 'completed', 'applied': apply, 'scanned': scanned,
            'corrected' if apply else 'would_correct': changed,
            'human_reviews_changed': False, 'training_eligibility_changed': False}
