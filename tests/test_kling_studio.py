"""No paid calls: crash recovery, polling and model selection contracts."""
import json
import pytest
from harness.models import kling_studio as adapter

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(adapter,'OUTPUT_DIR',tmp_path)
    monkeypatch.setattr(adapter,'JOBS',{'kling_test':{'id':'kling_test','status':'processing'}})
    monkeypatch.setattr(adapter,'POLLING',{'kling_test'})
    monkeypatch.setattr(adapter,'ACTIVE',True)
    return tmp_path


def test_submission_handle_is_durable_before_poll(setup,monkeypatch):
    calls=[]
    def cli(args):
        calls.append(args[1])
        if args[1]=='text_to_video':return {'body':{'generation_id':'gen_123'}}
        saved=json.loads(adapter.state_path('kling_test').read_text())
        assert saved['generation_id']=='gen_123'
        return {'body':{'generations':[{'status':'PROCESSING'}]}}
    monkeypatch.setattr(adapter,'cli_result',cli)
    adapter.run_generation('kling_test',['kling','text_to_video'])
    assert calls==['text_to_video','query_tasks']
    assert adapter.JOBS['kling_test']['status']=='processing'
    adapter.JOBS.clear();adapter.load_states()
    assert adapter.JOBS['kling_test']['generation_id']=='gen_123'
    adapter.poll_generation('kling_test')
    assert calls==['text_to_video','query_tasks','query_tasks']


def test_ambiguous_submission_never_becomes_refundable_failure(setup,monkeypatch):
    def fail(args):raise TimeoutError()
    monkeypatch.setattr(adapter,'cli_result',fail)
    adapter.run_generation('kling_test',['kling','text_to_video'])
    assert adapter.JOBS['kling_test']['status']=='uncertain'
    assert adapter.ACTIVE


def test_only_confirmed_terminal_error_releases_worker(setup,monkeypatch):
    adapter.JOBS['kling_test']['generation_id']='gen_123'
    monkeypatch.setattr(adapter,'cli_result',lambda args:{'body':{'status':'FAILED'}})
    adapter.poll_generation('kling_test')
    assert adapter.JOBS['kling_test']['status']=='failed'
    assert not adapter.ACTIVE

@pytest.mark.parametrize('model',['kling-video-v2_5','kling-video-v3_0','kling-video-v3_0_omni'])
def test_canonical_model_and_submit_without_long_poll(model):
    args=adapter.generation_args({'task':'t2va','prompt':'bottle','model':model,'target':{'duration_seconds':5}})
    assert args[args.index('--model')+1]==model
    assert args[args.index('--poll')+1]=='0'
    assert ('--prefer_multi_shots' in args)==(model!='kling-video-v2_5')


@pytest.mark.parametrize('model',['kling-video-v2_5','kling-video-v3_0','kling-video-v3_0_omni'])
def test_image_request_uses_selected_model_and_local_reference(setup,model):
    import base64,io
    from PIL import Image
    output=io.BytesIO();Image.new('RGB',(320,180),'white').save(output,'JPEG')
    uri='data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode()
    body={'task':'fl2va','prompt':'same lamp','model':model,'conditions':[{'type':'image','role':'keyframe','frame_index':0,'uri':uri}],'target':{'duration_seconds':5}}
    args=adapter.generation_args(body)
    assert args[1]=='image_to_video' and args[args.index('--model')+1]==model
    path=setup/'references'/args[args.index('--image')+1].split('/')[-1]
    assert path.read_bytes()==output.getvalue()
    assert args[args.index('--poll')+1]=='0'
    body['conditions'][0]['uri']='http://127.0.0.1/private'
    with pytest.raises(Exception) as caught:adapter.generation_args(body)
    assert caught.value.status_code==422


@pytest.mark.parametrize('provider,expected', [
    ({'status': 'QUEUED'}, {'stage': 'queued'}),
    ({'status': 'PROCESSING', 'progress': 43}, {'stage': 'generating', 'progress': 43}),
    ({'status': 'PROCESSING', 'progress': float('nan')}, {'stage': 'generating'}),
    ({'status': 'PROCESSING', 'progress': True}, {'stage': 'generating'}),
    ({'status': 'PROCESSING', 'progress': {'private': 'secret'}}, {'stage': 'generating'}),
])
def test_live_poll_is_single_read_and_projects_safe_progress(setup, monkeypatch, provider, expected):
    adapter.JOBS['kling_test'].update(generation_id='gen_123', progress=20)
    calls = []
    def query(args):
        calls.append(args)
        return {'body': {'generations': [dict(provider, url='https://private.invalid/signed', token='secret')]}}
    monkeypatch.setattr(adapter, 'cli_result', query)
    adapter.poll_generation('kling_test')
    assert len(calls) == 1
    assert calls[0][1] == 'query_tasks'
    assert calls[0][calls[0].index('--poll') + 1] == '0'
    saved = json.loads(adapter.state_path('kling_test').read_text())
    assert {k: saved[k] for k in ('stage', 'progress') if k in saved} == expected
    assert saved['checked_at'] > 0
    assert saved['status'] == 'processing'
    assert 'private' not in str(saved) and 'secret' not in str(saved)
    assert adapter.ACTIVE
