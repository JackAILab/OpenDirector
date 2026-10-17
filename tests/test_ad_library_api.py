import types
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from harness.library import store
from harness.studio.library_api import install


def test_gate_account_isolation_and_saved_review(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    identity,_=store.ingest({'source_url':'https://example.org/ad','title':'商业广告','quality_evidence':[]})
    _source_identity,_=store.ingest({'source_url':'https://example.org/source','title':'官方来源','quality_evidence':[],'media_status':'source_link'})
    app=FastAPI()
    def gate(request):
        if request.cookies.get('access')!='yes':raise HTTPException(403)
    def auth(value):
        if value not in ('Bearer one','Bearer two'):raise HTTPException(401)
        return {'id':1 if value=='Bearer one' else 2}
    install(types.SimpleNamespace(app=app,require_site_access=gate,require_session=auth))
    with TestClient(app) as c:
        assert c.get('/creative/api/library').status_code==403
        c.cookies.set('access','yes')
        assert c.get('/creative/api/library').json()['total']==2
        url='/creative/api/library/'+identity+'/review'
        body={'version':0,'state':'selected','scores':{'craft':5},'tags':['产品微距'],'note':'画面出色'}
        assert c.post(url,json=body).status_code==401
        c.headers['Authorization']='Bearer one'
        assert c.post(url,json=body).json()['review']['version']==1
        assert c.post(url,json=body).status_code==409
        assert c.get('/creative/api/library?state=selected').json()['total']==1
        history='/creative/api/library/'+identity+'/history'
        assert c.get(history).json()['history'][0]['note']=='画面出色'
        assert c.get('/creative/api/library?local_only=true').json()['total']==0
        c.headers['Authorization']='Bearer two'
        assert c.get('/creative/api/library?state=selected').json()['total']==0
        metrics=c.get('/creative/api/library/status').json()
        assert metrics['reviewed']==0
        assert metrics['source_link']==1
        assert metrics['selected']==0
        assert metrics['review_queue']['state']=='ready'
        assert metrics['review_queue']['total_pending']==0
        assert metrics['review_queue']['training_eligible'] is False
        assert c.get(history).json()['history']==[]


def test_actual_duration_filters_boundaries_pagination_and_own_preferences(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    ids=[]
    for n,duration in enumerate((30,30.1,60,180,180.1,None)):
        identity,_=store.ingest({'source_url':f'https://example.org/{n}','title':f'参考{n}','duration':999})
        ids.append(identity)
        if duration is not None:
            with store.connection() as c:
                c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',(identity,f'assets/{identity}/film.mp4','hash',100,duration,1,1280,720,0))
    store.review_item(ids[0],1,0,'selected',{},[], '')
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,require_session=lambda h:{'id':1 if h=='Bearer one' else 2}))
    with TestClient(app) as c:
        for band,count in [('short',1),('standard',2),('extended',1),('long',1),('unknown',1)]:
            data=c.get('/creative/api/library',params={'duration_band':band}).json()
            assert data['total']==count
        first=c.get('/creative/api/library?duration_band=standard&limit=1').json()
        second=c.get('/creative/api/library?duration_band=standard&limit=1&offset=1').json()
        assert first['total']==second['total']==2
        assert first['items'][0]['id']!=second['items'][0]['id']
        assert c.get('/creative/api/library?duration_band=short').json()['items'][0]['duration']==30
        assert c.get('/creative/api/library?duration_band=unknown&local_only=true').json()['total']==0
        url='/creative/api/library?duration_band=short&state=selected'
        assert c.get(url,headers={'Authorization':'Bearer one'}).json()['total']==1
        assert c.get(url,headers={'Authorization':'Bearer two'}).json()['total']==0
        assert c.get('/creative/api/library?duration_band=invalid').status_code==422


def test_status_uses_latest_preferences_and_invalidates_only_reviewer_cache(tmp_path,monkeypatch):
    from harness.studio import library_api
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setattr(library_api,'_is_production_library',lambda:True)
    monkeypatch.setattr(library_api,'_STATUS_CACHE',{})
    queue={'state':'unavailable','analysis_pending':None,'semantic_review_pending':None,
           'total_pending':None,'training_eligible':False}
    monkeypatch.setattr(library_api,'_review_queue_summary',lambda:dict(queue))
    iid,_=store.ingest({'source_url':'https://example.org/preference','title':'Preference'})
    store.review_item(iid,1,0,'selected',{},[], '')
    store.review_item(iid,2,0,'selected',{},[], '')
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,
                                 require_session=lambda h:{'id':1 if h=='Bearer one' else 2}))
    with TestClient(app) as c:
        status='/creative/api/library/status'
        for user in ('one','two'):
            assert c.get(status,headers={'Authorization':'Bearer '+user}).json()['selected']==1
        second_cache=library_api._STATUS_CACHE[2]
        body={'version':1,'state':'rejected','scores':{},'tags':[],'note':''}
        response=c.post('/creative/api/library/'+iid+'/review',headers={'Authorization':'Bearer one'},json=body)
        assert response.status_code==200
        assert 1 not in library_api._STATUS_CACHE
        assert library_api._STATUS_CACHE[2] is second_cache
        own=c.get(status,headers={'Authorization':'Bearer one'}).json()
        assert own['selected']==0 and own['reviewed']==1
        assert own['source_link'] is None
        assert own['review_queue']['total_pending'] is None
        assert c.get(status,headers={'Authorization':'Bearer two'}).json()['selected']==1
        queue.update(state='ready',analysis_pending=8,semantic_review_pending=2,total_pending=10)
        assert c.get(status,headers={'Authorization':'Bearer one'}).json()['review_queue']['total_pending']==10


