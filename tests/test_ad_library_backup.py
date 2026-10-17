import json
import hashlib
import time
import shutil
import sqlite3
from pathlib import Path
import pytest
from harness.library import store
from harness.tools.reference_backup import backup


def test_metadata_backup_counts_frozen_preferences_and_skill_history(tmp_path,monkeypatch):
    from harness.tools.reference_backup import verify_files
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    iid,_=store.ingest({'title':'Reference','source_url':'https://example.org/film'})
    store.review_item(iid,77,0,'selected',{'craft':4},[],'Human preference')
    with store.connection() as db:
        db.execute('CREATE TABLE reference_skill_versions(id TEXT,version INTEGER,data TEXT,created REAL,PRIMARY KEY(id,version))')
        db.execute('CREATE TABLE reference_skill_releases(id TEXT PRIMARY KEY,manifest TEXT,created REAL)')
        db.executemany('INSERT INTO reference_skill_versions VALUES(?,?,?,?)',
                       [('skill',1,'{}',1),('skill',2,'{}',2)])
        db.execute('INSERT INTO reference_skill_releases VALUES(?,?,?)',('release','{}',1))
    class Transport:
        def upload(self,folder,identity):
            self.folder=folder
            self.manifest=json.loads((folder/'manifest.json').read_text())
            assert self.manifest['record_counts']=={'human_reviews':1,'reference_skill_versions':2,'reference_skill_releases':1}
            # A concurrent new live version must not change the frozen snapshot's count.
            with store.connection() as db:db.execute('INSERT INTO reference_skill_versions VALUES(?,?,?,?)',('skill',3,'{}',3))
        def download(self,name,identity,directory):
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            if name=='manifest.json':target.write_text(json.dumps(self.manifest))
            else:shutil.copyfile(self.folder/name,target)
            return target
    transport=Transport();result=backup(transport,include_media=False,include_learning=False)
    assert result['state']=='verified'
    restored=store.ROOT/'restore_checks'/result['snapshot']/'library.sqlite3'
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT note FROM reviews').fetchone()[0]=='Human preference'
        assert db.execute('SELECT COUNT(*) FROM reference_skill_versions').fetchone()[0]==2
    for field in transport.manifest['record_counts']:
        transport.manifest['record_counts'][field]+=1
        directory=tmp_path/field;directory.mkdir()
        with pytest.raises(RuntimeError,match='restore_count_mismatch'):
            verify_files(transport,result['snapshot'],transport.manifest,directory)
        transport.manifest['record_counts'][field]-=1


