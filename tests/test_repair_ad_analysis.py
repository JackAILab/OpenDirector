import json

from harness.library import learning, store
from tools.repair_ad_analysis import repair


def test_repair_is_local_and_preserves_failed_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    identity, _ = store.ingest({'title': '测试案例', 'source_url': 'https://example.org/ad'})
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                  (identity, f'assets/{identity}/film.mp4', 'a' * 64, 10, 15, 1, 1280, 720, 0))
    evidence_dir = tmp_path / 'learning' / 'evidence' / identity
    evidence_dir.mkdir(parents=True)
    frames = [{'time': 1, 'path': '00.jpg'}, {'time': 10, 'path': '01.jpg'}]
    (evidence_dir / 'evidence.json').write_text(json.dumps({'frames': frames}))
    candidate = {
        'media_role': 'original_ad', 'confidence': 'medium',
        'principle': '用动作证明卖点', 'mechanism': '动作变化形成结果',
        'beats': [{'start': 1, 'end': 1, 'observation': '动作', 'purpose': '建立注意', 'frames': [0]}],
        'grill_questions': ['事实？'], 'transfer_rules': ['重新设计'], 'avoid': ['不要复制'],
    }
    (evidence_dir / 'candidate.json').write_text(json.dumps(candidate))
    failed = {'state': 'failed', 'error_code': 'ValueError', 'automatic_retry': False}
    (evidence_dir / 'analysis-attempt.json').write_text(json.dumps(failed))
    result = repair(identity)
    assert result['provider_called'] is False
    assert result['training_eligible'] is False
    assert result['repairs'][0]['kind'] == 'zero_length_beat'
    assert learning.get_analysis(identity)['beats'][0]['end'] == 10
    assert json.loads((evidence_dir / 'analysis-attempt-history.jsonl').read_text())['error_code'] == 'ValueError'
