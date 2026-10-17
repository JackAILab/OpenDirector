import httpx
import pytest
from tools.cache_ad_reference_media import playlist,local_playlist
from tools import cache_ad_reference_media as media

ORIGIN='https://media.dandad.org'
CDN='https://d2rmu1yblu9p0.cloudfront.net'


def test_dandad_official_cloudfront_mp4_is_allowlisted(tmp_path):
    def request(req):
        return httpx.Response(200,content=b'official mp4')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        local=media.direct_media(client,CDN+'/award-film.mp4',tmp_path)
    assert local.read_bytes()==b'official mp4'


def test_official_award_bubblevault_mp4_is_allowlisted(tmp_path):
    def request(req):
        return httpx.Response(200,content=b'official award mp4')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        local=media.direct_media(client,'https://bv-04.bubblevault.com/public/mp4/award/film.mp4',tmp_path)
    assert local.read_bytes()==b'official award mp4'


def test_direct_mp4_is_local_and_bounded(tmp_path,monkeypatch):
    calls=[]
    def request(req):
        calls.append(req.url.path);return httpx.Response(200,content=b'mp4 bytes')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        url=playlist(client,ORIGIN+'/film.mp4')
        assert not calls
        local=media.direct_media(client,url,tmp_path)
        assert local.read_bytes()==b'mp4 bytes'
        assert calls==['/film.mp4']
        with pytest.raises(ValueError,match='unsupported_media_format'):
            media.direct_media(client,ORIGIN+'/film.html',tmp_path)
        monkeypatch.setattr(media,'MAX_FILE',3)
        with pytest.raises(ValueError,match='media_limit'):
            media.direct_media(client,url,tmp_path)


def test_direct_mp4_stream_limit_without_content_length(tmp_path,monkeypatch):
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):yield b'too large'
    monkeypatch.setattr(media,'MAX_FILE',3)
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Chunks()))) as client:
        with pytest.raises(ValueError,match='media_limit'):
            media.direct_media(client,ORIGIN+'/film.mp4',tmp_path)


def test_hls_variant_and_local_only_manifest(tmp_path):
    manifest='#EXTM3U\n#EXT-X-ENDLIST\n#EXTINF:2,\none.ts\n'
    def request(req):
        body={'/master.m3u8':'#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080\nhigh.m3u8\n#EXT-X-STREAM-INF:RESOLUTION=1280x720\nreview.m3u8\n', '/review.m3u8':manifest, '/one.ts':'fragment'}[req.url.path]
        return httpx.Response(200,text=body)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        selected=playlist(client,ORIGIN+'/master.m3u8')
        assert selected.endswith('/review.m3u8')
        local=local_playlist(client,selected,tmp_path)
        assert 'https:' not in local.read_text()
        assert (tmp_path/'fragment-00000.bin').read_bytes()==b'fragment'


@pytest.mark.parametrize('text',[
    '#EXTM3U\n#EXT-X-ENDLIST\nhttp://127.0.0.1/private\n',
    '#EXTM3U\n#EXT-X-ENDLIST\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n',
    '#EXTM3U\n#EXTINF:2,\none.ts\n',
])
def test_unsafe_encrypted_or_live_media_not_downloaded(tmp_path,text):
    calls=[]
    def request(req):
        calls.append(str(req.url));return httpx.Response(200,text=text)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(ValueError):local_playlist(client,ORIGIN+'/review.m3u8',tmp_path)
    assert len(calls)==1


def test_media_byte_budget(tmp_path,monkeypatch):
    monkeypatch.setattr(media,'MAX_FILE',3)
    def request(req):return httpx.Response(200,text='#EXTM3U\n#EXT-X-ENDLIST\nlarge.ts\n' if req.url.path.endswith('.m3u8') else 'too large')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(ValueError,match='media_limit'):local_playlist(client,ORIGIN+'/review.m3u8',tmp_path)