def test_status_projects_backup_scope_without_manifest_content(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connection() as c:
        for n,manifest in enumerate(('not-json',json.dumps({'scope':'metadata','items':'private count payload'}),
                json.dumps({'scope':'metadata+learning','files':{'private/path':{}},'private_note':'never expose'}))):
            c.execute('INSERT INTO backups VALUES(?,?,?,?,?)',(str(n),n+1,manifest,'verified','snapshots/'+str(n)))
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,require_session=lambda h:{'id':1}))
    with TestClient(app) as c:
        response=c.get('/creative/api/library/status')
        assert response.status_code==200
        assert [b['scope'] for b in response.json()['backups']]==['metadata+learning','metadata',None]
        assert 'private/path' not in response.text and 'never expose' not in response.text
        assert 'private count payload' not in response.text
        assert all('manifest' not in b for b in response.json()['backups'])


def test_resumed_full_backup_is_visible_beyond_recent_metadata_history(tmp_path,monkeypatch):
    import json
    from harness.studio import library_api
    monkeypatch.setattr(store,'ROOT',tmp_path)
    monkeypatch.setattr(library_api,'_is_production_library',lambda:True)
    monkeypatch.setattr(library_api,'_STATUS_CACHE',{})
    monkeypatch.setattr(library_api,'_review_queue_summary',lambda:{'state':'unavailable'})
    with store.connection() as db:
        for n in range(5):
            manifest={'scope':'full' if n==0 else 'metadata','items':100+n,
                      'files':{'private/path':{}},'private_note':'must not appear'}
            db.execute('INSERT INTO backups VALUES(?,?,?,?,?)',
                       (str(n),n+1,json.dumps(manifest),'verifying' if n==0 else 'verified',None))
        plan=db.execute("EXPLAIN QUERY PLAN SELECT id,created,state,remote_revision FROM backups WHERE state IN ('uploading','verifying') ORDER BY created DESC LIMIT 1").fetchall()
        assert any('COVERING INDEX backup_summary_active' in row[3] for row in plan)
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,require_session=lambda h:{'id':1}))
    with TestClient(app) as client:
        response=client.get('/creative/api/library/status')
        payload=response.json()
        assert [b['id'] for b in payload['backups']]==['4','3','2']
        active=payload['active_backup']
        assert (active['id'],active['scope'],active['state'],active['items'])==('0','full','verifying',100)
        assert 'private/path' not in response.text and 'must not appear' not in response.text
        before=library_api._backup_metadata.cache_info()
        with store.connection() as db:
            db.execute("UPDATE backups SET state='uploading' WHERE id='0'")
        library_api._STATUS_CACHE.clear()
        active=client.get('/creative/api/library/status').json()['active_backup']
        assert active['state']=='uploading' and active['items']==100
        assert library_api._backup_metadata.cache_info().hits>before.hits
        assert library_api._backup_metadata.cache_info().misses==before.misses
        with store.connection() as db:
            db.execute("UPDATE backups SET state='verified' WHERE id='0'")
        library_api._STATUS_CACHE.clear()
        assert client.get('/creative/api/library/status').json()['active_backup'] is None


