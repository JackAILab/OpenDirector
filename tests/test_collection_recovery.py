import time
import fcntl
import pytest

from harness.library import store
from tools import refresh_ad_library


def test_recover_stale_collection_runs_closes_old_receipts(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connection() as c:
        c.execute(
            "INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)",
            ('stale-aicp', 'AICP official shortlist', time.time() - 3600, 'running'),
        )
        c.execute(
            "INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)",
            ('fresh-aicp', 'AICP official shortlist', time.time(), 'running'),
        )
    assert refresh_ad_library.recover_stale_collection_runs(max_age=1800)
    with store.connection() as c:
        stale = c.execute('SELECT state,error_code,finished FROM collection_runs WHERE id=?', ('stale-aicp',)).fetchone()
        fresh = c.execute('SELECT state,error_code,finished FROM collection_runs WHERE id=?', ('fresh-aicp',)).fetchone()
    assert tuple(stale) == ('interrupted', 'stale_worker', stale['finished'])
    assert tuple(fresh) == ('running', '', None)


def test_recovery_does_not_close_rows_while_worker_lock_is_held(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connection() as c:
        c.execute(
            "INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)",
            ('active-aicp', 'AICP official shortlist', time.time() - 3600, 'running'),
        )
    with (tmp_path / '.collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not refresh_ad_library.recover_stale_collection_runs(max_age=1800)
    with store.connection() as c:
        row = c.execute('SELECT state,error_code,finished FROM collection_runs WHERE id=?', ('active-aicp',)).fetchone()
    assert tuple(row) == ('running', '', None)


def test_soft_source_failure_does_not_mark_multi_source_rotation_hard():
    assert not refresh_ad_library.has_hard_failure({
        'nyf': {'state': 'failed', 'error_code': 'source_unavailable'},
        'media': {'state': 'completed', 'error_code': ''},
    })
    assert not refresh_ad_library.has_hard_failure({
        'discovery': {'state': 'deferred_backup_in_progress'},
    })
    assert refresh_ad_library.has_hard_failure({
        'aicp': {'state': 'failed', 'error_code': 'database_unavailable'},
    })


@pytest.mark.parametrize('code,hard', [
    ('source_unavailable', False), ('database_unavailable', True),
    ('collector_error', True), ('', True),
])
def test_archive_batch_failure_reaches_rotation_classifier(monkeypatch, code, hard):
    from types import SimpleNamespace
    from harness.tools import award_archive
    calls = []
    def failed_batch(*args, **kwargs):
        calls.append(1)
        return {'state': 'failed', 'error_code': code, 'discovered': 0,
                'inserted': 0, 'offset': 12, 'next_offset': 12}
    monkeypatch.setattr(award_archive, 'collect_archive', failed_batch)
    result = award_archive.collect_archive_batches(
        SimpleNamespace(listing_url=lambda year: None), 'Test', 'test', 2026,
        max_batches=4)
    assert calls == [1]
    assert result['state'] == 'failed'
    assert result['last_batch']['next_offset'] == 12
    assert refresh_ad_library.has_hard_failure({'ciclope': result}) is hard


@pytest.mark.parametrize('metadata_only', [False, True])
def test_metadata_rotation_can_run_without_invoking_media(monkeypatch, metadata_only):
    calls = []
    names = ['collect', 'collect_corporate', 'collect_aicp', 'collect_lia',
             'collect_adfest', 'collect_adfest_showcase', 'collect_cannes_lions', 'collect_nyf',
             'collect_effie', 'collect_webby', 'collect_kyoorius', 'collect_kyoorius_current',
             'collect_kinsale', 'collect_berlin_commercial', 'collect_cresta',
             'collect_ciclope', 'collect_british_arrows', 'collect_mother_london', 'cache']
    def fake(name):
        def execute(*args):
            calls.append((name, args))
            if name == 'collect_aicp':
                raise RuntimeError('provider failure must not stop later sources')
            return {'state': 'completed'}
        return execute
    for name in names:
        monkeypatch.setattr(refresh_ad_library, name, fake(name))
    monkeypatch.setattr(refresh_ad_library, 'recover_stale_collection_runs', lambda: True)
    result = refresh_ad_library.run(metadata_only=metadata_only)
    assert [name for name, _ in calls] == (names[:-1] if metadata_only else names)
    assert calls[0] == ('collect', (12,))
    assert result['aicp']['error_code'] == 'collector_error'
    assert result['british_arrows']['state'] == 'completed'
    assert ('media' in result) is not metadata_only
    if not metadata_only:
        assert calls[-1] == ('cache', (12,))


@pytest.mark.parametrize('year', [None, '2026'])
def test_ciclope_batch_budget_supports_rotation_and_explicit_year(monkeypatch, year):
    calls = []
    def fake_ciclope(*args, **kwargs):
        calls.append((args, kwargs))
        return {'state': 'completed', 'batches': kwargs.get('batches', 1)}
    monkeypatch.setattr(refresh_ad_library, 'collect_ciclope', fake_ciclope)
    monkeypatch.setattr(refresh_ad_library, 'recover_stale_collection_runs', lambda: True)
    monkeypatch.setenv('AD_LIBRARY_CICLOPE_BATCHES', '4')
    if year is None:
        monkeypatch.delenv('AD_LIBRARY_CICLOPE_YEAR', raising=False)
    else:
        monkeypatch.setenv('AD_LIBRARY_CICLOPE_YEAR', year)
    # Replace unrelated sources so the assertion is only about the policy.
    for name in ('collect', 'collect_corporate', 'collect_aicp', 'collect_lia',
                 'collect_adfest', 'collect_adfest_showcase', 'collect_cannes_lions', 'collect_nyf',
                 'collect_effie', 'collect_webby', 'collect_kyoorius', 'collect_kyoorius_current',
                 'collect_kinsale', 'collect_berlin_commercial', 'collect_cresta',
                 'collect_british_arrows', 'collect_mother_london'):
        monkeypatch.setattr(refresh_ad_library, name, lambda: {'state': 'completed'})
    result = refresh_ad_library.run(metadata_only=True)
    expected = {'batches': 4}
    if year is not None:
        expected['year'] = int(year)
    assert calls == [((), expected)]
    assert result['ciclope']['batches'] == 4


def test_ciclope_batch_budget_invalid_env_falls_back_to_one(monkeypatch):
    calls = []
    monkeypatch.setattr(refresh_ad_library, 'collect_ciclope', lambda *args, **kwargs: calls.append((args, kwargs)) or {'state': 'completed'})
    monkeypatch.setattr(refresh_ad_library, 'recover_stale_collection_runs', lambda: True)
    monkeypatch.setenv('AD_LIBRARY_CICLOPE_BATCHES', 'not-a-number')
    for name in ('collect', 'collect_corporate', 'collect_aicp', 'collect_lia',
                 'collect_adfest', 'collect_adfest_showcase', 'collect_cannes_lions', 'collect_nyf',
                 'collect_effie', 'collect_webby', 'collect_kyoorius', 'collect_kyoorius_current',
                 'collect_kinsale', 'collect_berlin_commercial', 'collect_cresta',
                 'collect_british_arrows', 'collect_mother_london'):
        monkeypatch.setattr(refresh_ad_library, name, lambda: {'state': 'completed'})
    refresh_ad_library.run(metadata_only=True)
    assert calls == [((), {})]


def test_media_lock_prevents_recovery_during_independent_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connection() as c:
        c.execute("INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)",
                  ('active-media', '本地视频缓存', time.time() - 3600, 'running'))
    with (tmp_path / '.media.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not refresh_ad_library.recover_stale_collection_runs()
    with store.connection() as c:
        row = c.execute("SELECT state,finished FROM collection_runs WHERE id='active-media'").fetchone()
    assert tuple(row) == ('running', None)