def test_interrupted_job_recovers_before_new_items(tmp_path,monkeypatch):
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    old,_=store.ingest({'source_url':'https://example.org/old','title':'Old'})
    new,_=store.ingest({'source_url':'https://example.org/new','title':'New'})
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'downloading',3,'',0)",(old,))
        c.execute("INSERT INTO collection_runs(id,source,started,state,inserted) VALUES('old-run','本地视频缓存',0,'running',6)")
    rows,used=media.recover_candidates(1)
    assert [r['id'] for r in rows]==[old] and used==0
    with store.connection() as c:
        assert c.execute('select state from media_jobs where item=?',(old,)).fetchone()[0]=='interrupted'
        run=c.execute("select state,inserted from collection_runs where id='old-run'").fetchone()
        assert tuple(run)==('interrupted',6)
        assert c.execute('select count(*) from media_jobs where item=?',(new,)).fetchone()[0]==0


def test_asset_and_progress_commit_together_or_rollback(tmp_path,monkeypatch):
    import sqlite3
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    one,_=store.ingest({'source_url':'https://example.org/one','title':'One'})
    two,_=store.ingest({'source_url':'https://example.org/two','title':'Two'})
    with store.connection() as c:
        c.execute("INSERT INTO collection_runs(id,source,started,state) VALUES('run','本地视频缓存',0,'running')")
        for item in (one,two):c.execute("INSERT INTO media_jobs VALUES(?,'downloading',1,'',0)",(item,))
    def asset(item):return (item,'assets/'+item+'/film.mp4','abc',100,15,1,1280,720,0)
    assert media.record_asset('run',asset(one))
    assert not media.record_asset('run',asset(one))
    with store.connection() as c:
        assert c.execute("select inserted from collection_runs where id='run'").fetchone()[0]==1
        c.execute("CREATE TRIGGER write_error BEFORE UPDATE ON collection_runs BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):media.record_asset('run',asset(two))
    with store.connection() as c:
        assert c.execute('select count(*) from assets where item=?',(two,)).fetchone()[0]==0
        assert c.execute('select state from media_jobs where item=?',(two,)).fetchone()[0]=='downloading'


@pytest.mark.parametrize('configured', ['0','-1','201','unbounded'])
def test_invalid_library_budget_stops_before_disk_or_network(tmp_path,monkeypatch,configured):
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path/'absent')
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB',configured)
    with pytest.raises(ValueError,match='invalid_library_budget'):
        media.run(1)
    assert not store.ROOT.exists()


@pytest.mark.parametrize('full,expected', [(True,'storage_limit'),(False,'disk_space_limit')])
def test_cache_capacity_gate_preserves_pending_items(tmp_path,monkeypatch,full,expected):
    import types
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB','50')
    iid,_=store.ingest({'source_url':'https://example.org/existing','title':'Existing'})
    store.ingest({'source_url':'https://example.org/pending','title':'Pending'})
    with store.connection() as c:
        c.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)",(iid,'assets/pending/film.mp4','abc',50*1024**3 if full else 0,15,1,1280,720,0))
    monkeypatch.setattr(media.shutil,'disk_usage',lambda _:types.SimpleNamespace(free=0))
    assert media.run(12)=={'state':expected}
    with store.connection() as c:
        assert c.execute('select count(*) from assets').fetchone()[0]==1
        assert c.execute('select count(*) from collection_runs').fetchone()[0]==0


def test_disk_filling_mid_batch_reports_stop_without_touching_pending(tmp_path,monkeypatch):
    import types
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB','50')
    store.ingest({'source_url':'https://example.org/pending','title':'Pending'})
    remaining=iter([media.MIN_FREE,0])
    monkeypatch.setattr(media.shutil,'disk_usage',lambda _:types.SimpleNamespace(free=next(remaining)))
    assert media.run(12)=={'state':'disk_space_limit','cached':0,'failed':0}
    with store.connection() as c:
        run=c.execute('select state,inserted,error_code from collection_runs').fetchone()
        assert tuple(run)==('partial',0,'disk_space_limit')
        assert c.execute('select count(*) from media_jobs').fetchone()[0]==0
        assert c.execute('select count(*) from assets').fetchone()[0]==0


