import pytest
from harness.research.captioner_bridge import convert


def example():
    task={'id':'task','asset_sha256':'b'*64,'source_path':'PRIVATE_PATH',
        'evidence':{'start':10,'end':15,'duration':5,'frames':[{'id':'f000','time':1,'source_time':11,'sha256':'a'*64,'path':'PRIVATE_PATH'}],
        'audio':{'id':'a000','sha256':'c'*64,'path':'PRIVATE_PATH'},'video':None}}
    obs={'omni':{'claims':[{'text':'light appears','start':1,'end':2,'modality':'audiovisual','evidence_ids':['f000','a000']}],
        'training_eligible':True,'human_approval':'approved','provider_payload':'PRIVATE_PAYLOAD'}}
    return task,obs


def test_bridge_offsets_and_namespaces_evidence_without_inheriting_approval():
    import json
    task,obs=example();one=convert(task,obs,'R');task['id']='child';two=convert(task,obs,'R')
    event=one['evidence']['events'][0]
    assert (event['start'],event['end'])==(11,12)
    assert event['evidence_ids']!=two['evidence']['events'][0]['evidence_ids']
    assert one['training_eligible'] is False and one['evidence']['independent_review']=='pending'
    assert 'PRIVATE' not in json.dumps(one)


def test_missing_audio_evidence_cannot_support_av_claim():
    task,obs=example();obs['omni']['claims'][0]['evidence_ids']=['f000']
    with pytest.raises(ValueError,match='modality_evidence_mismatch'):convert(task,obs,'R')
    task,obs=example();task['evidence']['frames'][0]['source_time']=12
    with pytest.raises(ValueError,match='frame_time_mismatch'):convert(task,obs,'R')


def test_uncertainty_is_retained_and_paths_do_not_change_identity():
    task,obs=example()
    obs['omni'].update(generation_truncated=True,uncertainties=[{'start':2,'end':3,'reason':'brief event unclear'}])
    one=convert(task,obs,'R');task['evidence']['frames'][0]['path']='DIFFERENT_PATH'
    two=convert(task,obs,'R')
    assert one==two
    warning=one['evidence']['observer_warnings']['omni']
    assert warning['generation_truncated'] is True
    assert warning['uncertainties']==[{'start':12,'end':13,'reason':'brief event unclear'}]
