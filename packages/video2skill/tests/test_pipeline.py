import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from video2skill.compiler import export, verify_bundle
from video2skill.schema import Evidence, Source
from video2skill.runner import Store, run
from video2skill.service import create_app
from video2skill.harness.tools.media import sample

EXAMPLE = Path(__file__).parents[1] / 'examples/evidence.json'

@pytest.fixture
def evidence():
    return Evidence.model_validate_json(EXAMPLE.read_text())


def test_reproducible_non_overwriting_bundle(tmp_path, evidence):
    assert export(evidence, tmp_path/'a') == export(evidence, tmp_path/'b')
    assert verify_bundle(tmp_path/'a')['valid']
    assert (tmp_path/'a/manifest.json').read_bytes() == (tmp_path/'b/manifest.json').read_bytes()
    with pytest.raises(FileExistsError): export(evidence, tmp_path/'a')
    (tmp_path/'a/SKILL.md').write_text('changed')
    with pytest.raises(ValueError, match='checksum'): verify_bundle(tmp_path/'a')


def test_recomputed_hash_does_not_bypass_review(tmp_path, evidence):
    export(evidence, tmp_path/'bundle')
    root = tmp_path/'bundle'
    (root/'review.json').write_text('{"training_eligible":true}')
    manifest = json.loads((root/'manifest.json').read_text())
    manifest['files']['review.json'] = hashlib.sha256((root/'review.json').read_bytes()).hexdigest()
    (root/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Review'): verify_bundle(root)

@pytest.mark.parametrize('mutation', ['frame', 'window', 'nan', 'duplicate'])
def test_invalid_evidence(evidence, mutation):
    data = evidence.model_dump()
    if mutation == 'frame': data['analysis']['beats'][0]['frames'] = [3]
    if mutation == 'window': data['analysis']['beats'][0]['end'] = 11
    if mutation == 'nan': data['duration'] = float('nan')
    if mutation == 'duplicate': data['frame_times'] = [1,1,7,9]
    with pytest.raises(ValidationError): Evidence.model_validate(data)

@pytest.mark.parametrize('url', ['https://user:secret@example.org/v','https://example.org/v?token=secret','file:///tmp/video'])
def test_private_citations_rejected(url):
    with pytest.raises(ValidationError): Source(title='Example', source_url=url)


def test_low_confidence_cannot_compile(tmp_path, evidence):
    evidence.analysis.confidence = 'low'
    with pytest.raises(ValueError): export(evidence, tmp_path/'bundle')
    assert not (tmp_path/'bundle').exists()


def test_queue_and_restart(tmp_path):
    store = Store(tmp_path)
    ids = [store.create() for _ in range(8)]
    with pytest.raises(ValueError, match='queue_full'): store.create()
    (tmp_path/ids[0]/'input.bin').write_bytes(b'source')
    store.recover()
    assert all(store.get(i)['state'] == 'interrupted' for i in ids)
    assert not (tmp_path/ids[0]/'input.bin').exists()
    assert store.create()


def test_provider_error_not_in_trajectory(tmp_path, monkeypatch, evidence):
    store = Store(tmp_path)
    identity = store.create()
    monkeypatch.setattr('video2skill.runner.sample', lambda *a: {})
    def fail(*a): raise RuntimeError('api_key=private provider raw response')
    monkeypatch.setattr('video2skill.runner.analyze', fail)
    run(store, identity, evidence.source)
    result = store.get(identity)
    assert result['error'] == 'analyzing_failed'
    assert 'private' not in json.dumps(result)

@pytest.fixture
def video(tmp_path):
    if not shutil.which('ffmpeg'): pytest.skip('ffmpeg is required for media integration')
    path = tmp_path/'synthetic.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=128x96:d=10:r=2','-c:v','mpeg4',str(path)],check=True)
    return path


def test_actual_media_sampling(tmp_path, video):
    result = sample(video, tmp_path/'frames', count=4)
    assert result['frame_times'] == [0,3.166667,6.333333,9.5]
    assert len(list((tmp_path/'frames').glob('*.jpg'))) == 4
    assert result['media_sha256'] == hashlib.sha256(video.read_bytes()).hexdigest()


def test_http_end_to_end(tmp_path, video, monkeypatch, evidence):
    monkeypatch.setattr('video2skill.service.configured', lambda: True)
    def analyze(source, media, frames, language):
        result = evidence.analysis.model_copy(deep=True)
        for beat in result.beats:
            beat.frames = [i for i,t in enumerate(media['frame_times']) if beat.start <= t < beat.end]
        return result
    monkeypatch.setattr('video2skill.runner.analyze', analyze)
    token = 'test-only-token-with-32-characters'
    auth = {'Authorization':'Bearer '+token}
    with TestClient(create_app(tmp_path/'store', token)) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/v1/jobs/unknown').status_code == 401
        request = {'source':evidence.source.model_dump_json()}
        files = {'video':('sample.mp4',video.read_bytes(),'video/mp4')}
        assert client.post('/v1/jobs',data=request,files=files,headers=auth).status_code == 422
        request['allow_model_call'] = 'true'
        assert client.post('/v1/jobs',data=request,files={'video':('empty.mp4',b'')},headers=auth).status_code == 422
        response = client.post('/v1/jobs',data=request,files=files,headers=auth)
        assert response.status_code == 202, response.text
        identity = response.json()['id']
        for _ in range(200):
            state = client.get('/v1/jobs/'+identity,headers=auth).json()
            if state['state'] in ('completed','failed'): break
            time.sleep(.05)
        assert state['state'] == 'completed', state
        assert [e['state'] for e in state['events']] == ['queued','sampling','analyzing','compiling','completed']
        result = client.get(f'/v1/jobs/{identity}/artifacts/skill.json',headers=auth)
        assert result.status_code == 200
        assert result.json()['review']['training_eligible'] is False
        assert client.get(f'/v1/jobs/{identity}/artifacts/input.bin',headers=auth).status_code == 404
        assert verify_bundle(tmp_path/'store'/identity/'bundle')['valid']
        assert not (tmp_path/'store'/identity/'input.bin').exists()


def test_adapter_uses_one_explicit_model_call(tmp_path, monkeypatch, evidence):
    from types import SimpleNamespace
    from video2skill.harness.models import vision
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            assert kwargs['timeout'] == 180
            self.chat = SimpleNamespace(completions=self)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=evidence.analysis.model_dump_json()))])
    monkeypatch.setenv('V2S_MODEL', 'test-vision')
    monkeypatch.setenv('V2S_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setattr(vision, 'OpenAI', Client)
    for i in range(4): (tmp_path/f'{i:02}.jpg').write_bytes(b'synthetic-frame')
    assert vision.analyze(evidence.source, evidence.model_dump(), tmp_path) == evidence.analysis
    assert len(calls) == 1
    assert calls[0]['model'] == 'test-vision'
    assert len(calls[0]['messages'][1]['content']) == 5
    assert vision.method()['model'] == 'test-vision'
    assert len(vision.method()['prompt_sha256']) == 64
