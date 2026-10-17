import json
import hashlib
import hmac
from test_creative_studio import client


SALT = b'candidate-api-test-key-material!!'


def queue_payload(creator=1):
    return {'schema': 'visualagent.training-candidate-queue.v1',
            'source_manifest_sha256': 'a' * 64,
            'training_eligible': False,
            'salt_sha256': hashlib.sha256(SALT).hexdigest(),
            'records': [{'sample_id': 'b' * 64, 'record_sha256': 'c' * 64,
                         'creator_token': hmac.new(SALT, f"creator:{creator}".encode(), hashlib.sha256).hexdigest(),
                         'partition': 'train', 'review_status': 'pending_exact_content_review',
                         'training_eligible': False,
                         'plan': {'brief': {'product': '测试产品'}, 'strategy_candidates': [{'principle': '单一主张'}]},
                         'trajectory': {'events': [{'stage': 'agent', 'code': 'plan_ready'}]}}]}


def test_candidate_queue_is_admin_scoped_and_receipt_is_private(client, tmp_path, monkeypatch):
    queue_path = tmp_path / 'queue.json'; queue_path.write_text(json.dumps(queue_payload()), encoding='utf-8'); queue_path.chmod(0o600)
    review_dir = tmp_path / 'reviews'
    monkeypatch.setenv('AD_TRAINING_CANDIDATE_QUEUE', str(queue_path))
    monkeypatch.setenv('AD_TRAINING_REVIEW_DIR', str(review_dir))
    key = tmp_path / 'salt'; key.write_bytes(SALT); key.chmod(0o600)
    monkeypatch.setenv('AD_LEARNING_SALT_FILE', str(key))
    assert client.get('/creative/api/admin/learning/candidates', headers={'Authorization': 'Bearer one'}).status_code == 403
    headers = {'Authorization': 'Bearer admin'}
    listed = client.get('/creative/api/admin/learning/candidates', headers=headers)
    assert listed.status_code == 200 and listed.json()['items'][0]['strategy_count'] == 1
    detail = client.get('/creative/api/admin/learning/candidates/' + 'b' * 64, headers=headers).json()['candidate']
    assert 'creator_token' not in detail and detail['trajectory']['events'][0]['code'] == 'plan_ready'
    body = {'privacy_review': True, 'rights_review': True, 'sanitized_context_review': True,
            'note': '逐项核对了候选的隐私、权利和脱敏上下文。'}
    saved = client.post('/creative/api/admin/learning/candidates/' + 'b' * 64 + '/review', json=body, headers=headers)
    assert saved.status_code == 200 and saved.json()['training_eligible'] is False
    receipt = next(review_dir.glob('*.json'))
    assert receipt.stat().st_mode & 0o777 == 0o600
    data = json.loads(receipt.read_text(encoding='utf-8'))
    assert 'reviewer_id' not in data and data['independent'] is True
    assert client.post('/creative/api/admin/learning/candidates/' + 'b' * 64 + '/review', json=body, headers=headers).status_code == 409


def test_candidate_queue_missing_is_explicit(client, tmp_path, monkeypatch):
    monkeypatch.setenv('AD_TRAINING_CANDIDATE_QUEUE', str(tmp_path / 'missing.json'))
    result = client.get('/creative/api/admin/learning/candidates', headers={'Authorization': 'Bearer admin'})
    assert result.status_code == 200 and result.json()['state'] == 'missing'


def test_creator_admin_cannot_review_own_candidate(client, tmp_path, monkeypatch):
    queue_path = tmp_path / 'queue.json'
    queue_path.write_text(json.dumps(queue_payload(creator=3)), encoding='utf-8'); queue_path.chmod(0o600)
    key = tmp_path / 'salt'; key.write_bytes(SALT); key.chmod(0o600)
    reviews = tmp_path / 'reviews'
    monkeypatch.setenv('AD_TRAINING_CANDIDATE_QUEUE', str(queue_path))
    monkeypatch.setenv('AD_TRAINING_REVIEW_DIR', str(reviews))
    monkeypatch.setenv('AD_LEARNING_SALT_FILE', str(key))
    body = {'privacy_review': True, 'rights_review': True, 'sanitized_context_review': True,
            'note': '逐项核对了候选的隐私、权利和脱敏上下文。'}
    response = client.post('/creative/api/admin/learning/candidates/' + 'b' * 64 + '/review',
                           json=body, headers={'Authorization': 'Bearer admin'})
    assert response.status_code == 409
    assert not reviews.exists()
    key.write_bytes(b'other-key-material-long-enough!!!!')
    response = client.post('/creative/api/admin/learning/candidates/' + 'b' * 64 + '/review',
                           json=body, headers={'Authorization': 'Bearer admin'})
    assert response.status_code == 409 and not reviews.exists()
