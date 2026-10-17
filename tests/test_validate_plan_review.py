import json
from pathlib import Path
import pytest
from harness.research.briefs import digest
from tools.validate_plan_review import validate


def make_files(tmp_path):
    packet = {'schema': 'visualagent.blind-plan-review.v1',
              'plans': [{'label': 'A', 'plan': {}, 'disclosed_task': {}},
                        {'label': 'B', 'plan': {}, 'disclosed_task': {}}],
              'review_status': 'pending', 'training_eligible': False}
    packet_path = tmp_path / 'packet.json'; packet_path.write_text(json.dumps(packet))
    ratings = {}
    for label in ('A', 'B'):
        ratings.update({f'{label}_violation': '无', f'{label}_utility': '4',
                        f'{label}_timeline_ready': '是',
                        f'{label}_creative_specificity': '清楚的商品动作',
                        f'{label}_evidence': '逐镜头指出事实依据和限制。'})
    review = {'schema': 'visualagent.human-plan-review-draft.v1',
              'packet_sha256': digest(packet), 'ratings': ratings,
              'review_status': 'complete', 'training_eligible': False}
    review_path = tmp_path / 'review.json'; review_path.write_text(json.dumps(review))
    return packet_path, review_path


def test_validate_blinded_review_and_normalize(tmp_path):
    packet, review = make_files(tmp_path)
    result = validate(packet, review, require_complete=True)
    assert result['training_eligible'] is False
    assert result['ratings']['A']['utility'] == 4


def test_validate_rejects_digest_and_extra_or_missing_ratings(tmp_path):
    packet, review = make_files(tmp_path)
    data = json.loads(review.read_text()); data['packet_sha256'] = 'wrong'
    review.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='packet_digest_mismatch'):
        validate(packet, review)
    data['packet_sha256'] = digest(json.loads(packet.read_text())); data['ratings']['A_extra'] = 'x'
    review.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='rating_keys_mismatch'):
        validate(packet, review)


def test_validate_rejects_ineligible_or_weak_evidence(tmp_path):
    packet, review = make_files(tmp_path)
    data = json.loads(review.read_text()); data['training_eligible'] = True
    review.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='training_must_remain_ineligible'):
        validate(packet, review)
    data['training_eligible'] = False; data['ratings']['B_evidence'] = '短'
    review.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='B_evidence_too_short'):
        validate(packet, review)
