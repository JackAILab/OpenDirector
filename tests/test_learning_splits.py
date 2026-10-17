import hashlib
import json
import pytest
from harness.learning.splits import assign,assign_frozen
from harness.learning.inventory import prepare,token
from harness.studio import store
from test_creative_studio import client,ready


def sha(s):return hashlib.sha256(s.encode()).hexdigest()


def record(name,*links):return {'sample_id':sha(name),'link_tokens':[sha(v) for v in links]}


def test_relationships_merge_transitively_and_are_order_independent(tmp_path):
    rows=[record('a','series'),record('b','series','source'),record('c','source','media'),record('d','media'),record('e','separate')]
    one=assign(rows,tmp_path/'one.sqlite','seed')['records']
    two=assign(rows[::-1],tmp_path/'two.sqlite','seed')['records']
    assert one==two
    family={r['family_id'] for r in one if r['sample_id']!=sha('e')}
    assert len(family)==1
    assert len({r['partition'] for r in one if r['sample_id']!=sha('e')})==1
    assert len({r['family_id'] for r in one})==2


def test_new_cross_partition_relation_is_quarantined_not_moved(tmp_path):
    registry=tmp_path/'split.sqlite';rows=[record(str(i),'family-'+str(i)) for i in range(50)]
    initial=assign(rows,registry,'freeze')['records']
    a=next(r for r in initial if r['partition']=='train');b=next(r for r in initial if r['partition']=='test')
    bridge={'sample_id':sha('bridge'),'link_tokens':[a['sample_id'],b['sample_id']]}
    updated=assign(rows+[bridge],registry,'freeze')['records']
    for r in updated:
        if r['sample_id'] in (a['sample_id'],b['sample_id'],sha('bridge')):assert r['partition']=='quarantine'
    # Removing the bridge from the next report cannot undo known leakage.
    later=assign(rows,registry,'freeze')['records']
    assert next(r for r in later if r['sample_id']==a['sample_id'])['partition']=='quarantine'
    with pytest.raises(ValueError,match='frozen'):assign(rows,registry,'changed')


def test_frozen_registry_reuse_quarantines_unseen_families(tmp_path):
    registry=tmp_path/'split.sqlite'
    initial=assign([record('a','family')],registry,'original-seed')['records']
    updated=assign_frozen([record('a','family'),record('b','new-family')],registry)['records']
    assert next(r for r in updated if r['sample_id']==sha('a'))['partition']==initial[0]['partition']
    assert next(r for r in updated if r['sample_id']==sha('b'))['partition']=='quarantine'


def test_growth_keeps_previous_assignments_and_uses_private_registry(tmp_path):
    registry=tmp_path/'split.sqlite';initial=assign([record('a','family')],registry,'seed')['records'][0]
    new=assign([record('a','family'),record('b','family')],registry,'seed')['records']
    assert all(r['partition']==initial['partition'] for r in new)
    assert registry.stat().st_mode & 0o777==0o600
    registry.chmod(0o644)
    with pytest.raises(ValueError,match='private'):assign([],registry,'seed')


def test_manifest_excludes_private_content_and_does_not_trust_project_eligibility(client,tmp_path):
    p=ready(client);p.update(training_eligible=True,messages=[{'role':'user','content':'person@example.org secret https://private.invalid'}])
    p['library_learning']={'source_item':'sample-source','media_sha256':'a'*64};store.save(p,1)
    q=ready(client);q['library_learning']={'source_item':'sample-source','media_sha256':'a'*64};store.save(q,1)
    result=prepare(b'x'*32,tmp_path/'registry.sqlite','seed')
    assert result['summary']['projects']==2 and result['summary']['training_eligible']==0
    assert len({r['family_id'] for r in result['records']})==1
    text=json.dumps(result)
    assert 'person@example' not in text and 'https://' not in text and p['id'] not in text
    assert all('privacy_review' in r['missing_evidence'] and not r['training_eligible'] for r in result['records'])


def test_archived_versions_and_historical_series_cannot_leak_between_partitions(client,tmp_path):
    from harness.learning import governance
    p=ready(client);p['state']='completed';p['artifact']='artifacts/old.mp4';p['versions']=[{'revision':0,'artifact':'artifacts/older.mp4','shots':[],'qa':{},'reviews':[]}]
    root=store.DATA/'artifacts';root.mkdir();(root/'old.mp4').write_bytes(b'old');(root/'older.mp4').write_bytes(b'older');store.save(p,1)
    q=ready(client);s=governance.create_series(1,'series');governance.set_family(p,1,s['id']);governance.set_family(q,1,s['id']);governance.set_family(q,1,None)
    report=prepare(b'x'*32,tmp_path/'split.sqlite','seed')
    assert report['summary']['versions']==3 and report['summary']['archived_versions']==1
    assert len({r['family_id'] for r in report['records']})==1
    assert report['summary']['actual_artifacts']==2


def test_duplicate_source_media_groups_distinct_library_ids(client,tmp_path,monkeypatch):
    import sqlite3
    from harness.library import store as library
    root=tmp_path/'library';root.mkdir();monkeypatch.setattr(library,'ROOT',root)
    with sqlite3.connect(root/'library.sqlite3') as c:
        c.execute('CREATE TABLE assets(item TEXT,sha256 TEXT)')
        c.executemany('INSERT INTO assets VALUES(?,?)',[('first','a'*64),('second','a'*64)])
    p=ready(client);p['library_reference']='first';store.save(p,1)
    q=ready(client);q['library_reference']='second';store.save(q,1)
    report=prepare(b'x'*32,tmp_path/'split.sqlite','seed')
    assert len({r['family_id'] for r in report['records']})==1
    assert all(r['relationships']['source_media']==1 for r in report['records'])


def test_manifest_reports_evidence_tiers_separately_from_training_count(client,tmp_path):
    p=ready(client);p['state']='completed';p['artifact']='artifacts/tier.mp4';path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'tier');store.save(p,1)
    result=prepare(b'x'*32,tmp_path/'split.sqlite','seed')
    tiers=result['summary']['evidence_tiers']
    assert tiers['artifact_reviewable']>=1 and tiers.get('consented_for_training',0)==0
    assert result['summary']['training_eligible']==0 and result['summary']['release_ready'] is False


def test_manifest_promotes_only_fully_gated_public_versions(client,tmp_path,monkeypatch):
    import harness.learning.inventory as inventory
    p=ready(client);p.update(state='completed',artifact='artifacts/gated.mp4')
    path=store.DATA/p['artifact'];path.parent.mkdir(parents=True);path.write_bytes(b'gated-film')
    digest=sha(path.read_bytes().decode())
    p['reviews']=[{'revision':p['revision'],'artifact_sha256':digest,'decision':'approved'}]
    store.save(p,1)
    monkeypatch.setattr(inventory,'inspect_episode',lambda *_: {'revisions':[{'revision':p['revision'],'missing_evidence':[], 'artifacts':[{'artifact_sha256':digest}]}]})
    monkeypatch.setattr(inventory.governance,'status',lambda *_args,**_kwargs: {'training':True,'public_dataset':True,'independent_quality':{'decision':'passed'}})
    monkeypatch.setattr(inventory.curation,'latest',lambda *_args,**_kwargs: {'decisions':{g:True for g in inventory.curation.GATES}})
    result=inventory.prepare(b'x'*32,tmp_path/'registry.sqlite','seed')
    assert result['summary']['training_eligible']==1 and result['summary']['release_ready'] is True
    assert result['records'][0]['training_eligible'] is True
