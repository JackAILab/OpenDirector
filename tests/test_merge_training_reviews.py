import json
from pathlib import Path

from harness.learning.candidate_review import make_receipt
from tools.merge_training_reviews import main


def test_merge_reviews_writes_bound_private_bundle(tmp_path, monkeypatch):
    queue = {
        'schema': 'visualagent.training-candidate-queue.v1',
        'source_manifest_sha256': 'a' * 64,
        'records': [{'sample_id': 'b' * 64, 'record_sha256': 'c' * 64, 'creator_token': 'creator',
                     'provenance': {'plan':'actual_agent_plan_snapshot','strategy_context':'external_reference_strategy_observation','trajectory':'actual_agent_observed_events','policy':'reference observations and user episodes must never be mixed as supervision'}}],
    }
    receipt = make_receipt(queue, 'b' * 64, 'reviewer',
                          {'privacy_review': True, 'rights_review': True,
                           'sanitized_context_review': True},
                          '独立核对候选内容、隐私和使用权，允许进入后续发布审核。',
                          reviewer_token='different')
    queue_path = tmp_path / 'queue.json'
    queue_path.write_text(json.dumps(queue), encoding='utf-8')
    receipts_dir = tmp_path / 'receipts'
    receipts_dir.mkdir()
    (receipts_dir / 'one.json').write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'bundle.json'
    monkeypatch.setattr('sys.argv', ['merge_training_reviews.py', '--queue', str(queue_path),
                                     '--receipts-dir', str(receipts_dir), '--output', str(output)])
    main()
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['schema'] == 'visualagent.training-candidate-review-bundle.v1'
    assert result['record_count'] == 1
    assert result['training_eligible'] is False
    assert output.stat().st_mode & 0o777 == 0o600


def test_merge_reviews_rejects_duplicate_candidate(tmp_path, monkeypatch):
    queue = {
        'schema': 'visualagent.training-candidate-queue.v1',
        'source_manifest_sha256': 'a' * 64,
        'records': [{'sample_id': 'b' * 64, 'record_sha256': 'c' * 64,
                     'provenance': {'plan':'actual_agent_plan_snapshot','strategy_context':'external_reference_strategy_observation','trajectory':'actual_agent_observed_events','policy':'reference observations and user episodes must never be mixed as supervision'}}],
    }
    receipt = make_receipt(queue, 'b' * 64, 'reviewer',
                           {'privacy_review': False, 'rights_review': True,
                            'sanitized_context_review': True},
                           '独立核对后发现隐私项仍需处理，暂不允许发布。')
    queue_path = tmp_path / 'queue.json'
    queue_path.write_text(json.dumps(queue), encoding='utf-8')
    receipts_dir = tmp_path / 'receipts'
    receipts_dir.mkdir()
    for name in ('one.json', 'two.json'):
        (receipts_dir / name).write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'bundle.json'
    monkeypatch.setattr('sys.argv', ['merge_training_reviews.py', '--queue', str(queue_path),
                                     '--receipts-dir', str(receipts_dir), '--output', str(output)])
    try:
        main()
    except ValueError as exc:
        assert 'Duplicate' in str(exc)
    else:
        raise AssertionError('duplicate receipt was accepted')
