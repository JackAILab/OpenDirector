"""Bounded source scheduling and private, unpublished download prefixes.

The caller holds the library media lock. Only fixed files in managed item
directories are removed; registered assets and annotations are never touched.
"""
from collections import defaultdict, deque
import re

from harness.models.reference_download import checkpoint_info, discard_prefix

MAX_PARTIAL_BYTES = 2 * 1024 ** 3
MAX_PARTIAL_ITEMS = 16


def media_source_family(ad_type):
    """Only a scheduling group; never a quality label or human preference."""
    for source in ('CICLOPE', 'Cresta', 'Berlin Commercial', 'Kinsale', 'Kyoorius'):
        if ad_type.startswith(source + ' · '):
            return source
    return 'other'


def balanced_media_ids(candidates, source_by_item, activity, limit):
    """Rotate sources inside each existing recovery/attempt priority tier.

    Source activity comes from durable job timestamps, so a batch of one also
    rotates after a completed or failed attempt. Within a source, retain FIFO.
    Callers filter eligibility/cooldown first and fetch only chosen payloads.
    """
    if type(limit) is not int or not 1 <= limit <= 12:
        raise ValueError('invalid_media_batch_limit')
    tiers = defaultdict(lambda: defaultdict(deque))
    for row in sorted(candidates, key=lambda row: (row['priority'], row['attempts'], row['created'], row['id'])):
        tiers[(row['priority'], row['attempts'])][source_by_item.get(row['id'], 'other')].append(row)
    last_attempt = defaultdict(float)
    for row in activity:
        source = source_by_item.get(row['item'], 'other')
        last_attempt[source] = max(last_attempt[source], row['updated'])
    selected = []
    for tier in sorted(tiers):
        queues = tiers[tier]
        sources = sorted(queues, key=lambda source: (
            last_attempt[source], queues[source][0]['created'], queues[source][0]['id']))
        while any(queues.values()):
            for source in sources:
                if queues[source]:
                    selected.append(queues[source].popleft()['id'])
                    if len(selected) == limit:
                        return selected
    return selected


class PartialCache:
    def __init__(self, library_root):
        self.root = library_root / '.media-partials'

    def entries(self):
        if not self.root.is_dir() or self.root.is_symlink():
            return []
        result = []
        for path in self.root.iterdir():
            if re.fullmatch(r'[0-9a-f]{24}', path.name) and path.is_dir() and not path.is_symlink():
                result.append(path)
        return result

    def ready_ids(self, max_bytes):
        # Hints cannot validate a prefix; hashing and source identity checks
        # happen before a Range request. Limit SQL parameters even on old data.
        return [p.name for p in self.entries() if checkpoint_info(p, max_bytes)][:MAX_PARTIAL_ITEMS]

    def discard(self, identity):
        if not re.fullmatch(r'[0-9a-f]{24}', identity):
            raise ValueError('invalid_partial_identity')
        path = self.root / identity
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('invalid_partial_identity')
        discard_prefix(path)
        try:
            path.rmdir()
        except (FileNotFoundError, OSError):
            pass

    def reserve(self, identity, max_bytes, budget, *, protected=()):
        if not re.fullmatch(r'[0-9a-f]{24}', identity):
            raise ValueError('invalid_partial_identity')
        if self.root.is_symlink():
            raise ValueError('invalid_partial_identity')
        budget = max(0, min(budget, MAX_PARTIAL_BYTES))
        # The caller serializes reservations and protects all active workers.
        # Reserve their full allowance, including directories not created yet;
        # a small prefix must not be mistaken for its eventual download size.
        protected = set(protected) - {identity}
        if any(not re.fullmatch(r'[0-9a-f]{24}', key) for key in protected):
            raise ValueError('invalid_partial_identity')
        entries = self.entries()
        candidates = []
        for path in entries:
            if path.name == identity or path.name in protected:
                continue
            source = path / 'source.mp4'
            try:
                stat = source.stat()
                candidates.append((stat.st_mtime, path.name, stat.st_size))
            except FileNotFoundError:
                self.discard(path.name)
        candidates.sort()
        total = sum(entry[2] for entry in candidates) + len(protected) * max_bytes
        while candidates and (total + max_bytes > budget or len(candidates) + len(protected) >= MAX_PARTIAL_ITEMS):
            _, key, size = candidates.pop(0)
            self.discard(key)
            total -= size
        if total + max_bytes > budget or len(candidates) + len(protected) >= MAX_PARTIAL_ITEMS:
            self.discard(identity)
            return None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.root / identity
        if target.is_symlink():
            raise ValueError('invalid_partial_identity')
        target.mkdir(exist_ok=True, mode=0o700)
        return target