@pytest.mark.parametrize('record_counts',[None,[],{}, {'human_reviews':False,'reference_skill_versions':0,'reference_skill_releases':0}])
def test_record_count_manifest_must_be_complete_typed_counts(tmp_path,record_counts):
    from harness.tools.reference_backup import verify_files
    source=tmp_path/'source.sqlite3'
    with sqlite3.connect(source) as db:db.execute('CREATE TABLE items(id TEXT)')
    payload=source.read_bytes()
    manifest={'items':0,'record_counts':record_counts,'files':{'library.sqlite3':{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}}
    class Transport:
        def download(self,name,identity,directory):
            target=directory/name
            if name=='manifest.json':target.write_text(json.dumps(manifest))
            else:target.write_bytes(payload)
            return target
    with pytest.raises(RuntimeError,match='invalid_snapshot_manifest'):
        verify_files(Transport(),'snapshot',manifest,tmp_path)


def test_readback_retries_bounded_transport_error_at_same_identity(tmp_path,monkeypatch):
    from harness.tools import reference_backup as action
    monkeypatch.setattr(action.time,'sleep',lambda _:None)
    content=b'checked remote bytes'
    manifest={'files':{'poster.jpg':{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}}}
    class Transport:
        calls=[]
        def download(self,name,identity,directory):
            self.calls.append((name,identity))
            if name=='poster.jpg' and self.calls.count((name,identity))==1:
                raise RuntimeError('remote_download_unavailable')
            target=directory/name
            target.write_text(json.dumps(manifest)) if name=='manifest.json' else target.write_bytes(content)
            return target
    transport=Transport()
    action.verify_files(transport,'fixed-snapshot',manifest,tmp_path)
    assert transport.calls==[('manifest.json','fixed-snapshot'),('poster.jpg','fixed-snapshot'),('poster.jpg','fixed-snapshot')]


@pytest.mark.parametrize('workers', [1, 4])
def test_backup_snapshot_restore_and_no_secret_sweep(tmp_path,monkeypatch,workers):
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    iid,_=store.ingest({'title':'案例','source_url':'https://example.org/film'})
    relative=f'assets/{iid}/film.mp4'
    media=store.ROOT/relative;media.parent.mkdir(parents=True);media.write_bytes(b'video-fixture'*100000)
    (media.parent/'poster.jpg').write_bytes(b'poster-fixture')
    checksum=hashlib.sha256(media.read_bytes()).hexdigest()
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',(iid,relative,checksum,media.stat().st_size,15,1,1280,720,time.time()))
    (store.ROOT/'do-not-upload-secret.txt').write_text('private-value')
    class Transport:
        def fork_for_readback(self,identity):
            import copy
            return copy.copy(self)
        def upload(self,folder,identity):
            self.folder=folder
            with store.connection() as c:assert c.execute('select state from backups where id=?',(identity,)).fetchone()[0]=='uploading'
            assert not (folder/'do-not-upload-secret.txt').exists()
            assert len((folder/'items.jsonl').read_text().splitlines())==1
            manifest=json.loads((folder/'manifest.json').read_text())
            assert manifest['files'][relative]['sha256']==checksum
            assert manifest['files'][relative]['bytes']==media.stat().st_size
            assert (folder/relative).read_bytes()==media.read_bytes()
            assert (folder/relative).with_name('poster.jpg').is_file()
            assert not list(folder.rglob('*.part'))
        def download(self,name,identity,directory):
            with store.connection() as c:assert c.execute('select state from backups where id=?',(identity,)).fetchone()[0]=='verifying'
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.folder/name,target);return target
    result=backup(Transport(),readback_workers=workers);assert result['state']=='verified' and result['items']==1
    with store.connection() as c:assert c.execute('select state from backups').fetchone()[0]=='verified'
    class Corrupt(Transport):
        def download(self,name,identity,directory):
            p=super().download(name,identity,directory)
            if name==relative:p.write_bytes(b'corrupt')
            return p
    with pytest.raises(RuntimeError):backup(Corrupt(),readback_workers=workers)
    with store.connection() as c:assert c.execute('select state from backups order by created desc limit 1').fetchone()[0]=='failed'


def test_retention_only_removes_old_verified_managed_copies(tmp_path,monkeypatch):
    from harness.tools.reference_backup import retain_verified
    monkeypatch.setattr(store,'ROOT',tmp_path)
    ids=[f'20261001T020000Z-{i:08x}' for i in range(10)]
    with store.connection() as c:
        for i,identity in enumerate(ids):
            c.execute('INSERT INTO backups(id,created,manifest,state) VALUES(?,?,?,?)',(identity,i,'{}','verified'))
            for name in ('snapshots','restore_checks'):(tmp_path/name/identity).mkdir(parents=True)
    failed=tmp_path/'snapshots'/'failed-copy';failed.mkdir()
    retain_verified()
    assert len(list((tmp_path/'snapshots').iterdir()))==9
    assert len(list((tmp_path/'restore_checks').iterdir()))==2
    assert failed.is_dir()
    assert all((tmp_path/'snapshots'/i).is_dir() for i in ids[-8:])


def test_copy_checked_rejects_corrupt_source_without_publishing(tmp_path):
    from harness.tools.reference_backup import copy_checked
    source=tmp_path/'source.mp4';source.write_bytes(b'corrupted source')
    target=tmp_path/'snapshot'/'film.mp4'
    with pytest.raises(RuntimeError,match='source_asset_checksum_failed'):
        copy_checked(source,target,hashlib.sha256(b'expected source').hexdigest())
    assert not target.exists() and not target.with_name('film.mp4.part').exists()
    assert source.read_bytes()==b'corrupted source'