def test_media_progress_survives_newer_source_runs_and_counts_only_current_failures(tmp_path,monkeypatch):
    from harness.studio import library_api
    monkeypatch.setattr(store,'ROOT',tmp_path)
    ids=[store.ingest({'title':'素材','source_url':f'https://example.org/media/{n}'})[0] for n in range(3)]
    with store.connection() as db:
        db.execute('INSERT INTO collection_runs(id,source,started,state,discovered,inserted) VALUES(?,?,?,?,?,?)',
                   ('media','本地视频缓存',10,'running',8,4))
        for n in range(9):
            db.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',
                       (str(n),'官方来源',20+n,'completed'))
        for iid,state,updated in zip(ids,['failed','failed','downloading'],[9,11,12]):
            db.execute('INSERT INTO media_jobs VALUES(?,?,?,?,?)',(iid,state,1,'private provider detail',updated))
        plan=db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*) FROM media_jobs WHERE state='failed' AND updated>=10").fetchall()
        assert any('COVERING INDEX media_job_update' in r[3] for r in plan)
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,require_session=lambda h:{'id':1}))
    with TestClient(app) as client:
        response=client.get('/creative/api/library/status');data=response.json()
        assert len(data['runs'])==8 and all(r['id']!='media' for r in data['runs'])
        assert (data['media_cache']['inserted'],data['media_cache']['discovered'],data['media_cache']['failed'])==(4,8,1)
        assert 'private provider detail' not in response.text
        with store.connection() as db:
            db.execute("UPDATE collection_runs SET state='partial',finished=30 WHERE id='media'")
            db.execute("UPDATE media_jobs SET updated=40,state='failed'")
        library_api._STATUS_CACHE.clear()
        data=client.get('/creative/api/library/status').json()
        assert data['media_cache']['state']=='partial' and data['media_cache']['failed'] is None


def test_preparing_backup_counts_stay_live_until_manifest_is_final(tmp_path,monkeypatch):
    import json
    from harness.studio import library_api
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connection() as db:
        db.execute('INSERT INTO backups VALUES(?,?,?,?,?)',
                   ('preparing-full',1,json.dumps({'scope':'full'}),'preparing',None))
        plan=db.execute("EXPLAIN QUERY PLAN SELECT id,created,state,remote_revision FROM backups WHERE state IN ('preparing','uploading','verifying') ORDER BY created DESC LIMIT 1").fetchall()
        assert any('COVERING INDEX backup_summary_in_progress' in row[3] for row in plan)
    app=FastAPI()
    install(types.SimpleNamespace(app=app,require_site_access=lambda r:None,require_session=lambda h:{'id':1}))
    with TestClient(app) as client:
        for state,items in [('preparing',None),('preparing',3),('uploading',5)]:
            manifest={'scope':'full','files':{'private/path':{'note':'must not appear'}}}
            if items is not None:manifest['items']=items
            with store.connection() as db:
                db.execute('UPDATE backups SET state=?,manifest=? WHERE id=?',
                           (state,json.dumps(manifest),'preparing-full'))
            library_api._STATUS_CACHE.clear()
            response=client.get('/creative/api/library/status')
            active=response.json()['active_backup']
            assert (active['scope'],active['state'],active['items'])==('full',state,items)
            assert 'private/path' not in response.text and 'must not appear' not in response.text
        with store.connection() as db:db.execute("UPDATE backups SET state='verified'")
        library_api._STATUS_CACHE.clear()
        final=client.get('/creative/api/library/status').json()
        assert final['active_backup'] is None and final['backups'][0]['items']==5


def test_backup_progress_is_auth_gated_and_never_overrides_database_state(tmp_path,monkeypatch):
    import json
    from harness.library.backup_progress import write_progress
    from harness.studio import library_api
    monkeypatch.setattr(store,'ROOT',tmp_path/'library')
    monkeypatch.setenv('AD_LIBRARY_PROGRESS_ROOT',str(tmp_path/'progress'))
    identity='20261014T220000Z-1234abcd'
    with store.connection() as db:
        db.execute('INSERT INTO backups VALUES(?,?,?,?,?)',
                   (identity,1,json.dumps({'scope':'metadata+learning','items':8}),'preparing',None))
    event={'snapshot':identity,'state':'preparing','phase':'learning_evidence',
           'processed_analysis_versions':2,'total_analysis_versions':3,
           'copied_learning_files':27,'private_path':'must never appear'}
    write_progress(store.ROOT,event)
    app=FastAPI()
    def gate(request):
        if request.cookies.get('access')!='yes':raise HTTPException(403)
    install(types.SimpleNamespace(app=app,require_site_access=gate,require_session=lambda h:{'id':1}))
    with TestClient(app) as client:
        endpoint='/creative/api/library/status'
        assert client.get(endpoint).status_code==403
        client.cookies.set('access','yes')
        response=client.get(endpoint)
        active=response.json()['active_backup']
        assert active['state']=='preparing'
        assert active['progress']['processed_analysis_versions']==2
        assert 'must never appear' not in response.text
        # A newer phase must not display a previous phase's completed count.
        with store.connection() as db:db.execute("UPDATE backups SET state='verifying'")
        library_api._STATUS_CACHE.clear()
        assert client.get(endpoint).json()['active_backup']['progress'] is None
        write_progress(store.ROOT,{'snapshot':identity,'state':'verifying','verified_files':4,'total_files':4})
        assert client.get(endpoint).json()['active_backup']['state']=='verifying'
        with store.connection() as db:db.execute("UPDATE backups SET state='verified'")
        library_api._STATUS_CACHE.clear()
        payload=client.get(endpoint).json()
        assert payload['active_backup'] is None
        assert payload['backups'][0]['progress'] is None


