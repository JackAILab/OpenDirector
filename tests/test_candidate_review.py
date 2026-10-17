import pytest
from harness.learning.candidate_review import make_receipt,validate_release

def queue():
    return {'schema':'visualagent.training-candidate-queue.v1','source_manifest_sha256':'a'*64,
            'records':[{'sample_id':'b'*64,'record_sha256':'c'*64,'creator_token':'creator-token','training_eligible':False,
                        'provenance':{'plan':'actual_agent_plan_snapshot','strategy_context':'external_reference_strategy_observation','trajectory':'actual_agent_observed_events','policy':'reference observations and user episodes must never be mixed as supervision'}}]}

def test_exact_review_receipt_promotes_only_matching_candidate():
    q=queue();r=make_receipt(q,'b'*64,'reviewer-1',{g:True for g in ('privacy_review','rights_review','sanitized_context_review')},'已核对脱敏后的确切文本与授权范围。',reviewer_token='different-token')
    out=validate_release(q,[r]);assert out[0]['training_eligible'] and out[0]['public_release']

def test_review_is_bound_to_queue_and_all_gates():
    q=queue();r=make_receipt(q,'b'*64,'reviewer-1',{g:True for g in ('privacy_review','rights_review','sanitized_context_review')},'逐项复核了候选文本与来源边界。',reviewer_token='different-token')
    r['queue_sha256']='d'*64
    with pytest.raises(ValueError,match='Missing exact-content'):validate_release(q,[r])


def test_creator_cannot_sign_exact_content_review():
    q=queue();q['records'][0]['creator_token']='same-token'
    with pytest.raises(ValueError,match='Creator cannot'):
        make_receipt(q,'b'*64,'reviewer-1',{g:True for g in ('privacy_review','rights_review','sanitized_context_review')},'独立核对了脱敏后的确切文本。',reviewer_token='same-token')


def test_release_rejects_candidate_without_provenance_separation():
    q=queue();q['records'][0].pop('provenance')
    r=make_receipt(q,'b'*64,'reviewer-1',{g:True for g in ('privacy_review','rights_review','sanitized_context_review')},'候选内容已逐项核对，但来源分层缺失。',reviewer_token='different-token')
    with pytest.raises(ValueError,match='provenance'):
        validate_release(q,[r])
