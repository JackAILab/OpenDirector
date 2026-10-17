import pytest


def test_analysis_runner_requires_model_endpoint_before_work(monkeypatch):
    from tools.analyze_ad_library import configured_model
    monkeypatch.delenv('CREATIVE_MODEL_URL', raising=False)
    monkeypatch.delenv('CREATIVE_MODEL_KEY_FILE', raising=False)
    with pytest.raises(RuntimeError, match='creative_model_url_unconfigured'):
        configured_model()


def test_analysis_runner_uses_default_model_when_endpoint_is_configured(monkeypatch, tmp_path):
    from tools.analyze_ad_library import configured_model
    key = tmp_path / 'key'
    key.write_text('placeholder')
    monkeypatch.setenv('CREATIVE_MODEL_URL', 'http://127.0.0.1:1')
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE', str(key))
    monkeypatch.delenv('CREATIVE_MODEL', raising=False)
    assert configured_model() == 'cb-gpt-5.6-sol'


def test_library_read_timeout_is_bounded(monkeypatch):
    import time
    import tools.analyze_ad_library as runner
    monkeypatch.setattr(runner, '_read_rows_worker', lambda output, selected=None: time.sleep(5))
    started = time.monotonic()
    with pytest.raises(runner.LibraryReadTimeout):
        runner.read_library_rows(1)
    assert time.monotonic() - started < 5


@pytest.fixture
def library_for_selection(tmp_path, monkeypatch):
    import sqlite3
    root = tmp_path / 'library'
    root.mkdir()
    monkeypatch.setenv('AD_LIBRARY_ROOT', str(root))
    with sqlite3.connect(root / 'library.sqlite3') as db:
        db.executescript('''
            CREATE TABLE items(id TEXT PRIMARY KEY, data TEXT);
            CREATE TABLE assets(item TEXT PRIMARY KEY, path TEXT, sha256 TEXT, duration REAL);
        ''')
        ids = [f'{i:024x}' for i in range(2500)]
        db.executemany('INSERT INTO items VALUES(?,?)', [(i, '{}') for i in ids])
        db.executemany('INSERT INTO assets VALUES(?,?,?,?)', [(i, 'film.mp4', '0' * 64, 15) for i in ids])
    return root, ids


def test_selected_read_fetches_only_requested_media_in_queue_order(library_for_selection):
    from tools.analyze_ad_library import read_library_rows
    _, ids = library_for_selection
    selected = tuple(reversed(ids[122:146]))
    rows = read_library_rows(10, selected=selected)
    assert [row['id'] for row in rows] == list(selected)
    assert all(row['duration'] == 15 for row in rows)


def test_missing_selected_asset_stops_the_batch_before_model_calls(library_for_selection):
    import sqlite3
    from tools.analyze_ad_library import read_library_rows
    root, ids = library_for_selection
    with sqlite3.connect(root / 'library.sqlite3') as db:
        db.execute('DELETE FROM assets WHERE item=?', (ids[400],))
    # Exercise the second query chunk: partial results must not escape.
    with pytest.raises(RuntimeError, match='analysis_selection_unavailable'):
        read_library_rows(10, selected=tuple(ids[100:500]))


def test_empty_selection_does_not_read_database_or_fall_back_to_all(monkeypatch):
    import tools.analyze_ad_library as runner
    def unexpected_read(*args, **kwargs):
        pytest.fail('Empty selection must not open a database or start a worker')
    monkeypatch.setattr(runner.tempfile, 'mkstemp', unexpected_read)
    assert runner.read_library_rows(selected=()) == []


@pytest.mark.parametrize('entries', [{}, [{'id': 'invalid'}], [{'id': 'a' * 24}] * 2, [None], []])
def test_selection_validation_is_explicit(tmp_path, entries):
    import json
    from tools.analyze_ad_library import load_selection
    path = tmp_path / 'selection.json'
    path.write_text(json.dumps(entries))
    if entries == []:
        assert load_selection(path) == ()
    else:
        with pytest.raises(RuntimeError, match='invalid_analysis_selection'):
            load_selection(path)
    assert load_selection(None) is None