def test_exact_file_grouping_preserves_filters_and_separate_preferences(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(store,'ROOT',tmp_path)
    ids=[]
    for n in range(6):
        identity,_=store.ingest({'source_url':f'https://example.org/source/{n}',
            'title':'原版广告' if n==0 else '同名广告', 'brand':'同一品牌',
            'industry':'食品饮料' if n==0 else '其他', 'source_name':f'奖项来源 {n}'})
        ids.append(identity)
        with store.connection() as db:
            db.execute('UPDATE items SET created=? WHERE id=?',(n,identity))
            if n!=3:
                checksum='a'*64 if n<2 else 'b'*64 if n==2 else 'legacy-invalid'
                db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                    (identity,f'assets/{identity}/film.mp4',checksum,100,30,1,1280,720,0))
    store.review_item(ids[0],1,0,'selected',{'craft':5},['私有标签'],'only user one')
    store.review_item(ids[1],2,0,'rejected',{},[],'only user two')
    with store.connection() as db:
        prior=[tuple(row) for row in db.execute('SELECT * FROM reviews ORDER BY seq')]
    app=FastAPI()
    def gate(request):
        if request.cookies.get('access')!='yes':raise HTTPException(403)
    install(types.SimpleNamespace(app=app,require_site_access=gate,
        require_session=lambda value:{'id':1 if value=='Bearer one' else 2}))
    with TestClient(app) as client:
        related='/creative/api/library/'+ids[0]+'/same-video'
        assert client.get(related).status_code==403
        client.cookies.set('access','yes')
        url='/creative/api/library'
        grouped=client.get(url,params={'unique_media':True}).json()
        assert grouped['total']==5  # one verified duplicate pair, invalid/unknown remain separate
        returned={i['id'] for i in grouped['items']}
        assert ids[0] not in returned and ids[1] in returned
        assert set(ids[2:]).issubset(returned)  # titles and brands never identify a file
        assert client.get(url).json()['total']==6
        assert client.get(url,params={'unique_media':True,'local_only':True}).json()['total']==4
        for filters in ({'industry':'食品饮料'}, {'q':'原版广告'}, {'state':'selected'}):
            data=client.get(url,params={'unique_media':True,**filters},headers={'Authorization':'Bearer one'}).json()
            assert data['total']==1 and data['items'][0]['id']==ids[0]
        assert client.get(url,params={'unique_media':True,'state':'selected'},headers={'Authorization':'Bearer two'}).json()['total']==0
        pages=[client.get(url,params={'unique_media':True,'limit':2,'offset':n}).json() for n in (0,2,4)]
        assert {page['total'] for page in pages}=={5}
        all_ids=[item['id'] for page in pages for item in page['items']]
        assert len(all_ids)==len(set(all_ids))==5
        metrics=client.get(url+'/status').json()
        assert metrics['playable']==5 and metrics['distinct_playable']==4
        guest=client.get(related).json()
        assert guest['total']==2 and all(i['review_state']=='pending' for i in guest['items'])
        own=client.get(related,headers={'Authorization':'Bearer one'}).json()
        other=client.get(related,headers={'Authorization':'Bearer two'}).json()
        assert {i['id']:i['review_state'] for i in own['items']}=={ids[0]:'selected',ids[1]:'pending'}
        assert {i['id']:i['review_state'] for i in other['items']}=={ids[0]:'pending',ids[1]:'rejected'}
        for result in (guest,own,other):
            for item in result['items']:
                assert set(item)=={'id','title','source_url','source_name','review_state'}
            assert 'only user' not in json.dumps(result)
        assert client.get(url+'/'+ids[3]+'/same-video').json()=={'total':0,'items':[]}
        assert client.get(url+'/'+ids[4]+'/same-video').json()=={'total':0,'items':[]}
        assert client.get(url+'/missing/same-video').status_code==404
    with store.connection() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM reviews ORDER BY seq')]==prior
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0]==6
        assert all(json.loads(row[0])['training_eligible'] is False for row in db.execute('SELECT data FROM items'))


def test_same_file_sources_are_bounded(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    for n in range(25):
        identity,_=store.ingest({'source_url':f'https://example.org/group/{n}','title':'广告'})
        with store.connection() as db:
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                (identity,'not-exposed','c'*64,100,15,1,1280,720,n))
    result=store.same_video_sources(identity,1,limit=10000)
    assert result['total']==25 and len(result['items'])==20
    assert all('path' not in item and 'sha256' not in item for item in result['items'])
