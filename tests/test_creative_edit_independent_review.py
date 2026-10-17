import json
import time

from harness.studio import edit_api, store
from harness.tools.creative_edit_media import digest
from test_creative_edit import client, source_project


def _ratings():
    return {key: {'score': 4, 'evidence': '完整回看中记录了对应画面或声音证据'} for key in (
        'product_fidelity', 'claim_accuracy', 'narrative', 'visual_quality', 'audio_quality')}


def _exported(c, monkeypatch):
    p = source_project(c, monkeypatch)
    base = '/creative/api/projects/' + p['id'] + '/edit'
    doc = c.get(base).json()
    saved = c.put(base, json={'revision': p['revision'], 'spec': doc['spec']})
    assert saved.status_code == 200
    revision = saved.json()['revision']
    approved = {'revision': revision, 'decision': 'approved',
                'checks': {'full_video_watched': True, 'audio_listened': True, 'product_facts_checked': True}}
    assert c.post(base + '/review', json=approved).status_code == 200

    def render(project, spec, directory):
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'final.mp4').write_bytes(b'edit-film')
        (directory / 'edit.json').write_text(json.dumps(spec, ensure_ascii=False))
        return {'technical': 'passed', 'audio': True, 'training_eligible': False}

    monkeypatch.setattr(edit_api, 'render_edit', render)
    job = c.post(base + '/export', json={'revision': revision}).json()
    for _ in range(100):
        result = c.get(base).json()
        if result['export']['state'] == 'completed':
            break
        time.sleep(.01)
    assert result['export']['state'] == 'completed'
    export = result['export']
    requested = c.post(base + '/review/request', json={'revision': revision, 'export_id': export['id']})
    assert requested.status_code == 200, requested.text
    assert requested.json()['request']['status'] == 'pending_independent_review'
    return p, export


def test_edit_export_requires_owner_review_then_independent_admin_receipt(client, monkeypatch):
    c = client
    p, export = _exported(c, monkeypatch)
    queue = c.get('/creative/api/admin/learning/edit/queue', headers={'Authorization': 'Bearer admin'})
    assert queue.status_code == 200 and queue.json()['items'][0]['export_id'] == export['id']
    url = '/creative/api/admin/learning/edit/projects/' + p['id'] + '/exports/' + export['id']
    detail = c.get(url, headers={'Authorization': 'Bearer admin'})
    assert detail.status_code == 200
    d = detail.json()
    assert d['training_eligible'] is False and d['assessment'] is None
    assert c.get(url + '/media', params={'revision': export['revision'], 'digest': export['artifact_sha256']},
                 headers={'Authorization': 'Bearer admin'}).content == b'edit-film'
    body = {'export_id': export['id'], 'revision': export['revision'],
            'artifact_sha256': export['artifact_sha256'], 'decision': 'passed',
            'ratings': _ratings(),
            'checks': {'full_video_watched': True, 'audio_listened': True, 'product_facts_checked': True}}
    result = c.post(url + '/assessment', json=body, headers={'Authorization': 'Bearer admin'})
    assert result.status_code == 200 and result.json()['independent']
    assert result.json()['training_eligible'] is False
    assert c.get('/creative/api/admin/learning/edit/queue', headers={'Authorization': 'Bearer admin'}).json()['items'] == []
    assert c.get(url, headers={'Authorization': 'Bearer admin'}).json()['assessment']['decision'] == 'passed'


def test_edit_independent_review_rejects_owner_and_changed_media(client, monkeypatch):
    c = client
    p, export = _exported(c, monkeypatch)
    url = '/creative/api/admin/learning/edit/projects/' + p['id'] + '/exports/' + export['id']
    assert c.get(url, headers={'Authorization': 'Bearer one'}).status_code == 403
    final = store.DATA / 'edits' / p['id'] / export['id'] / 'final.mp4'
    final.write_bytes(b'tampered')
    assert c.get(url, headers={'Authorization': 'Bearer admin'}).status_code == 409
    assert c.get('/creative/api/admin/learning/edit/queue', headers={'Authorization': 'Bearer admin'}).json()['items'] == []
