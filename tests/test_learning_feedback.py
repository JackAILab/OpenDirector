import json
import sqlite3

from harness.learning import feedback
from harness.learning.episodes import inspect_episode
from harness.studio import store
from test_creative_studio import client, ready


def test_owner_plan_feedback_is_version_bound_and_redacted(client):
    p = ready(client)
    url = '/creative/api/projects/' + p['id'] + '/learning/feedback'
    body = {'revision': p['revision'], 'decision': 'revise', 'rating': 3,
            'strategy_indices': [0, 0], 'changed_dimensions': ['audio', 'story'],
            'note': '请把联系人 a@example.com 的链接 https://private.invalid 去掉'}
    result = client.post(url, json=body).json()
    assert result['training_eligible'] is False
    assert '[REDACTED_EMAIL]' in result['note'] and '[REDACTED_URL]' in result['note']
    history = client.get(url).json()
    assert history['count'] == 1 and history['latest']['strategy_indices'] == [0]
    assert history['training_eligible'] is False
    assert client.post(url, json={**body, 'revision': p['revision'] - 1}).status_code == 409
    assert client.post(url, json={**body, 'decision': 'unknown'}).status_code == 422
    assert client.post(url, json={**body, 'rating': 0}).status_code == 422


def test_feedback_is_append_only_and_episode_sanitizer_keeps_bounded_fields(client):
    p = ready(client)
    feedback.record(p, 1, 'keep', 5, [1], ['claim'], '保留结构')
    store.event(p, 'learning', 'plan_feedback_recorded')
    report = inspect_episode(p['id'], 1)
    revision = next(item for item in report['revisions'] if item['revision'] == p['revision'])
    assert revision['feedback'][0]['decision'] == 'keep'
    with sqlite3.connect(store.DATA / 'learning' / 'episodes.sqlite3') as db:
        row = db.execute('SELECT data FROM learning_feedback').fetchone()
        payload = json.loads(row[0]); payload['decision'] = 'reject'
        db.execute('UPDATE learning_feedback SET data=?', (json.dumps(payload),))
    try:
        inspect_episode(p['id'], 1)
    except ValueError as exc:
        assert 'Feedback integrity' in str(exc)
    else:
        raise AssertionError('tampered feedback must fail closed')


def test_feedback_aggregate_contains_no_project_or_note_content(client):
    p = ready(client)
    feedback.record(p, 1, 'keep', 4, [2], ['audio', 'shots'], '声音需要更有层次')
    result = feedback.aggregate()
    assert result['feedback_count'] == 1
    assert result['rating_mean'] == 4
    assert result['decisions'] == {'keep': 1}
    assert result['changed_dimensions'] == {'audio': 1, 'shots': 1}
    assert result['strategy_indices'] == {'2': 1}
    assert '声音需要' not in str(result)
    assert result['training_eligible'] is False
