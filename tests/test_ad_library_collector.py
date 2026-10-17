import json
import httpx
import pytest
from harness.library import store
from tools import collect_ad_references as collector


@pytest.mark.parametrize('setting', [None, '', '0', 'true'])
def test_backup_lock_defers_without_database_or_network(tmp_path, monkeypatch, setting):
    import fcntl
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    if setting is None:
        monkeypatch.delenv('AD_LIBRARY_METADATA_OVERLAP', raising=False)
    else:
        monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', setting)
    def unexpected(*args, **kwargs):
        raise AssertionError('Deferred collection must not access database or network')
    monkeypatch.setattr(collector, '_run_unlocked', unexpected)
    with (tmp_path / '.backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert collector.run(12) == {'state': 'deferred_backup_in_progress'}
    assert not (tmp_path / 'library.sqlite3').exists()


def test_metadata_overlap_keeps_collector_lock(tmp_path, monkeypatch):
    import fcntl
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    def unexpected(*args, **kwargs):
        raise AssertionError('A second collector must not access database or network')
    monkeypatch.setattr(store, 'connection', unexpected)
    monkeypatch.setattr(collector.httpx, 'Client', unexpected)
    with (tmp_path / '.backup.lock').open('a') as backup_lock, (tmp_path / '.collector.lock').open('a') as collector_lock:
        fcntl.flock(backup_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(collector_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert collector.run(12) == {'state': 'already_running'}


def test_collection_during_upload_keeps_frozen_backup_and_human_preference(tmp_path, monkeypatch):
    import shutil
    import sqlite3
    from harness.tools.reference_backup import backup
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'data')
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    monkeypatch.setenv('AD_LIBRARY_YEARS', '2023')
    existing, _ = store.ingest({'source_url': 'https://example.org/existing', 'title': 'Existing film'})
    store.review_item(existing, 7, 0, 'selected', {'craft': 5}, [], 'Keep this preference')
    url = 'https://www.dandad.org/work/d-ad-awards-archive/new-film'
    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(404)), **kw))
    monkeypatch.setattr(collector.dandad, 'discover_films', lambda client, year, page: ([url], 2))
    monkeypatch.setattr(collector.dandad, 'fetch', lambda client, source: {'source_url': source, 'title': 'New film', 'media_url': 'https://media.dandad.org/new.m3u8'})
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)

    class Transport:
        def upload(self, folder, identity):
            self.folder = folder
            # backup() owns the real backup lock for the entire upload.
            result = collector.run(12)
            assert result['state'] == 'completed' and result['inserted'] == 1
            with sqlite3.connect(folder / 'library.sqlite3') as frozen:
                assert frozen.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 1
                assert frozen.execute('SELECT note FROM reviews').fetchone()[0] == 'Keep this preference'
            assert len((folder / 'items.jsonl').read_text().splitlines()) == 1

        def download(self, name, identity, directory):
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.folder / name, target)
            return target

    result = backup(Transport(), include_media=False, include_learning=False)
    assert result['state'] == 'verified' and result['items'] == 1
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 1
    assert store.get_item(existing, 7)['review']['note'] == 'Keep this preference'
    assert json.loads((store.ROOT / 'collection_cursor.json').read_text()) == {'year': 2023, 'page': 2}


def test_first_collection_creates_directory_and_releases_backup_lock(tmp_path, monkeypatch):
    import fcntl
    root = tmp_path / 'new' / 'library'
    monkeypatch.setattr(store, 'ROOT', root)
    monkeypatch.setattr(collector, '_run_unlocked', lambda limit, year: {'state': 'completed'})
    assert collector.run(12)['state'] == 'completed'
    with (root / '.backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_year_transition_keeps_existing_human_preference(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setenv('AD_LIBRARY_YEARS','2026,2023')
    (tmp_path/'collection_cursor.json').write_text(json.dumps({'year':2026,'page':1}))
    url='https://www.dandad.org/work/d-ad-awards-archive/test'
    identity,_=store.ingest({'source_url':url,'title':'Original'})
    store.review_item(identity,7,0,'selected',{'craft':5},['lighting'],'Human preference')
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',3,'source_locator_missing',0)",(identity,))
    real_client=httpx.Client
    monkeypatch.setattr(collector.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(lambda r:httpx.Response(404)),**kw))
    monkeypatch.setattr(collector.dandad,'discover_films',lambda client,year,page:([url],1))
    monkeypatch.setattr(collector.dandad,'fetch',lambda client,source:{'source_url':source,'title':'Updated','media_url':'https://media.dandad.org/test.m3u8'})
    monkeypatch.setattr(collector.time,'sleep',lambda seconds:None)
    result=collector.run(30)
    assert result['state']=='completed' and result['inserted']==0
    assert json.loads((tmp_path/'collection_cursor.json').read_text())=={'year':2023,'page':1}
    item=store.get_item(identity,7)
    assert item['title']=='Updated' and item['review']['state']=='selected'
    assert item['review']['note']=='Human preference' and item['training_eligible'] is False
    assert (tmp_path/'assets'/identity/'source.json').is_file()
    with store.connection() as c:
        job=c.execute('SELECT state,attempts,error_code FROM media_jobs WHERE item=?',(identity,)).fetchone()
        assert tuple(job)==('pending',3,'')


def test_rolling_years_expand_after_original_three(monkeypatch):
    monkeypatch.delenv('AD_LIBRARY_YEARS',raising=False)
    years=collector.source_years(2026)
    assert len(years)==16 and set(years)==set(range(2011,2027))
    assert collector.following_year(2026,years)==2023
    assert collector.following_year(2020,years)==2019
    assert collector.following_year(2015,years)==2014
    assert collector.following_year(2014,years)==2013
    assert collector.following_year(2011,years)==2025
    assert 2027 in collector.source_years(2027) and 2011 not in collector.source_years(2027)


@pytest.mark.parametrize('setting',['2026,2026','not-a-year','2999'])
def test_invalid_year_configuration_fails_before_network(tmp_path,monkeypatch,setting):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setenv('AD_LIBRARY_YEARS',setting)
    def network(**kw):raise AssertionError('Unexpected network request')
    monkeypatch.setattr(collector.httpx,'Client',network)
    result=collector.run(30)
    assert result['state']=='failed' and result['error_code']=='invalid_source_years'


def test_year_backfill_keeps_main_cursor_and_own_preferences(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    main={'year':2019,'page':3}
    (tmp_path/'collection_cursor.json').write_text(json.dumps(main))
    url='https://www.dandad.org/work/d-ad-awards-archive/older-film'
    identity,_=store.ingest({'source_url':url,'title':'Older film'})
    store.review_item(identity,7,0,'selected',{'craft':5},[], 'keep my preference')
    real_client=httpx.Client
    monkeypatch.setattr(collector.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(lambda r:httpx.Response(404)),**kw))
    monkeypatch.setattr(collector.dandad,'discover_films',lambda client,year,page:([url],9))
    monkeypatch.setattr(collector.dandad,'fetch',lambda client,source:{'source_url':source,'title':'Updated older film','media_url':'https://media.dandad.org/test.m3u8'})
    monkeypatch.setattr(collector.time,'sleep',lambda seconds:None)
    assert collector.run(30,2014)['state']=='completed'
    assert json.loads((tmp_path/'collection_cursor.json').read_text())==main
    assert json.loads((tmp_path/'collection_cursor_2014.json').read_text())=={'year':2014,'page':2}
    assert store.get_item(identity,7)['review']['note']=='keep my preference'