@pytest.mark.parametrize('phase', ['database', 'learning', 'media'])
def test_preparation_failure_has_receipt_without_upload_or_private_details(tmp_path,monkeypatch,caplog,phase):
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    iid,_=store.ingest({'title':'案例','source_url':'https://example.org/preparation'})
    relative=f'assets/{iid}/film.mp4'
    media=store.ROOT/relative;media.parent.mkdir(parents=True);media.write_bytes(b'media')
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                  (iid,relative,hashlib.sha256(b'media').hexdigest(),5,15,1,1280,720,time.time()))
    def fail(*args,**kwargs):
        with store.connection() as c:
            row=c.execute("SELECT state,manifest FROM backups ORDER BY created DESC LIMIT 1").fetchone()
        assert row[0]=='preparing'
        summary=json.loads(row[1])
        assert summary['scope']=='full' and summary['media_complete'] is False
        assert summary.get('items')==(None if phase=='database' else 1)
        raise OSError('private upstream details')
    if phase=='database':monkeypatch.setattr(action,'copy_sqlite_snapshot',fail)
    elif phase=='learning':monkeypatch.setattr(action,'snapshot_learning',fail)
    else:
        copy=action.copy_checked
        monkeypatch.setattr(action,'copy_checked',lambda source,*args,**kw:
                            fail() if Path(source)==media else copy(source,*args,**kw))
    class Transport:
        def upload(self,*args):pytest.fail('An incomplete snapshot must not upload')
    progress=[]
    with pytest.raises(RuntimeError,match='backup_failed; local_snapshot_preserved'):
        backup(Transport(),progress=progress.append)
    with store.connection() as c:
        rows=c.execute('SELECT state,manifest,remote_revision FROM backups').fetchall()
    assert len(rows)==1 and rows[0][0]=='failed' and rows[0][2] is None
    assert 'private upstream details' not in caplog.text+rows[0][1]+json.dumps(progress)
    assert progress[0]['state']=='preparing'
    assert media.read_bytes()==b'media'


def test_preparation_recovery_requires_exclusive_backup_lock(tmp_path,monkeypatch):
    import fcntl
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connection() as c:
        c.execute('INSERT INTO backups VALUES(?,?,?,?,?)',('old',1,'{}','preparing',None))
    with (tmp_path/'.backup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert backup(object())=={'state':'already_running'}
        with store.connection() as c:
            assert c.execute("SELECT state FROM backups WHERE id='old'").fetchone()[0]=='preparing'
    def fail(*args):raise OSError('unavailable')
    monkeypatch.setattr(action,'copy_sqlite_snapshot',fail)
    with pytest.raises(RuntimeError,match='backup_failed'):backup(object())
    with store.connection() as c:
        assert c.execute("SELECT state FROM backups WHERE id='old'").fetchone()[0]=='interrupted'
        assert c.execute("SELECT state FROM backups WHERE id!='old'").fetchone()[0]=='failed'


def test_space_preflight_stops_full_copy_but_preserves_metadata_backup(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    iid,_=store.ingest({'title':'空间检查','source_url':'https://example.org/space'})
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                  (iid,f'assets/{iid}/film.mp4','a'*64,4*1024**3,15,1,1280,720,time.time()))
    monkeypatch.setattr(action.shutil,'disk_usage',lambda _:SimpleNamespace(free=3*1024**3))
    class Transport:
        uploads=0
        def upload(self,folder,identity):self.folder=folder;self.uploads+=1
        def download(self,name,identity,directory):
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.folder/name,target);return target
    transport=Transport()
    with pytest.raises(RuntimeError,match='^backup_space_limit$'):backup(transport)
    with store.connection() as c:
        assert c.execute('SELECT state FROM backups').fetchone()[0]=='failed'
    assert transport.uploads==0 and not (store.ROOT/'snapshots').exists()
    result=backup(transport,include_media=False,include_learning=False)
    assert result['state']=='verified' and transport.uploads==1
    assert not (transport.folder/'assets').exists()
    with store.connection() as c:assert c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==1


