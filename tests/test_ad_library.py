import pytest
from harness.library import store

@pytest.fixture
def item(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    record={'source_url':'https://example.org/ad?id=7&utm_source=search','title':'广告案例','brand':'品牌','industry':'家居','quality_evidence':[{'kind':'official','text':'品牌官方发布'}]}
    identity,new=store.ingest(record);assert new
    return identity,record

def test_idempotent_ingest_does_not_approve_or_erase_human_review(item):
    identity,record=item
    store.review_item(identity,7,0,'selected',{'craft':4},['光影'],'适合家居广告')
    assert store.ingest(record)==(identity,False)
    store.ingest({**record,'title':'更新标题','training_eligible':True,'review':{'state':'selected'}})
    actual=store.get_item(identity,7)
    assert actual['review']['state']=='selected' and actual['revision']==2
    assert actual['training_eligible'] is False
    assert store.get_item(identity,8)['review']['state']=='pending'

def test_concurrent_review_conflict_and_history(item):
    identity,_=item
    store.review_item(identity,7,0,'selected',{'hook':5},[],'')
    with pytest.raises(RuntimeError):store.review_item(identity,7,0,'rejected',{},[],'')
    store.review_item(identity,7,1,'revisit',{},[],'需重看声音')
    with store.connection() as c:assert c.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==2
    assert store.list_items(7,state='revisit')['total']==1
    assert store.list_items(8,state='pending')['total']==1
    assert store.list_items(7,search='不存在')['total']==0

def test_bad_scores_and_signed_source_rejected(item):
    identity,_=item
    with pytest.raises(ValueError):store.review_item(identity,7,0,'selected',{'craft':True},[],'')
    with pytest.raises(ValueError):store.ingest({'source_url':'https://example.org/ad?token=secret','title':'x'})
