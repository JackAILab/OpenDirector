import json
from harness.research.briefs import digest
from tools.summarize_plan_reviews import summarize


def make_review(tmp_path, status='complete'):
    packet={'schema':'visualagent.blind-plan-review.v1','plans':[{'label':'A','plan':{},'disclosed_task':{}},{'label':'B','plan':{},'disclosed_task':{}}], 'review_status':'pending','training_eligible':False}
    pp=tmp_path/'packet.json'; pp.write_text(json.dumps(packet))
    ratings={}
    for label, violation, utility in [('A','无','4'),('B','有','2')]:
        ratings.update({f'{label}_violation':violation,f'{label}_utility':utility,
                        f'{label}_timeline_ready':'是',f'{label}_creative_specificity':'清楚的商品动作',
                        f'{label}_evidence':'逐镜头说明事实依据与限制。'})
    rp=tmp_path/'review.json'; rp.write_text(json.dumps({'schema':'visualagent.human-plan-review-draft.v1','packet_sha256':digest(packet),'ratings':ratings,'review_status':status,'training_eligible':False}))
    return pp,rp


def test_aggregate_complete_reviews(tmp_path):
    pair=make_review(tmp_path)
    result=summarize([pair])
    assert result['review_status']=='complete'
    assert result['independent_review_completed']==0
    assert result['validated_complete_records']==1
    assert result['independence_status']=='not_verified'
    assert result['plan_count']==2
    assert result['violations']=={'有':1,'无':1}
    assert result['utility']=={'n':2,'mean':3.0,'min':2,'max':4}
    assert result['training_eligible'] is False


def test_draft_does_not_count_as_independent_review(tmp_path):
    pair=make_review(tmp_path, status='draft')
    result=summarize([pair], require_complete=False)
    assert result['review_status']=='partial'
    assert result['independent_review_completed']==0
    assert result['training_eligible'] is False


def test_duplicate_review_does_not_inflate_counts(tmp_path):
    pair=make_review(tmp_path)
    result=summarize([pair,pair])
    assert result['review_record_count']==1
    assert result['plan_count']==2
    assert result['errors'][0]['error']=='duplicate_review'
    assert result['review_status']=='partial'


def test_two_records_for_one_packet_are_not_two_packets(tmp_path):
    pair=make_review(tmp_path)
    data=json.loads(pair[1].read_text())
    data['ratings']['A_utility']='3'
    second=tmp_path/'second.json'; second.write_text(json.dumps(data))
    result=summarize([pair,(pair[0],second)])
    assert result['packet_count']==1
    assert result['review_record_count']==2
    assert result['independent_review_completed']==0