def test_learning_preflight_keeps_working_space_before_copying(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connection():pass
    monkeypatch.setattr(action.shutil,'disk_usage',lambda _:SimpleNamespace(free=1024**3))
    assert action.check_snapshot_space(False,False)>0
    with pytest.raises(RuntimeError,match='backup_space_limit'):
        action.check_snapshot_space(False,True)


def test_resume_failed_readback_reuses_checked_files_without_upload(tmp_path,monkeypatch):
    from harness.tools.reference_backup import resume_verification
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    store.ingest({'title':'案例','source_url':'https://example.org/resume'})
    class Transport:
        uploads=0;failed=False;calls=[]
        def upload(self,folder,identity):
            self.uploads+=1;self.folder=folder;self.identity=identity
            self.last=list(json.loads((folder/'manifest.json').read_text())['files'])[-1]
        def download(self,name,identity,directory):
            self.calls.append(name)
            if name==self.last and not self.failed:
                self.failed=True;raise ConnectionError('private upstream details')
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.folder/name,target);return target
    transport=Transport()
    with pytest.raises(RuntimeError):backup(transport)
    result=resume_verification(transport,transport.identity)
    assert result['state']=='verified' and result['reused_files']==result['verified_files']-1
    assert transport.uploads==1
    # A damaged local restoration copy must be fetched again, never trusted.
    (store.ROOT/'restore_checks'/transport.identity/'items.jsonl').write_bytes(b'corrupted cache')
    result=resume_verification(transport,transport.identity)
    assert result['state']=='verified' and transport.uploads==1
    with store.connection() as c:assert c.execute('select state from backups').fetchone()[0]=='verified'


def test_resume_refuses_changed_remote_manifest(tmp_path,monkeypatch):
    from harness.tools.reference_backup import resume_verification
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    store.ingest({'title':'案例','source_url':'https://example.org/manifest'})
    class Transport:
        changed=False
        def upload(self,folder,identity):self.folder=folder;self.identity=identity
        def download(self,name,identity,directory):
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.folder/name,target)
            if name=='manifest.json' and self.changed:
                data=json.loads(target.read_text());data['items']+=1;target.write_text(json.dumps(data))
            return target
    transport=Transport();backup(transport);transport.changed=True
    with pytest.raises(RuntimeError,match='remote_manifest_mismatch'):
        resume_verification(transport,transport.identity)
    with store.connection() as c:assert c.execute('select state from backups').fetchone()[0]=='failed'


def test_transport_retries_only_transient_download_errors(monkeypatch,tmp_path):
    import types
    from harness.models import reference_backup as adapter
    errors=pytest.importorskip('modelscope_hub.errors')
    monkeypatch.setattr(adapter.time,'sleep',lambda _:None)
    transport=adapter.ModelScopeBackup();calls=[]
    def request(*args,**kwargs):
        calls.append((args,kwargs))
        if len(calls)<3:raise errors.NetworkError('private details')
        return tmp_path/'downloaded'
    transport.api=types.SimpleNamespace(download_file=request)
    assert transport.download('film.mp4','snapshot',tmp_path)==tmp_path/'downloaded'
    assert len(calls)==3 and calls[0]==calls[1]==calls[2]
    def invalid(*args,**kwargs):
        calls.append((args,kwargs));raise errors.FileIntegrityError('private details')
    transport.api.download_file=invalid;calls.clear()
    with pytest.raises(RuntimeError,match='remote_file_integrity_failed'):
        transport.download('film.mp4','snapshot',tmp_path)
    assert len(calls)==1


def test_missing_download_retries_only_when_listing_proves_presence(monkeypatch,tmp_path):
    import types
    from harness.models import reference_backup as adapter
    errors=pytest.importorskip('modelscope_hub.errors')
    monkeypatch.setattr(adapter.time,'sleep',lambda _:None)
    t=adapter.ModelScopeBackup();calls=[];present=True
    def listing(*args,**kw):return [{'Path':'snapshots/test/film.mp4'}] if present else []
    def request(*args,**kwargs):
        calls.append((args,kwargs))
        if len(calls)<3 or not present:raise errors.NotExistError('private details')
        return tmp_path/'downloaded'
    t.api=types.SimpleNamespace(download_file=request,legacy=types.SimpleNamespace(list_repo_files=listing))
    monkeypatch.setattr(t,'connect',lambda:None)
    assert t.download('film.mp4','test',tmp_path)==tmp_path/'downloaded'
    assert len(calls)==3 and calls[0]==calls[1]==calls[2]
    present=False;calls.clear()
    with pytest.raises(RuntimeError,match='remote_file_missing'):t.download('film.mp4','test',tmp_path)
    assert len(calls)==1
    present=True;calls.clear()
    def inconsistent(*args,**kwargs):
        calls.append((args,kwargs));raise errors.NotExistError('private details')
    t.api.download_file=inconsistent
    with pytest.raises(RuntimeError,match='remote_download_inconsistent'):
        t.download('film.mp4','test',tmp_path)
    assert len(calls)==3