def test_long_hls_chooses_bounded_official_variant(monkeypatch):
    monkeypatch.setattr(media,'MAX_FILE',1000)
    calls=[]
    def request(req):
        calls.append(req.url.path)
        body={'/master.m3u8':'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=8000,RESOLUTION=1280x720\nlarge.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=400,RESOLUTION=768x1366\nsmall.m3u8\n',
              '/large.m3u8':'#EXTM3U\n#EXTINF:10,\nlarge.ts\n#EXT-X-ENDLIST\n',
              '/small.m3u8':'#EXTM3U\n#EXTINF:10,\nsmall.ts\n#EXT-X-ENDLIST\n'}[req.url.path]
        return httpx.Response(200,text=body)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        assert playlist(client,ORIGIN+'/master.m3u8').endswith('/small.m3u8')
    assert not any(v.endswith('.ts') for v in calls)


def test_all_oversized_variants_stop_before_segments(monkeypatch):
    monkeypatch.setattr(media,'MAX_FILE',100)
    def request(req):
        assert not req.url.path.endswith('.ts')
        return httpx.Response(200,text=('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=8000,RESOLUTION=1280x720\nlarge.m3u8\n' if req.url.path.endswith('master.m3u8') else '#EXTM3U\n#EXTINF:10,\nlarge.ts\n#EXT-X-ENDLIST\n'))
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(ValueError,match='media_limit'):playlist(client,ORIGIN+'/master.m3u8')


def test_explicit_retry_only_reopens_size_failures(tmp_path,monkeypatch):
    from harness.library import store
    import time
    monkeypatch.setattr(store,'ROOT',tmp_path)
    limited,_=store.ingest({'source_url':'https://example.org/limited','title':'Limited'})
    other,_=store.ingest({'source_url':'https://example.org/other','title':'Other'})
    slow,_=store.ingest({'source_url':'https://example.org/slow','title':'Slow'})
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'media_limit',?)",(limited,time.time()))
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'unsupported_media_locator',?)",(other,time.time()))
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'download_timeout',?)",(slow,time.time()))
    assert not media.recover_candidates(12)[0]
    assert [r['id'] for r in media.recover_candidates(12,True)[0]]==[limited]


def test_missing_source_locator_is_retired_from_recovery_queue(tmp_path,monkeypatch):
    from harness.library import store
    import time
    monkeypatch.setattr(store,'ROOT',tmp_path)
    missing,_=store.ingest({'source_url':'https://example.org/missing','title':'Missing locator'})
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'source_locator_missing',?)",(missing,time.time()-8*3600))
    assert media.recover_candidates(12)[0] == []
    assert media.recover_candidates(12,True)[0] == []


def test_official_source_links_do_not_enter_download_queue(tmp_path,monkeypatch):
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    external,_=store.ingest({'source_url':'https://example.org/official','title':'Official archive','media_status':'source_link'})
    downloadable,_=store.ingest({'source_url':'https://example.org/downloadable','title':'Download candidate'})
    rows,_=media.recover_candidates(12)
    assert [r['id'] for r in rows]==[downloadable]
    with store.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM media_jobs WHERE item=?',(external,)).fetchone()[0]==0


def test_official_award_video_source_link_enters_download_queue(tmp_path,monkeypatch):
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    award,_=store.ingest({'source_url':'https://example.org/award','title':'Award film',
        'media_status':'source_link','creative_structure':{
            'public_video_url':'https://bv-04.bubblevault.com/public/mp4/award/film.mp4'}})
    rows,_=media.recover_candidates(12)
    assert [r['id'] for r in rows]==[award]


@pytest.mark.parametrize('value',['0','-1','1025','3.5','unbounded'])
def test_explicit_file_limit_rejects_unbounded_values(value):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):media.file_limit_mib(value)


