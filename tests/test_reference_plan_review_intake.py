from copy import deepcopy
import pytest
from harness.research.briefs import digest
from tools.validate_reference_plan_review import validate,summarize


def sample():
    p={'schema':'visualagent.reference-plan-review-packet.v1','form_template_sha256':'a'*64,
       'training_eligible':False,'plans':[{'label':'P01'}],'sources':[{'label':'V01'},{'label':'V02'}]}
    r={'schema':'visualagent.reference-plan-review.v1','packet_sha256':digest(p),'reviewer_code':'r1',
       'stage1_locked':True,'review_status':'submitted_unverified','independence_status':'not_verified',
       'training_eligible':False,'stage1':{'P01_violation':'无法判断','P01_goal':'部分','P01_utility':'无法判断','P01_evidence':'待核对'},
       'stage2':{}}
    for v in ['V01','V02']:
        r['stage2'].update({v+'_view':'完整观看但声音无法判断','P01_'+v+'_relation':'无法判断','P01_'+v+'_evidence':'关系证据不足'})
    return p,r


def test_unknown_is_preserved_not_scored_zero():
    p,r=sample();s=summarize(p,[r])
    assert s['rating_counts']['stage1']['P01_utility']=={'无法判断':1}
    assert s['independent_reviews_completed']==0 and s['semantic_effect'] is None


@pytest.mark.parametrize('key,value',[('stage1_locked',False),('stage1_locked',1),('review_status','draft'),('training_eligible',True),('independence_status','verified')])
def test_no_implicit_promotion(key,value):
    p,r=sample();r[key]=value
    with pytest.raises(ValueError):validate(p,r)


def test_changed_form_and_missing_rating_rejected():
    p,r=sample();p['form_template_sha256']='b'*64
    with pytest.raises(ValueError,match='packet_digest'):validate(p,r)
    p,r=sample();del r['stage2']['P01_V02_relation']
    with pytest.raises(ValueError,match='coverage'):validate(p,r)


def test_invalid_rating_and_blank_evidence():
    p,r=sample();r['stage1']['P01_utility']='0'
    with pytest.raises(ValueError,match='invalid_rating'):validate(p,r)
    p,r=sample();r['stage2']['P01_V01_evidence']=' '
    with pytest.raises(ValueError,match='missing_evidence'):validate(p,r)


def test_duplicates_and_revisions_do_not_inflate_votes():
    p,r=sample();revision=deepcopy(r);revision['stage1']['P01_goal']='是'
    s=summarize(p,[r,r,revision]);assert s['duplicate_submissions']==1
    assert s['reviewer_codes_with_conflicting_versions']==1
    assert s['unconflicted_submissions_in_counts']==0
    assert s['rating_counts']=={'stage1':{},'stage2':{}}


def test_empty_intake_still_checks_packet():
    p,_=sample();assert summarize(p,[])['unique_submissions']==0
    p['plans'].append(p['plans'][0])
    with pytest.raises(ValueError,match='duplicate_packet_label'):summarize(p,[])