def test_small_missing_file_detected_without_listing_before_large_media(tmp_path):
    from harness.tools.reference_backup import verify_files
    manifest={'files':{'film.mp4':{'bytes':5,'sha256':'unused'},'poster.jpg':{'bytes':1,'sha256':'unused'}}}
    class Transport:
        calls=[]
        def download(self,name,identity,directory):
            self.calls.append(name)
            if name!='manifest.json':raise RuntimeError('remote_file_missing')
            p=directory/name;p.write_text(json.dumps(manifest));return p
        def inventory(self,identity):raise AssertionError('verification must not list directories')
    t=Transport()
    with pytest.raises(RuntimeError,match='remote_file_missing'):
        verify_files(t,'snapshot',manifest,tmp_path,reuse=True)
    assert t.calls==['manifest.json','poster.jpg']


def test_inventory_presence_does_not_replace_content_checks(tmp_path):
    from harness.tools.reference_backup import verify_files
    manifest={'files':{'film.mp4':{'bytes':5,'sha256':hashlib.sha256(b'valid').hexdigest()}}}
    class Transport:
        def inventory(self,identity):return {'film.mp4'}
        def download(self,name,identity,directory):
            p=directory/name
            p.write_text(json.dumps(manifest)) if name=='manifest.json' else p.write_bytes(b'wrong')
            return p
    with pytest.raises(RuntimeError,match='remote_checksum_mismatch'):
        verify_files(Transport(),'snapshot',manifest,tmp_path)


def test_unlisted_file_requires_actual_download_and_checksum(tmp_path):
    from harness.tools.reference_backup import verify_files
    manifest={'files':{'poster.jpg':{'bytes':5,'sha256':hashlib.sha256(b'valid').hexdigest()}}}
    class Transport:
        calls=[]
        def inventory(self,identity):return set()
        def download(self,name,identity,directory):
            self.calls.append(name);p=directory/name
            p.write_text(json.dumps(manifest)) if name=='manifest.json' else p.write_bytes(b'valid')
            return p
    t=Transport();assert verify_files(t,'snapshot',manifest,tmp_path)==0
    assert t.calls==['manifest.json','poster.jpg']


def test_pinned_commit_is_used_for_listing_and_every_download(monkeypatch,tmp_path):
    import types
    from harness.models.reference_backup import ModelScopeBackup
    identity='20261001T224814Z-46b48a69';revision='a'*40
    t=ModelScopeBackup(revisions_dir=tmp_path/'pins');t.record_revision(identity,revision)
    calls=[]
    def listing(*args,**kw):
        calls.append(('list',kw));return [{'Path':'snapshots/'+identity+'/poster.jpg'}]
    def download(*args,**kw):
        calls.append(('download',kw));return tmp_path/'poster.jpg'
    t.api=types.SimpleNamespace(legacy=types.SimpleNamespace(list_repo_files=listing),download_file=download)
    assert t.inventory(identity)=={'poster.jpg'}
    assert t.download('poster.jpg',identity,tmp_path)==tmp_path/'poster.jpg'
    assert all(kw['revision']==revision for _,kw in calls)
    assert calls[1][1]['force'] is True
    # Corrupt pins fail closed, rather than reading the changing default branch.
    (tmp_path/'pins'/(identity+'.json')).write_text(json.dumps({'snapshot':identity,'revision':'master'}))
    with pytest.raises(RuntimeError,match='invalid_remote_revision'):t.inventory(identity)
    assert len(calls)==2


def test_upload_pins_final_commit_and_never_sync_deletes(monkeypatch,tmp_path):
    import types
    from harness.models.reference_backup import ModelScopeBackup
    identity='20261001T224814Z-46b48a69';calls=[]
    t=ModelScopeBackup(revisions_dir=tmp_path/'pins')
    def upload(*args,**kw):
        calls.append(kw);return [{'commit_id':'a'*40},{'commit_id':'b'*40}]
    t.api=types.SimpleNamespace(upload_folder=upload)
    monkeypatch.setattr(t,'connect',lambda:None)
    t.upload(tmp_path,identity)
    assert t.revision_for(identity)=='b'*40
    assert calls[0]['sync_remote_repo'] is False


