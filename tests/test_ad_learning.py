import pytest
from harness.library import store,learning
from harness.learning.episodes import record_plan,release_blockers
from harness.studio import store as studio
from test_creative_studio import client


def analysis():
    return {'media_role':'original_ad','confidence':'medium','principle':'用动作证明功能','mechanism':'前景活动与结果变化形成对照',
        'beats':[{'start':0,'end':5,'observation':'看到动作','purpose':'建立任务','frames':[0]}],
        'grill_questions':['卖点是否有证据？'],'transfer_rules':['设计新的动作'],'avoid':['没有相关功能时不用']}


def test_analysis_cannot_invent_timestamps_or_audio_review():
    raw=analysis();raw['audio_semantics_reviewed']=True
    result=learning.validate(raw,15,[1])
    assert not result['audio_semantics_reviewed'] and not result['training_eligible']
    assert not result['reconstructed_trajectory']
    raw['beats'][0]['frames']=[1]
    with pytest.raises(ValueError):learning.validate(raw,15,[1])
    raw['beats'][0]['frames']=[0];raw['beats'][0]['end']=.1
    with pytest.raises(ValueError):learning.validate(raw,15,[1])


def test_analysis_repairs_zero_length_sampled_beat_without_inventing_audio():
    raw=analysis();raw['beats'][0]['start']=1;raw['beats'][0]['end']=1
    result=learning.validate(raw,15,[1,10])
    assert result['beats'][0]['end']==10
    assert result['validation_repairs']==[{'kind':'zero_length_beat','beat':0,'original_end':1,'repaired_end':10}]
    assert result['audio_semantics_reviewed'] is False
    assert result['training_eligible'] is False


def test_analysis_version_is_pinned_to_current_media(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    identity,_=store.ingest({'title':'测试广告','source_url':'https://example.com/ad'})
    with store.connection() as c:c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',(identity,'assets/a.mp4','a'*64,10,15,1,1280,720,0))
    clean=learning.validate(analysis(),15,[1])
    assert learning.save_analysis(identity,'a'*64,1,'test-model',clean,[1])==1
    assert learning.get_analysis(identity)['analysis_version']==1
    assert learning.save_analysis(identity,'a'*64,1,'test-model',clean,[1])==2
    with store.connection() as c:c.execute('UPDATE assets SET sha256=? WHERE item=?',('b'*64,identity))
    assert learning.get_analysis(identity) is None


def test_private_plan_revisions_are_non_overwriting(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'DATA',tmp_path)
    p={'id':'project','revision':1,'brief':{'product':'杯子'},'shots':[]}
    digest=record_plan(p,1)
    assert record_plan(p,1)==digest
    p['brief']['product']='另一件商品'
    with pytest.raises(ValueError):record_plan(p,1)
    p['revision']=2;assert record_plan(p,1)!=digest


def test_film_approval_alone_does_not_authorize_training():
    blockers=release_blockers({'gates':{'human_approval':True},'provenance':'reverse_engineered_ad'})
    assert 'training_consent' in blockers and 'independent_semantic_review' in blockers
    assert 'actual_agent_provenance' in blockers


def test_episode_capture_failure_does_not_block_user_plan(client,monkeypatch):
    from test_creative_studio import ready
    import harness.learning.episodes as episodes
    def fail(*args):raise OSError('capture disk unavailable')
    monkeypatch.setattr(episodes,'record_plan',fail)
    p=ready(client)
    assert p['state']=='ready' and p['shots']
    assert any(e['code']=='plan_capture_failed' for e in p['events'])


def test_strategy_snapshot_preserves_evidence_and_excludes_user_data(tmp_path,monkeypatch):
    import json,hashlib,shutil
    from harness.tools.reference_backup import backup
    monkeypatch.setattr(store,'ROOT',tmp_path/'library')
    identity,_=store.ingest({'title':'案例','source_url':'https://example.org/source'})
    sha='a'*64;clean=learning.validate(analysis(),15,[1])
    learning.save_analysis(identity,sha,1,'test-model',clean,[1])
    folder=store.ROOT/'learning/evidence'/identity;folder.mkdir(parents=True)
    (folder/'00.jpg').write_bytes(b'frame evidence')
    (folder/'evidence.json').write_text(json.dumps({'media_sha256':sha,'frames':[{'time':1,'path':'00.jpg'}]}))
    (store.ROOT/'learning/episodes.sqlite3').write_bytes(b'private user context')
    (store.ROOT/'learning/credential.txt').write_text('do not copy')
    class Transport:
        def upload(self,directory,identity):
            self.directory=directory
            assert not (directory/'learning/episodes.sqlite3').exists()
            assert not (directory/'learning/credential.txt').exists()
        def download(self,name,identity,directory):
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.directory/name,target);return target
    result=backup(Transport())
    assert result['state']=='verified'
    snapshot=store.ROOT/'snapshots'/result['snapshot']
    manifest=json.loads((snapshot/'manifest.json').read_text())
    assert manifest['analyses']==1 and 'learning/analyses.sqlite3' in manifest['files']
    assert manifest['files'][f'learning/evidence/{identity}/00.jpg']['sha256']==hashlib.sha256(b'frame evidence').hexdigest()


