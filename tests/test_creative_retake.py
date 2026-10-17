"""Real media + fixed provider. Never contact a paid model."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import types

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from harness.studio import store, retake_api, edit_api
from harness.tools import creative_retake as retake
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_media import describe, source_catalog, digest
from harness.models import kling_retake

FFMPEG = '/tmp/visualagent-fftools/node_modules/ffmpeg-static/ffmpeg'
FFPROBE = '/tmp/visualagent-fftools/node_modules/ffprobe-static/bin/linux/x64/ffprobe'


@pytest.fixture
def media(tmp_path, monkeypatch):
    if not Path(FFMPEG).exists(): pytest.skip('ffmpeg is required for real retake media checks')
    monkeypatch.setenv('CREATIVE_FFMPEG', FFMPEG); monkeypatch.setenv('CREATIVE_FFPROBE', FFPROBE)
    monkeypatch.setenv('CREATIVE_RETAKE_INPUT_DIR', str(tmp_path / 'spool'))
    monkeypatch.setattr(store, 'DATA', tmp_path / 'data')
    store.LOCKS.clear(); store.RUNNING.clear()
    folder = store.DATA / 'artifacts' / ('b' * 24); folder.mkdir(parents=True)
    for name, color, hz in [('film', 'red', 440), ('candidate', 'blue', 880)]:
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', f'color={color}:s=1280x720:r=30:d=3',
            '-f', 'lavfi', '-i', f'sine=frequency={hz}:sample_rate=48000:duration=3', '-shortest',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', str(folder / (name + '.mp4'))], check=True)
    p = {'id': 'a' * 24, 'revision': 1, 'state': 'completed', 'aspect': '16:9', 'run_id': 'b' * 24,
         'generation_mode': 'single_native', 'film': {'state': 'completed'}, 'brief': {'product': 'fixture'}}
    catalog = source_catalog(p)
    p['edit'] = validate_edit({'sources': {'primary': catalog['primary']['sha256']},
        'clips': [{'source': 'primary', 'start': 0, 'end': 3, 'gain': .4, 'transition': {'kind': 'dissolve', 'duration': .4}},
                  {'source': 'primary', 'start': 0, 'end': 3}],
        'captions': [{'start': .5, 'end': 1.8, 'text': 'Hello jacket.', 'words': [
            {'start': 0, 'end': .4, 'text': 'Hello'}, {'start': .6, 'end': 1.1, 'text': ' jacket.'}], 'word_highlight': True}],
        'audio': [{'source': 'primary', 'start': 0, 'end': 2, 'at': 3, 'gain': .3}]}, catalog=catalog)
    store.save(p, 1)
    yield p, folder / 'candidate.mp4'
    store.LOCKS.clear(); store.RUNNING.clear()


def test_freeze_audio_restore_and_reversible_plan(media):
    p, raw = media
    original_edit = deepcopy(p['edit']); original_hash = digest(raw.parent / 'film.mp4')
    job = retake.prepare(p, 0, 'Warm the background; keep the jacket.')
    assert job['state'] == 'ready' and job['credits'] == 4 and job['duration'] == 3
    assert job['preserve_audio'] and job['training_eligible'] is False
    body = retake.payload(p, job); body.pop('provider')
    base = kling_retake.validate_request(body)
    assert not describe(base)['has_audio']  # Provider receives visual input only.
    assert describe(base)['duration'] == 3
    asset = retake.finish_candidate(p, job, raw)
    candidate = store.DATA / 'edit-assets' / p['id'] / asset['id'] / 'source.mp4'
    # Zero crossing rate of restored audio is ~440Hz, not the candidate's 880Hz.
    output = subprocess.check_output([FFMPEG, '-v', 'error', '-i', str(candidate), '-map', '0:a:0',
        '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
    import array
    samples = array.array('h', output)[4800:48000]
    cycles = sum(a < 0 <= b for a, b in zip(samples, samples[1:])) / (len(samples) / 48000)
    assert 435 < cycles < 445
    p['edit_assets'] = {asset['id']: asset}; job['state'] = 'completed'
    draft = retake.candidate_plan(p, job)
    assert draft['captions'] == original_edit['captions'] and draft['audio'] == original_edit['audio']
    assert draft['duration'] == original_edit['duration']
    assert draft['clips'][0]['gain'] == .4 and draft['clips'][0]['transition'] == original_edit['clips'][0]['transition']
    assert draft['clips'][0]['source'] == 'edit_' + job['id']
    assert draft['clips'][1] == original_edit['clips'][1] and p['edit'] == original_edit
    assert digest(raw.parent / 'film.mp4') == original_hash
    assert retake.finish_candidate(p, job, raw)['sha256'] == asset['sha256']  # Read-only recovery.
    p['edit']['clips'][1]['gain'] = .8
    with pytest.raises(ValueError, match='时间轴'): retake.candidate_plan(p, job)


def test_bounds_capability_tamper_and_output_mismatch(media, monkeypatch):
    p, raw = media
    short = deepcopy(p); short['edit']['clips'][0]['end'] = 2; short['edit']['audio'] = []
    with pytest.raises(ValueError, match='3–10'): retake.prepare(short, 0, 'light')
    job = retake.prepare(p, 0, 'light'); body = retake.payload(p, job); body.pop('provider')
    for mutation in [dict(enable_audio=True), dict(model='kling-video-v3_0'), dict(extra='ignored')]:
        with pytest.raises(ValueError): kling_retake.validate_request(dict(body, **mutation))
    forged = deepcopy(body); forged['conditions'][0]['reference'] = '../../private'
    with pytest.raises(ValueError): kling_retake.validate_request(forged)
    path = kling_retake.validate_request(body); path.write_bytes(b'x' * 2000)
    with pytest.raises(ValueError, match='changed'): kling_retake.validate_request(body)
    monkeypatch.setattr(retake, 'media_probe', lambda _: {'format': {'duration': '4'}, 'streams': [{'codec_type': 'video', 'width': 1280, 'height': 720}]})
    with pytest.raises(ValueError, match='时长'): retake.finish_candidate(p, job, raw)
    assert raw.is_file() and not p.get('edit_assets')


def test_provider_arguments_use_base_video_no_new_sound():
    d = kling_retake.provider_arguments({'prompt': '视频1 warm', 'target': {'duration_seconds': 4}}, 'https://upload.invalid/test')
    assert d['model'] == kling_retake.MODEL
    assert d['inputs'] == [{'name': 'video_1', 'inputType': 'URL', 'url': 'https://upload.invalid/test'}]
    values = {a['name']: a['value'] for a in d['arguments']}
    assert values['enable_audio'] == values['keepOriginalSound'] == values['prefer_multi_shots'] == 'false'
    assert values['imageCount'] == '1' and values['aspect_ratio'] == 'auto' and values['duration'] == '4'


def test_mcp_paid_call_once_after_preflight_and_upload(media, monkeypatch):
    from contextlib import contextmanager
    import httpx
    p, _ = media; job = retake.prepare(p, 0, 'light'); body = retake.payload(p, job); body.pop('provider')
    seen = []
    def cli(args):
        assert args == ['kling', 'who_am_i', '--quiet']; seen.append('discovery')
        return {'body': {'availableModels': {'omni_ref_video': {'models': [{'model': kling_retake.MODEL}]}}}}
    @contextmanager
    def connection():
        def call(name, args):
            seen.append(name)
            if name == 'file_upload': return {'ticket': 'private-ticket', 'uploadUrl': 'https://upload.invalid'}
            assert args['inputs'][0]['name'] == 'video_1'
            raise TimeoutError('provider private payload')
        class Client:
            def post(self, url, **kwargs):
                seen.append('upload'); assert kwargs['files']['file'][1].read(4)
                return httpx.Response(200, request=httpx.Request('POST', url), json={'url': 'https://uploaded.invalid'})
        yield call, Client()
    monkeypatch.setattr(kling_retake, 'connection', connection)
    with pytest.raises(RuntimeError, match='未重新生成') as error: kling_retake.submit(body, cli, 'kling')
    assert str(error.value) != 'provider private payload'
    assert seen == ['discovery', 'file_upload', 'upload', 'omni_ref_video']


@pytest.mark.parametrize('sse', [True, False])
def test_mcp_transport_single_attempt_and_bounded_result(sse):
    import httpx
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        result = {'jsonrpc': '2.0', 'id': 2, 'result': {'ok': True}}
        return httpx.Response(200, headers={'mcp-session-id': 'test-session', 'content-type': 'text/event-stream' if sse else 'application/json'},
            content=('event: message\ndata: ' + json.dumps(result) + '\n\n') if sse else json.dumps(result))
    headers = {}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert kling_retake._rpc(client, headers, {'id': 2, 'method': 'tools/call'}) == {'ok': True}
    assert len(calls) == 1 and headers['Mcp-Session-Id'] == 'test-session'


def make_client(monkeypatch, media, mode='complete'):
    p, raw = media; app = FastAPI(); calls = []
    def auth(a):
        if a == 'Bearer fixture': return {'id': 1}
        if a == 'Bearer other': return {'id': 2}
        raise HTTPException(401)
    gateway = types.SimpleNamespace(app=app, require_session=auth)
    edit_api.install(gateway); retake_api.install(gateway)
    async def submit(self, snapshot, job):
        calls.append('submit')
        assert store.load(p['id'], 1)['edit_retakes'][job['id']]['state'] == 'submitting'
        if mode == 'uncertain': raise TimeoutError('sensitive details must not escape')
        return {'id': 'existing_provider_job'}
    async def status(self, handle):
        calls.append('status'); assert handle == 'existing_provider_job'
        return {'status': 'completed', 'trajectory': {'shots': [{'id': 'main', 'duration': 3,
                'points': [[0, 0, 0], [1, 0, 0]], 'closed': False}]}}
    async def download(self, handle, destination):
        calls.append('download'); destination.write_bytes(raw.read_bytes())
    monkeypatch.setattr(retake.CreativeRetakeTool, 'submit_retake', submit)
    monkeypatch.setattr(retake.CreativeRetakeTool, 'status', status)
    monkeypatch.setattr(retake.CreativeRetakeTool, 'download', download)
    return TestClient(app, headers={'Authorization': 'Bearer fixture'}), calls


def wait_job(client, url):
    import time
    for _ in range(100):
        job = client.get(url).json()
        if job['state'] not in ('submitting', 'generating', 'checking'): return job
        time.sleep(.05)
    raise AssertionError('Job did not finish')


def test_api_owner_budget_exact_replay_and_no_timeline_overwrite(media, monkeypatch):
    p, raw = media; client, calls = make_client(monkeypatch, media)
    url = '/creative/api/projects/' + p['id'] + '/edit/retakes'
    with client:
        preview = client.post(url + '/preview', json={'revision': 1, 'clip_index': 0, 'intent': 'light'})
        assert preview.status_code == 200, preview.text
        job = preview.json(); route = url + '/' + job['id']; assert calls == []
        assert 'reference' not in job and 'provider_job_id' not in job
        assert client.get(route + '/input', headers={'Authorization': 'Bearer other'}).status_code == 404
        assert client.get(route, headers={'Authorization': 'Bearer other'}).status_code == 404
        approval = dict(revision=1, quote_digest=job['quote_digest'], approved_credits=job['credits'])
        assert client.post(route + '/generate', json=dict(approval, approved_credits=1)).status_code == 409
        assert calls == []
        monkeypatch.setattr(retake_api, 'quote', lambda *args: 8)
        assert client.post(route + '/generate', json=approval).status_code == 409
        monkeypatch.setattr(retake_api, 'quote', retake.quote)
        assert calls == []
        assert client.post(route + '/generate', json=approval).status_code == 200
        done = wait_job(client, route); assert done['state'] == 'completed', done
        assert done['qa']['semantic'] == 'pending' and not done['training_eligible']
        assert done['provider_poll']['status']=='completed' and done['provider_resolution']=='source_verified'
        assert client.post(route + '/generate', json=approval).status_code == 200
        assert calls.count('submit') == 1 and calls.count('download') == 1
        assert store.load(p['id'], 1)['edit'] == p['edit']
        plan = client.post(route + '/plan', json={'revision': done['project_revision']})
        assert plan.status_code == 200, plan.text
        assert plan.json()['spec']['captions'] == p['edit']['captions']
        assert store.load(p['id'], 1)['edit'] == p['edit']


def test_scene_retake_link_requires_current_approval_and_is_persisted(media, monkeypatch):
    p, _ = media; suggestion_id='d'*32
    p['scene_render_intent']={'scene_hash':'a'*64}
    p['scene_render_review']={'artifact_sha256':'b'*64}
    p['scene_retake_suggestions']={suggestion_id:{
        'id':suggestion_id,'state':'approved_for_generation','scene_hash':'a'*64,
        'artifact_sha256':'b'*64,'segments':[{'start':0,'end':3}]}}
    store.save(p,1);client, _ = make_client(monkeypatch, media)
    with client:
        base='/creative/api/projects/'+p['id']+'/edit/retakes'
        job=client.post(base+'/preview',json={'revision':1,'clip_index':0,'intent':'修正站位','scene_retake_id':suggestion_id})
        assert job.status_code==200,job.text;assert job.json()['scene_retake_id']==suggestion_id
        p['scene_render_review']['artifact_sha256']='f'*64;store.save(p,1)
        stale=client.post(base+'/preview',json={'revision':1,'clip_index':0,'intent':'再次修正','scene_retake_id':suggestion_id})
        assert stale.status_code==409


def test_uncertain_submit_stops_and_restart_only_resumes_known_handle(media, monkeypatch):
    p, _ = media; client, calls = make_client(monkeypatch, media, 'uncertain')
    base = '/creative/api/projects/' + p['id'] + '/edit/retakes'
    with client:
        job = client.post(base + '/preview', json={'revision': 1, 'clip_index': 0, 'intent': 'light'}).json()
        route = base + '/' + job['id']; approval = dict(revision=1, quote_digest=job['quote_digest'], approved_credits=4)
        client.post(route + '/generate', json=approval)
        result = wait_job(client, route); assert result['state'] == 'needs_review'
        assert 'sensitive' not in json.dumps(result)
        for _ in range(3): client.get(route); client.post(route + '/generate', json=approval)
        assert calls == ['submit']
        # Simulate persisted provider handle with an interrupted poll, not a new request.
        current = store.load(p['id'], 1); current['edit_retakes'][job['id']].update(state='generating', provider_job_id='existing_provider_job')
        store.save(current, 1)
        assert wait_job(client, route)['state'] == 'completed'
        assert calls.count('submit') == 1 and calls.count('download') == 1


def test_explicit_scene_batch_submits_each_approved_shot_once_and_replays_receipt(media, monkeypatch):
    p, raw = media
    suggestion_id = 'd' * 32
    p['scene_render_intent'] = {'scene_hash': 'a' * 64}
    p['scene_render_review'] = {'artifact_sha256': 'b' * 64}
    p['scene_retake_suggestions'] = {suggestion_id: {
        'id': suggestion_id, 'state': 'approved_for_generation',
        'model': retake.MODEL, 'model_label': 'Kling O3', 'intent': '保持商品细节，修正镜头光照',
        'scene_hash': 'a' * 64, 'artifact_sha256': 'b' * 64,
        'segments': [
            {'shot_id': 'main', 'name': '主镜头', 'start': 0, 'end': 3, 'duration': 3,
             'billable_duration': 3, 'credits': 4, 'note': '保持皮革纹理'},
            {'shot_id': 'detail', 'name': '细节镜头', 'start': 0, 'end': 3, 'duration': 3,
             'billable_duration': 3, 'credits': 4, 'note': '保留拉链高光'},
        ], 'credits': 8, 'training_eligible': False,
    }}
    p['scene_retake_batch_approvals'] = {suggestion_id: {
        'scene_retake_id': suggestion_id, 'revision': 1,
        'scene_hash': 'a' * 64, 'artifact_sha256': 'b' * 64,
        'shots': [{'shot_id': 'main', 'decision': 'approved', 'note': ''},
                  {'shot_id': 'detail', 'decision': 'approved', 'note': ''}],
        'receipt_sha256': 'c' * 64, 'training_eligible': False,
    }}
    store.save(p, 1)
    client, calls = make_client(monkeypatch, media)
    base = '/creative/api/projects/' + p['id'] + '/edit/retakes'
    body = {'revision': 1, 'scene_retake_id': suggestion_id,
            'approval_receipt_sha256': 'c' * 64, 'shot_ids': ['main', 'detail'],
            'approved_credits': 8, 'confirm': 'submit'}
    with client:
        first = client.post(base + '/batch', json=body)
        assert first.status_code == 200, first.text
        queue_id = first.json()['id']
        assert first.json()['training_eligible'] is False
        for _ in range(100):
            current = client.get(base + '/batch/' + queue_id).json()
            if current['state'] in ('completed', 'failed', 'needs_review'):
                break
            import time; time.sleep(.03)
        assert current['state'] == 'completed', current
        assert current['completed_count'] == 2
        assert len(current['jobs']) == 2
        assert all(job['state'] == 'completed' for job in current['jobs'])
        replay = client.post(base + '/batch', json=body)
        assert replay.status_code == 200 and replay.json()['id'] == queue_id
        assert calls.count('submit') == 2 and calls.count('download') == 2
        receipt = client.post('/creative/api/projects/' + p['id'] + '/edit/scene-retake-batch-receipt',
                              json={'revision': current['project_revision'], 'scene_retake_id': suggestion_id})
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()['receipt']['execution']['state'] == 'completed'
        assert 'provider_job_id' not in json.dumps(replay.json())


def test_scene_batch_stops_after_uncertain_first_submission_without_retry(media, monkeypatch):
    p, _ = media
    suggestion_id = 'e' * 32
    p['scene_render_intent'] = {'scene_hash': 'a' * 64}
    p['scene_render_review'] = {'artifact_sha256': 'b' * 64}
    p['scene_retake_suggestions'] = {suggestion_id: {
        'id': suggestion_id, 'state': 'approved_for_generation', 'model': retake.MODEL,
        'scene_hash': 'a' * 64, 'artifact_sha256': 'b' * 64, 'intent': '修正镜头',
        'segments': [{'shot_id': 'main', 'name': '主镜头', 'start': 0, 'end': 3, 'duration': 3,
                      'billable_duration': 3, 'credits': 4},
                     {'shot_id': 'detail', 'name': '细节镜头', 'start': 0, 'end': 3, 'duration': 3,
                      'billable_duration': 3, 'credits': 4}], 'credits': 8,
        'training_eligible': False,
    }}
    p['scene_retake_batch_approvals'] = {suggestion_id: {
        'scene_retake_id': suggestion_id, 'revision': 1, 'scene_hash': 'a' * 64,
        'artifact_sha256': 'b' * 64, 'shots': [{'shot_id': 'main', 'decision': 'approved'},
                                                {'shot_id': 'detail', 'decision': 'approved'}],
        'receipt_sha256': 'f' * 64, 'training_eligible': False,
    }}
    store.save(p, 1)
    client, calls = make_client(monkeypatch, media, 'uncertain')
    base = '/creative/api/projects/' + p['id'] + '/edit/retakes'
    body = {'revision': 1, 'scene_retake_id': suggestion_id, 'approval_receipt_sha256': 'f' * 64,
            'shot_ids': ['main', 'detail'], 'approved_credits': 8, 'confirm': 'submit'}
    with client:
        queue = client.post(base + '/batch', json=body).json()
        for _ in range(100):
            current = client.get(base + '/batch/' + queue['id']).json()
            if current['state'] in ('completed', 'failed', 'needs_review'):
                break
            import time; time.sleep(.03)
        assert current['state'] == 'needs_review'
        assert current['completed_count'] == 0
        assert current['jobs'][0]['state'] == 'needs_review'
        assert current['jobs'][1]['state'] == 'ready'
        replay = client.post(base + '/batch', json=body)
        assert replay.status_code == 200 and replay.json()['id'] == queue['id']
        assert calls == ['submit']