def test_learning_only_restores_analysis_and_cited_frames_without_original_media(tmp_path, monkeypatch):
    import sqlite3
    from harness.library import learning
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'data')
    iid, _ = store.ingest({'title': '参考案例', 'source_url': 'https://example.org/learning'})
    media = store.ROOT / 'assets' / iid / 'film.mp4'
    media.parent.mkdir(parents=True)
    media.write_bytes(b'original media excluded from this scope')
    sha = hashlib.sha256(media.read_bytes()).hexdigest()
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                  (iid, str(media.relative_to(store.ROOT)), sha, media.stat().st_size, 15, 1, 1280, 720, time.time()))
    evidence = store.ROOT / 'learning/evidence' / iid
    evidence.mkdir(parents=True)
    details = {'media_sha256': sha, 'frames': [{'path': '00.jpg', 'time': 1}]}
    (evidence / 'evidence.json').write_text(json.dumps(details))
    (evidence / '00.jpg').write_bytes(b'cited frame')
    (evidence / 'candidate.json').write_text('{"private":"not part of backup"}')
    (evidence / 'analysis-attempt.json').write_text('{"state":"completed"}')
    learning.save_analysis(iid, sha, 1, 'test-model', {'training_eligible': False}, [1])

    class Transport:
        def upload(self, folder, identity):
            import tarfile
            self.folder = folder
            self.manifest = json.loads((folder / 'manifest.json').read_text())
            assert self.manifest['scope'] == 'metadata+learning'
            assert self.manifest['learning_complete'] is True
            assert self.manifest['media_complete'] is False
            assert self.manifest['analyses'] == 1
            assert not (folder / 'assets').exists()
            assert not list(folder.rglob('candidate.json'))
            assert not list(folder.rglob('analysis-attempt.json'))
            assert not (folder / 'learning').exists()
            expected = {'learning/analyses.sqlite3', f'learning/evidence/{iid}/00.jpg',
                        f'learning/evidence/{iid}/evidence.json'}
            assert set(self.manifest['learning_members']) == expected
            # Checking only the loose files misses private content inside tar.
            with tarfile.open(folder / 'learning.bundle.tar') as archive:
                assert set(archive.getnames()) == expected
                for member in archive.getmembers():
                    assert member.isfile() and member.mode == 0o600
                    assert (member.uid, member.gid, member.uname, member.gname, member.mtime) == (0, 0, '', '', 0)
            assert set(self.manifest['files']) == {'library.sqlite3', 'items.jsonl',
                                                  'preferences.jsonl', 'learning.bundle.tar'}

        def download(self, name, identity, directory):
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.folder / name, target)
            return target

    transport = Transport()
    # A real directory-service outage must not prevent creating and restoring
    # the bundle. This fails if TarFile.add/gettarinfo is reintroduced.
    import tarfile
    def unexpected_lookup(*args):
        raise AssertionError('Learning archives must not resolve system account names')
    progress=[]
    with monkeypatch.context() as lookups:
        if tarfile.pwd is not None:
            lookups.setattr(tarfile.pwd, 'getpwuid', unexpected_lookup)
        if tarfile.grp is not None:
            lookups.setattr(tarfile.grp, 'getgrgid', unexpected_lookup)
        result = backup(transport, include_media=False, include_learning=True, progress=progress.append)
    assert result['state'] == 'verified'
    learning_progress=[p for p in progress if p.get('phase','').startswith('learning_') and p['state']=='preparing']
    assert learning_progress[-1]['phase']=='learning_snapshot_ready'
    assert all(p['snapshot']==result['snapshot'] for p in learning_progress)
    restored = store.ROOT / 'restore_checks' / result['snapshot'] / 'learning'
    assert (restored / 'evidence' / iid / '00.jpg').read_bytes() == b'cited frame'
    with sqlite3.connect(restored / 'analyses.sqlite3') as c:
        assert c.execute('SELECT item,media_sha256 FROM analyses').fetchone() == (iid, sha)


