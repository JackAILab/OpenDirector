from copy import deepcopy
import pytest
from harness.research.briefs import digest
from tools.validate_relation_review import validate,summarize


def sample():
    p={'schema':'visualagent.source-relation-packet.v1','training_eligible':False,
       'clips':[{'label':'S01','duration':10,'sha256':'a'*64}]}
    r={'schema':'visualagent.source-relation-review.v1','packet_sha256':digest(p),
       'reviewer_code':'r1','review_status':'submitted_unverified','independence_status':'not_verified',
       'training_eligible':False,'clips':[{'label':'S01','watched':True,'audio':'已完整听过',
       'role':'原始广告','goal':'测试目标','uncertainty':'证据有限','events':[
       {'id':'E1','start':0,'end':2,'modality':'视觉','observation':'人物出现'}],
       'relations':[{'events':['E1'],'kind':'人物反应','interpretation':'人物反应解释',
       'support':'有依据的解释','alternatives':'也可能是其他原因'}]}]}
    return p,r


def test_valid_is_not_approved():
    p,r=sample();assert validate(p,r)==r
    s=summarize(p,[r]);assert s['independent_reviews_completed']==0 and not s['training_eligible']
    assert s['semantic_agreement'] is None


@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),-1,11,None])
def test_bad_time(value):
    p,r=sample();r['clips'][0]['events'][0]['start']=value
    with pytest.raises(ValueError,match='invalid_event_time'):validate(p,r)


def test_wrong_packet_missing_clip_and_bad_link():
    p,r=sample();r['packet_sha256']='0'*64
    with pytest.raises(ValueError,match='packet_digest'):validate(p,r)
    p,r=sample();r['clips']=[]
    with pytest.raises(ValueError,match='coverage'):validate(p,r)
    p,r=sample();r['clips'][0]['relations'][0]['events']=['E99']
    with pytest.raises(ValueError,match='event_link'):validate(p,r)


def test_duplicate_and_revision_do_not_inflate_reviewers():
    p,r=sample();revision=deepcopy(r);revision['clips'][0]['goal']='修改目标'
    s=summarize(p,[r,r,revision]);assert s['duplicate_submissions']==1
    assert s['declared_reviewer_codes']==1 and s['reviewer_codes_with_conflicting_versions']==1
    assert s['independent_reviews_completed']==0


def test_silent_media_cannot_support_audio_claim():
    p,r=sample();r['clips'][0]['audio']='无法播放声音';r['clips'][0]['events'][0]['modality']='声音'
    with pytest.raises(ValueError,match='without_listening'):validate(p,r)


@pytest.mark.parametrize('key,value',[('review_status','draft'),('training_eligible',True),('independence_status','verified')])
def test_no_self_approval(key,value):
    p,r=sample();r[key]=value
    with pytest.raises(ValueError):validate(p,r)


def test_empty_intake():
    p,_=sample();s=summarize(p,[]);assert s['valid_unique_submissions']==0


def test_invalid_packet_rejected_without_reviews():
    with pytest.raises(ValueError,match="invalid_packet"):summarize({},[])
