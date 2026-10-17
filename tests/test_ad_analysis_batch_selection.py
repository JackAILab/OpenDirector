import json
import sqlite3
from tools.run_ad_analysis_batch import select_unattempted_ids


def test_failed_and_recent_attempts_do_not_starve_unattempted_media(tmp_path):
    receipts = {
        'failed': {'state': 'failed', 'error_code': 'ValueError'},
        'completed': {'state': 'completed'},
        'recent': {'state': 'started', 'started_at': 950},
        'stale': {'state': 'started', 'started_at': 100},
        'bad-time': {'state': 'started', 'started_at': 'invalid'},
    }
    for name, receipt in receipts.items():
        directory = tmp_path / name
        directory.mkdir()
        (directory / 'analysis-attempt.json').write_text(json.dumps(receipt))
    (tmp_path / 'corrupt').mkdir()
    (tmp_path / 'corrupt/analysis-attempt.json').write_text('invalid JSON')
    rows = [{'item': name, 'missing': ['analysis']}
            for name in ['failed', 'completed', 'recent', 'corrupt', 'bad-time', 'stale', 'new1', 'new2']]
    selected, skipped = select_unattempted_ids(rows, tmp_path, 2, now=1000)
    assert selected == ['stale', 'new1']
    assert skipped == 5
    # Selection must never erase receipts or authorize failed calls again.
    for name, receipt in receipts.items():
        assert json.loads((tmp_path / name / 'analysis-attempt.json').read_text()) == receipt


def test_all_protected_is_idle_and_semantic_reviews_are_not_reanalyzed(tmp_path):
    (tmp_path / 'failure').mkdir()
    (tmp_path / 'failure/analysis-attempt.json').write_text('{"state":"failed"}')
    rows = [{'item': 'failure', 'missing': ['analysis']},
            {'item': 'review', 'missing': ['audio_semantics', 'full_motion']}]
    assert select_unattempted_ids(rows, tmp_path, 24, now=1000) == ([], 1)


def test_scheduled_selection_respects_explicit_source_medium_without_changing_queue(tmp_path, monkeypatch):
    from harness.library import store, learning
    from tools.run_ad_analysis_batch import choose_ids
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    categories = ['Berlin Commercial · MUSIC VIDEOS / CRAFT: IDEA',
                  'Berlin Commercial · Personal Work / Craft: Direction',
                  'Berlin Commercial · Commercial Work / Craft: Use of Sound & Music',
                  'Berlin Commercial · Craft: Idea']
    ids = [store.ingest({'source_url': f'https://example.org/{n}',
                        'title': 'Music video is just a title here', 'ad_type': category})[0]
           for n, category in enumerate(categories)]
    payload = {'state': 'ready', 'items': [{'item': i, 'missing': ['analysis']} for i in ids]}
    before = json.dumps(payload, sort_keys=True)
    monkeypatch.setattr(learning, 'analysis_review_queue', lambda limit: payload)
    with learning.connection():
        pass
    assert choose_ids(2) == (ids[2:], 0)
    assert json.dumps(payload, sort_keys=True) == before
    assert not (tmp_path / 'learning/evidence').exists()


def test_new_films_take_priority_and_a_batch_never_repeats_one_video(tmp_path):
    rows = [
        {'item': 'known-copy', 'media_sha256': 'a'*64, 'missing': ['analysis']},
        {'item': 'new-first-source', 'media_sha256': 'b'*64, 'missing': ['analysis']},
        {'item': 'new-other-award', 'media_sha256': 'b'*64, 'missing': ['analysis']},
        {'item': 'another-new-film', 'media_sha256': 'c'*64, 'missing': ['analysis']},
    ]
    before = json.dumps(rows)
    assert select_unattempted_ids(rows, tmp_path, 2, now=1000, analyzed_media={'a'*64}) == (
        ['new-first-source', 'another-new-film'], 0)
    # When fresh films run out, source-specific analysis remains possible.
    assert select_unattempted_ids(rows, tmp_path, 24, now=1000, analyzed_media={'a'*64}) == (
        ['new-first-source', 'another-new-film', 'known-copy'], 0)
    assert json.dumps(rows) == before
    assert not list(tmp_path.iterdir())


def test_current_digest_priority_preserves_protected_attempts_and_source_queue(tmp_path, monkeypatch):
    from harness.library import store, learning
    from tools.run_ad_analysis_batch import choose_ids
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    ids = [store.ingest({'source_url': f'https://example.org/dedup/{n}', 'title': f'Film {n}'})[0]
           for n in range(5)]
    hashes = ['a'*64, 'a'*64, 'b'*64, 'c'*64, 'b'*64]
    with store.connection() as db:
        for item, digest in zip(ids, hashes):
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                       (item, f'assets/{item}/film.mp4', digest, 100, 30, 1, 1280, 720, 0))
    with learning.connection() as db:
        db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)', (ids[0], hashes[0], 1, 1, 'test', '{}', 0))
        # The third source was analyzed before its file changed: the new film
        # must still be prioritized, while the old hash does not suppress it.
        db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)', (ids[2], 'd'*64, 1, 1, 'test', '{}', 0))
    evidence = tmp_path/'learning/evidence'/ids[3]
    evidence.mkdir(parents=True)
    attempt = evidence/'analysis-attempt.json'
    attempt.write_text('{"state":"failed"}')
    payload = {'state': 'ready', 'items': [
        {'item': ids[n], 'media_sha256': hashes[n], 'missing': ['analysis']} for n in (1, 2, 3, 4)]}
    before = json.dumps(payload)
    monkeypatch.setattr(learning, 'analysis_review_queue', lambda limit: payload)
    assert choose_ids(24) == ([ids[2], ids[1]], 1)
    assert json.dumps(payload) == before
    assert attempt.read_text() == '{"state":"failed"}'
    with sqlite3.connect(tmp_path/'learning/analyses.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM analyses').fetchone()[0] == 2