def test_learning_bundle_uses_frozen_database_even_when_live_source_changes(tmp_path, monkeypatch):
    import sqlite3
    import tarfile
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'data')
    evidence = store.ROOT / 'learning/evidence' / ('a' * 24)
    evidence.mkdir(parents=True)
    (evidence / 'evidence.json').write_text(json.dumps({'media_sha256': 'b' * 64, 'frames': []}))
    live = store.ROOT / 'learning/analyses.sqlite3'
    with sqlite3.connect(live) as c:
        c.execute('CREATE TABLE analyses(item TEXT,media_sha256 TEXT)')
        c.execute('INSERT INTO analyses VALUES(?,?)', ('a' * 24, 'b' * 64))
    real_copy = action.copy_checked
    def mutate_after_database_snapshot(source, destination, expected=None):
        if Path(source).name == 'evidence.json':
            with sqlite3.connect(live) as c:
                c.execute('DELETE FROM analyses')
        return real_copy(source, destination, expected)
    monkeypatch.setattr(action, 'copy_checked', mutate_after_database_snapshot)
    folder = tmp_path / 'snapshot'; folder.mkdir()
    count, members = action.snapshot_learning(folder)
    assert count == 1
    with tarfile.open(folder / 'learning.bundle.tar') as archive:
        data = archive.extractfile('learning/analyses.sqlite3').read()
    restored = tmp_path / 'restored.sqlite3'; restored.write_bytes(data)
    assert hashlib.sha256(data).hexdigest() == members['learning/analyses.sqlite3']['sha256']
    with sqlite3.connect(restored) as c:
        assert c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0] == 1
    with sqlite3.connect(live) as c:
        assert c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0] == 0


@pytest.fixture
def learning_progress_fixture(tmp_path,monkeypatch):
    from harness.tools import reference_backup as action
    monkeypatch.setattr(store,'ROOT',tmp_path/'data')
    for identity in ('a'*24,'c'*24):
        folder=store.ROOT/'learning/evidence'/identity
        folder.mkdir(parents=True)
        (folder/'evidence.json').write_text(json.dumps({'media_sha256':'b'*64,
            'frames':[{'path':'00.jpg'},{'path':'01.jpg'}]}))
        for name in ('00.jpg','01.jpg'):(folder/name).write_bytes(b'frame bytes')
    with sqlite3.connect(store.ROOT/'learning/analyses.sqlite3') as db:
        db.execute('CREATE TABLE analyses(item TEXT,media_sha256 TEXT,version INTEGER)')
        db.executemany('INSERT INTO analyses VALUES(?,?,?)',
            [('a'*24,'b'*64,1),('a'*24,'b'*64,2),('c'*24,'b'*64,1)])
    output=tmp_path/'snapshot';output.mkdir()
    return action,output


def test_learning_preparation_counts_only_copied_files_and_keeps_versions_separate(learning_progress_fixture,monkeypatch):
    action,output=learning_progress_fixture
    ticks=[100.0]
    monkeypatch.setattr(action.time,'monotonic',lambda:ticks[0])
    original=action.copy_checked
    def slow_copy(*args,**kwargs):
        result=original(*args,**kwargs);ticks[0]+=6;return result
    monkeypatch.setattr(action,'copy_checked',slow_copy)
    progress=[]
    count,members=action.snapshot_learning(output,progress=progress.append)
    assert count==3 and len(members)==7  # Two evidence sets, three analysis versions.
    assert progress[0]=={'phase':'learning_database'}
    counted=progress[1:]
    assert counted[0]['processed_analysis_versions']==0
    assert counted[0]['copied_learning_files']==1
    assert counted[-1]['phase']=='learning_snapshot_ready'
    assert counted[-1]['processed_analysis_versions']==3
    assert counted[-1]['total_analysis_versions']==3
    assert counted[-1]['copied_learning_files']==7
    assert counted[-1]['copied_learning_bytes']==sum(v['bytes'] for v in members.values())
    for field in ('processed_analysis_versions','copied_learning_files','copied_learning_bytes'):
        values=[event[field] for event in counted]
        assert values==sorted(values)
    assert all(set(event)=={'phase','processed_analysis_versions','total_analysis_versions',
                            'copied_learning_files','copied_learning_bytes'} for event in counted)


def test_learning_preparation_progress_is_throttled_and_not_remote_verification(learning_progress_fixture,monkeypatch):
    action,output=learning_progress_fixture
    monkeypatch.setattr(action.time,'monotonic',lambda:100)
    progress=[]
    action.snapshot_learning(output,progress=progress.append)
    assert [p['phase'] for p in progress]==['learning_database','learning_evidence',
                                           'learning_bundle','learning_snapshot_ready']
    assert all('verified' not in json.dumps(p) for p in progress)