def test_creation_journal_is_private_owner_scoped_and_tamper_evident(tmp_path,monkeypatch):
    import json,sqlite3
    from harness.learning.episodes import record_transition,inspect_episode,record_artifact
    monkeypatch.setattr(studio,'DATA',tmp_path)
    p={'id':'p','revision':1,'generation_mode':'single_native','messages':[{'content':'private@example.org https://secret.example/key'}],
       'film':{'job_id':'secret-provider-payload'},'model':'private-endpoint','brief':{'product':'cup'}}
    first=record_transition(p,1,10,'agent','planning_started')
    assert record_transition(p,1,10,'agent','planning_started')==first
    record_transition(p,1,11,'agent','plan_ready')
    p['qa']={'technical':'passed','audio':True,'duration':15,'raw_payload':'secret','semantic':'passed','human':'approved'}
    artifact=tmp_path/'film.mp4';artifact.write_bytes(b'actual-file-bytes')
    observed=record_artifact(p,1,artifact)
    assert observed['qa']['semantic']=='pending' and observed['qa']['human']=='pending'
    report=inspect_episode('p',1)
    assert report['chain_verified'] and 'generation_accepted' in report['revisions'][0]['missing_evidence']
    assert not report['training_eligible']
    assert inspect_episode('p',2)['revisions']==[]
    serialized=json.dumps(report)
    assert 'private@example' not in serialized and 'secret-provider' not in serialized and 'private-endpoint' not in serialized
    with sqlite3.connect(tmp_path/'learning/episodes.sqlite3') as c:
        c.execute("UPDATE transitions SET data='{}' WHERE event_seq=10")
    with pytest.raises(ValueError,match='integrity'):inspect_episode('p',1)


def test_journal_rejects_rewrite_and_owner_change(tmp_path,monkeypatch):
    from harness.learning.episodes import record_transition
    monkeypatch.setattr(studio,'DATA',tmp_path)
    p={'id':'p','revision':1,'brief':{}}
    record_transition(p,1,1,'agent','plan_ready')
    p['brief']={'product':'changed'}
    with pytest.raises(ValueError,match='overwrite'):record_transition(p,1,1,'agent','plan_ready')
    with pytest.raises(ValueError,match='lineage'):record_transition(p,2,2,'agent','plan_ready')
    with pytest.raises(ValueError):record_transition(p,1,2,'agent','https://secret')


def test_journal_capture_failure_never_repeats_or_breaks_planning(client,monkeypatch):
    import harness.learning.episodes as episodes
    from test_creative_studio import ready
    calls=[]
    def fail(*args):calls.append(args);raise OSError('private failure detail')
    monkeypatch.setattr(episodes,'record_transition',fail)
    p=ready(client)
    assert p['state']=='ready'
    assert any(e['code']=='transition_capture_failed' for e in p['events'])
    assert 'private failure detail' not in str(p['events'])
    assert len(calls)>0


def test_journal_does_not_hide_a_capture_gap(client,monkeypatch):
    from test_creative_studio import ready
    from harness.learning.episodes import inspect_episode
    p=ready(client)
    with studio.connection() as c:
        c.execute('INSERT INTO events(project,time,stage,code,shot) VALUES(?,?,?,?,?)',
            (p['id'],0,'learning','transition_capture_failed',''))
    report=inspect_episode(p['id'],1)
    assert report['unrecorded_event_count']==1
    assert all('incomplete_capture_history' in r['missing_evidence'] for r in report['revisions'])
