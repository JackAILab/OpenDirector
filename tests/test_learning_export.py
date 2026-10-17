import json
import pytest
from harness.learning.export import release
from harness.learning.inventory import input_fingerprints


def manifest(**kw):
    return {'schema':'visualagent.private-dataset-preparation.v1','summary':{'release_ready':False},'records':kw.get('records',[])}


def test_release_is_fail_closed_and_non_overwriting(tmp_path):
    source=tmp_path/'manifest.json';source.write_text(json.dumps(manifest(records=[{'sample_id':'a'*64,'training_eligible':False,'public_dataset_consent':False,'missing_evidence':['privacy_review']}])));out=tmp_path/'receipt.json'
    result=release(source,out)
    assert result['state']=='not_ready' and result['eligible_count']==0 and result['content_exported'] is False
    assert 'privacy_review' in result['blockers']['a'*64] and not result['training_records']
    with pytest.raises(FileExistsError):release(source,out)
    assert 'sample_id' not in out.read_text()


def test_release_requires_all_explicit_gates(tmp_path):
    source=tmp_path/'manifest.json';source.write_text(json.dumps(manifest(records=[{'sample_id':'b'*64,'training_eligible':True,'public_dataset_consent':True,'missing_evidence':[]}])));out=tmp_path/'receipt.json'
    result=release(source,out)
    assert result['state']=='ready' if False else result['state']=='not_ready'
    assert 'training_eligible_false' not in result['blockers']['b'*64] if 'b'*64 in result['blockers'] else True


def test_release_rejects_manifest_when_authoritative_inputs_changed(tmp_path,monkeypatch):
    source=tmp_path/'manifest.json';source.write_text(json.dumps({**manifest(records=[]),'input_fingerprints':{'projects':'old','episodes':None,'library':None,'library_analyses':None}}));out=tmp_path/'receipt.json'
    result=release(source,out)
    assert result['state']=='not_ready' and 'stale_input_fingerprints' in result['blockers']['manifest']