@pytest.mark.parametrize('missing',[False,True])
def test_broken_preparation_observer_never_changes_integrity_result(learning_progress_fixture,missing):
    action,output=learning_progress_fixture
    if missing:(store.ROOT/'learning/evidence'/('a'*24)/'01.jpg').unlink()
    def broken(event):raise RuntimeError('private observer failure')
    if missing:
        with pytest.raises(RuntimeError,match='learning_evidence_missing'):
            action.snapshot_learning(output,progress=broken)
        assert not (output/'learning.bundle.tar').exists()
    else:
        assert action.snapshot_learning(output,progress=broken)[0]==3


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('case', ['valid', 'legacy', 'corrupt_member', 'count_mismatch', 'missing', 'extra', 'duplicate', 'symlink', 'hardlink', 'traversal'])
def test_learning_bundle_restoration_checks_members_and_bytes(tmp_path, monkeypatch, case, workers):
    import io
    import sqlite3
    import tarfile
    from harness.tools import reference_backup as action
    # File completion must not flood learning progress while time is fixed.
    monkeypatch.setattr(action.time, 'monotonic', lambda: 100)
    source = tmp_path / 'source'; source.mkdir()
    db = source / 'analyses.sqlite3'
    with sqlite3.connect(db) as c:c.execute('CREATE TABLE analyses(item TEXT)')
    payloads = {'learning/analyses.sqlite3': db.read_bytes(), 'learning/evidence/00.jpg': b'frame'}
    expected = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in payloads.items()}
    bundle = source / 'learning.bundle.tar'
    with tarfile.open(bundle, 'w') as archive:
        for name, data in payloads.items():
            if case == 'missing' and name.endswith('.jpg'):continue
            if case == 'corrupt_member' and name.endswith('.jpg'):data = b'wrong'
            member = tarfile.TarInfo(name); member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if case in ('extra', 'duplicate', 'symlink', 'hardlink', 'traversal'):
            name = {'extra': 'learning/unrequested', 'duplicate': 'learning/evidence/00.jpg',
                    'symlink': 'learning/link', 'hardlink': 'learning/link',
                    'traversal': 'learning/../../outside'}[case]
            member = tarfile.TarInfo(name)
            if case in ('symlink', 'hardlink'):
                member.type = tarfile.SYMTYPE if case == 'symlink' else tarfile.LNKTYPE
                member.linkname = '../../outside'
            archive.addfile(member, io.BytesIO(b''))
    manifest = {'analyses': 1 if case == 'count_mismatch' else 0, 'learning_bundle': bundle.name,
                'files': {bundle.name: {'bytes': bundle.stat().st_size, 'sha256': action.digest(bundle)}}}
    if case == 'legacy':manifest['files'].update(expected)
    else:manifest['learning_members'] = expected
    class Transport:
        def fork_for_readback(self,identity):return Transport()
        def download(self, name, identity, directory):
            target = directory / name
            if name == 'manifest.json':target.write_text(json.dumps(manifest))
            else:shutil.copyfile(source / name, target)
            return target
    restore = tmp_path / 'restore'; restore.mkdir()
    progress=[]
    if case in ('valid', 'legacy'):
        action.verify_files(Transport(), 'snapshot', manifest, restore, readback_workers=workers, progress=progress.append)
        assert (restore / 'learning/evidence/00.jpg').read_bytes() == b'frame'
    else:
        with pytest.raises(RuntimeError, match='remote_checksum_mismatch|restore_count_mismatch|invalid_restore_path'):
            action.verify_files(Transport(), 'snapshot', manifest, restore, readback_workers=workers, progress=progress.append)
    assert all(event['state']=='verifying' for event in progress)
    counted=[event for event in progress if 'verified_learning_files' in event]
    assert counted[0]['verified_learning_files']==0
    if case in ('valid', 'legacy', 'count_mismatch'):
        assert [event['verified_learning_files'] for event in counted if event['phase']=='learning']==[0,2]
        assert counted[-1]['phase']=='learning_integrity'
        assert counted[-1]['verified_learning_bytes']==counted[-1]['total_learning_bytes']==sum(map(len,payloads.values()))
    else:
        assert counted[-1]['verified_learning_files']<counted[-1]['total_learning_files']
        assert not any(event['phase']=='learning_integrity' for event in counted)
    assert not any('learning/' in json.dumps(event) for event in progress)
    assert not (tmp_path / 'outside').exists()