def test_explicit_file_limit_and_retry_priority(tmp_path,monkeypatch):
    from harness.library import store
    import time
    assert media.file_limit_mib('512')==512
    assert media.file_limit_mib('1024')==1024
    monkeypatch.setattr(store,'ROOT',tmp_path)
    old,_=store.ingest({'source_url':'https://example.org/large','title':'Large'})
    store.ingest({'source_url':'https://example.org/new','title':'New'})
    with store.connection() as c:c.execute("INSERT INTO media_jobs VALUES(?,'failed',2,'media_limit',?)",(old,time.time()))
    assert [r['id'] for r in media.recover_candidates(1,True)[0]]==[old]


def test_fresh_discoveries_do_not_starve_older_media(tmp_path,monkeypatch):
    from harness.library import store
    import time
    monkeypatch.setattr(store,'ROOT',tmp_path)
    def add(slug,created):
        identity,_=store.ingest({'source_url':'https://example.org/'+slug,'title':slug})
        with store.connection() as c:c.execute('UPDATE items SET created=? WHERE id=?',(created,identity))
        return identity
    oldest=add('oldest',1)
    middle=add('middle',2)
    newest=add('newest',3)
    cooled=add('cooled_failure',0)
    recent=add('recent_failure',0)
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'ReadTimeout',?)",(cooled,time.time()-7*3600))
        c.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'ReadTimeout',?)",(recent,time.time()))
    assert [r['id'] for r in media.recover_candidates(2)[0]]==[oldest,middle]
    add('another_new_reference',4)
    assert [r['id'] for r in media.recover_candidates(2)[0]]==[oldest,middle]
    candidates=[r['id'] for r in media.recover_candidates(12)[0]]
    assert candidates[:3]==[oldest,middle,newest]
    assert candidates[-1]==cooled and recent not in candidates


@pytest.mark.parametrize('value',['0','59','1801','3.5','unbounded'])
def test_download_timeout_must_be_bounded(value):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):media.download_timeout_seconds(value)


@pytest.mark.parametrize('hls',[False,True])
@pytest.mark.parametrize('budget',[600,1200])
def test_slow_download_obeys_selected_deadline_without_changing_byte_limit(tmp_path,monkeypatch,hls,budget):
    from types import SimpleNamespace
    now=[0]
    monkeypatch.setattr(media,'time',SimpleNamespace(monotonic=lambda:now[0]))
    monkeypatch.setattr(media,'DOWNLOAD_TIMEOUT',media.download_timeout_seconds(str(budget)))
    monkeypatch.setattr(media,'MAX_FILE',2)
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            now[0]=599;yield b'a'
            now[0]=601;yield b'b'
            if budget==600:
                raise AssertionError('Must check deadline without buffering more slow chunks')
    def request(req):
        if req.url.path.endswith('.m3u8'):
            return httpx.Response(200,text='#EXTM3U\n#EXTINF:2,\nclip.ts\n#EXT-X-ENDLIST\n')
        return httpx.Response(200,stream=Slow())
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        action=lambda:media.local_playlist(client,ORIGIN+'/index.m3u8',tmp_path) if hls else media.direct_media(client,ORIGIN+'/clip.mp4',tmp_path)
        if budget==600:
            with pytest.raises(ValueError,match='download_timeout'):action()
        else:
            path=action()
            assert (tmp_path/'fragment-00000.bin' if hls else path).read_bytes()==b'ab'


def test_candidate_read_does_not_hold_recovery_write_transaction(tmp_path,monkeypatch):
    from harness.library import store
    import sqlite3
    monkeypatch.setattr(store,'ROOT',tmp_path)
    old,_=store.ingest({'source_url':'https://example.org/old','title':'Old'})
    with store.connection() as c:
        c.execute("INSERT INTO media_jobs VALUES(?,'downloading',1,'',0)",(old,))
    real_select=media.select_candidates
    def observe(c,limit,retry_limited):
        assert not c.in_transaction
        # A different writer must be able to commit once recovery is done,
        # even before the potentially slow candidate read has started.
        with sqlite3.connect(tmp_path/'library.sqlite3',timeout=0.1) as writer:
            assert writer.execute('SELECT state FROM media_jobs WHERE item=?',(old,)).fetchone()[0]=='interrupted'
            writer.execute("INSERT INTO collection_runs(id,source,started,state) VALUES('other-worker','Test',0,'running')")
        return real_select(c,limit,retry_limited)
    monkeypatch.setattr(media,'select_candidates',observe)
    assert [r['id'] for r in media.recover_candidates(8)[0]]==[old]


