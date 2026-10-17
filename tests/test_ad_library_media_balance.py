"""Keep a large old archive from starving other playable reference sources."""
import time

from harness.library import store
from tools import cache_ad_reference_media as media


def add(source, number, created):
    identity, _ = store.ingest({
        'source_url': f'https://example.org/{source}/{number}',
        'title': f'{source} {number}', 'ad_type': source + ' · Film',
        'media_status': 'source_link',
        'creative_structure': {'public_video_url': 'https://bv-04.bubblevault.com/public/mp4/award/film.mp4'},
    })
    with store.connection() as db:
        db.execute('UPDATE items SET created=? WHERE id=?', (created, identity))
    return identity


def test_large_older_archive_shares_batch_with_other_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    old = [add('CICLOPE', i, i+1) for i in range(25)]
    cresta = [add('Cresta', i, i+100) for i in range(3)]
    berlin = [add('Berlin Commercial', i, i+200) for i in range(3)]
    with store.connection() as db:
        rows = media.select_candidates(db, 6)
        assert [row['id'] for row in rows] == [old[0], cresta[0], berlin[0], old[1], cresta[1], berlin[1]]
        assert db.execute('SELECT COUNT(*) FROM media_jobs').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0


def test_single_item_batches_rotate_using_persisted_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    old = [add('CICLOPE', i, i+1) for i in range(5)]
    cresta = add('Cresta', 0, 100)
    berlin = add('Berlin Commercial', 0, 200)
    selected = []
    for _ in range(3):
        # Each call uses a new database connection, as a new worker does.
        with store.connection() as db:
            identity = media.select_candidates(db, 1)[0]['id']
        selected.append(identity)
        with store.connection() as db:
            db.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'ReadTimeout',?)", (identity, time.time()))
    assert selected == [old[0], cresta, berlin]


def test_recovery_and_cooldown_still_override_source_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    interrupted = add('CICLOPE', 0, 20)
    old = add('CICLOPE', 1, 1)
    fresh = add('Berlin Commercial', 0, 10)
    failed = add('Cresta', 0, 0)
    with store.connection() as db:
        db.execute("INSERT INTO media_jobs VALUES(?,'downloading',3,'',?)", (interrupted, time.time()))
        db.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'ReadTimeout',?)", (failed, time.time()))
    rows, _ = media.recover_candidates(3)
    assert [row['id'] for row in rows] == [interrupted, fresh, old]
    with store.connection() as db:
        assert db.execute('SELECT attempts FROM media_jobs WHERE item=?', (failed,)).fetchone()[0] == 1


def test_family_lookup_reads_covering_index_and_payloads_only_for_chosen_items(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    for number in range(20):
        add('CICLOPE', number, number)
    add('Cresta', 0, 100)
    with store.connection() as db:
        plan = db.execute('EXPLAIN QUERY PLAN SELECT id,ad_type FROM items INDEXED BY item_type_recent').fetchall()
        assert any('COVERING INDEX item_type_recent' in row['detail'] for row in plan)
        queries = []
        db.set_trace_callback(queries.append)
        rows = media.select_candidates(db, 2)
    assert len(rows) == 2
    payload_queries = [query for query in queries if query.startswith('SELECT id,data FROM items WHERE id IN')]
    assert len(payload_queries) == 1
    assert all(row['id'] in payload_queries[0] for row in rows)


def test_automatic_batches_defer_explicit_non_ads_but_keep_targeted_access(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    categories = ('Berlin Commercial · MUSIC VIDEOS / CRAFT: IDEA',
                  'Berlin Commercial · Personal Work / Craft: Direction',
                  'Berlin Commercial · Commercial Work / Craft: Use of Sound & Music',
                  'Berlin Commercial · Craft: Idea')
    ids = [add('Berlin Commercial', i, i) for i in range(4)]
    with store.connection() as db:
        db.executemany('UPDATE items SET ad_type=? WHERE id=?', zip(categories, ids))
        before = [tuple(r) for r in db.execute('SELECT * FROM items ORDER BY id')]
        assert {r['id'] for r in media.select_candidates(db, 8)} == set(ids[2:])
        assert [r['id'] for r in media.select_candidates(db, 1, only_item=ids[0])] == [ids[0]]
        # Neither skipped media nor an explicit selection is an attempt or preference.
        assert db.execute('SELECT COUNT(*) FROM media_jobs').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0
        assert before == [tuple(r) for r in db.execute('SELECT * FROM items ORDER BY id')]
        db.executemany('DELETE FROM items WHERE id=?', [(i,) for i in ids[2:]])
        assert media.select_candidates(db, 8) == []
