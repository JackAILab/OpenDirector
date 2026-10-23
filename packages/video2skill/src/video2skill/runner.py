"""Task lifecycle and sanitized observations; model access stays in the adapter."""
from contextlib import contextmanager
import sqlite3
import time
import uuid
from pathlib import Path
from .compiler import export
from .schema import Evidence, Source
from .harness.tools.media import sample
from .harness.models.vision import analyze, method


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT, updated REAL, error TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events(job TEXT, state TEXT, time REAL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'jobs.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            n = db.execute("SELECT count(*) FROM jobs WHERE state IN ('uploading','queued','sampling','analyzing','compiling')").fetchone()[0]
            if n >= 8: raise ValueError('queue_full')
            db.execute('INSERT INTO jobs VALUES(?,?,?,NULL)', (identity, 'uploading', time.time()))
        (self.root / identity).mkdir()
        return identity

    def update(self, identity, state, error=None):
        now = time.time()
        with self.connect() as db:
            db.execute('UPDATE jobs SET state=?,updated=?,error=? WHERE id=?', (state, now, error, identity))
            db.execute('INSERT INTO events VALUES(?,?,?)', (identity, state, now))

    def get(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None: return None
            result = dict(row)
            result['events'] = [dict(r) for r in db.execute('SELECT state,time FROM events WHERE job=? ORDER BY rowid', (identity,))]
            return result

    def recover(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM jobs WHERE state NOT IN ('completed','failed','interrupted')")]
        for identity in ids:
            self.update(identity, 'interrupted', 'service_restarted_no_retry')
            (self.root / identity / 'input.bin').unlink(missing_ok=True)


def run(store, identity, source: Source, target_duration=15, language='zh'):
    folder = store.root / identity
    stage = 'sampling'
    try:
        store.update(identity, stage)
        media = sample(folder / 'input.bin', folder / 'frames')
        stage = 'analyzing'
        store.update(identity, stage)
        analysis = analyze(source, media, folder / 'frames', language)
        evidence = Evidence(source=source, analysis=analysis, method=method(), **media)
        stage = 'compiling'
        store.update(identity, stage)
        export(evidence, folder / 'bundle', target_duration)
        store.update(identity, 'completed')
    except Exception:
        # Provider exceptions may contain tokens, URLs or raw response bodies.
        store.update(identity, 'failed', stage + '_failed')
    finally:
        (folder / 'input.bin').unlink(missing_ok=True)