def test_candidate_index_tracks_source_locator_changes(tmp_path,monkeypatch):
    from harness.library import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    record={'source_url':'https://example.org/entry','title':'Entry','media_status':'source_link'}
    identity,_=store.ingest(record)
    with store.connection() as c:assert media.select_candidates(c,8)==[]
    store.ingest({**record,'creative_structure':{'public_video_url':CDN+'/film.mp4'}})
    with store.connection() as c:assert [r['id'] for r in media.select_candidates(c,8)]==[identity]
    store.ingest(record)
    with store.connection() as c:assert media.select_candidates(c,8)==[]


@pytest.mark.parametrize('release_lock', [True, False])
def test_asset_registration_retries_busy_commit_atomically(tmp_path, monkeypatch, release_lock):
    import sqlite3
    from contextlib import contextmanager
    from harness.library import store
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    identity, _ = store.ingest({'source_url': 'https://example.org/complete', 'title': 'Complete'})
    with store.connection() as c:
        c.execute("INSERT INTO collection_runs(id,source,started,state) VALUES('recovery','cache',0,'running')")
        c.execute("INSERT INTO media_jobs VALUES(?,'downloading',1,'',0)", (identity,))
    asset = (identity, 'assets/ready.mp4', 'a' * 64, 123, 15, 1, 1280, 720, 0)
    blocker = sqlite3.connect(tmp_path / 'library.sqlite3')
    blocker.execute('BEGIN')
    blocker.execute('SELECT COUNT(*) FROM assets').fetchone()
    waits = []
    opened = []

    @contextmanager
    def immediate_connection():
        db = sqlite3.connect(tmp_path / 'library.sqlite3', timeout=0)
        opened.append(True)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def release(delay):
        waits.append(delay)
        # The failed COMMIT has rolled back all three database changes.
        assert blocker.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0
        assert blocker.execute("SELECT inserted FROM collection_runs WHERE id='recovery'").fetchone()[0] == 0
        if release_lock:
            blocker.rollback()
            blocker.close()

    try:
        with monkeypatch.context() as patches:
            patches.setattr(store, 'connection', immediate_connection)
            patches.setattr(media.time, 'sleep', release)
            if release_lock:
                assert media.record_asset('recovery', asset)
                assert len(opened) == 2 and waits == [1]
                assert not media.record_asset('recovery', asset)
            else:
                with pytest.raises(sqlite3.OperationalError):
                    media.record_asset('recovery', asset)
                assert len(opened) == 3 and waits == [1, 2]
    finally:
        if not release_lock:
            blocker.rollback()
            blocker.close()
    with store.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == int(release_lock)
        assert c.execute("SELECT inserted FROM collection_runs WHERE id='recovery'").fetchone()[0] == int(release_lock)
        assert c.execute('SELECT state FROM media_jobs').fetchone()[0] == ('completed' if release_lock else 'downloading')


def test_asset_registration_does_not_retry_readonly_database(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import contextmanager
    from harness.library import store
    path = tmp_path / 'read-only.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE assets(a,b,c,d,e,f,g,h,i)')
    opened = []

    @contextmanager
    def readonly_connection():
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
            opened.append(True)
            yield db

    monkeypatch.setattr(store, 'connection', readonly_connection)
    monkeypatch.setattr(media.time, 'sleep', lambda _: pytest.fail('Readonly writes must not be retried'))
    with pytest.raises(sqlite3.OperationalError) as caught:
        media.record_asset('recovery', tuple(range(9)))
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_READONLY
    assert opened == [True]
