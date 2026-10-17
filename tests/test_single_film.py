"""Single paid film contract: storyboard beats never become individual submissions."""
import asyncio
import types
import pytest
from test_creative_studio import client, ready
from harness.tools.creative_video import CreativeVideoTool, film_prompt
from harness.models import kling_studio
from harness.core import creative_runner as runner
from harness.studio import store


def test_one_request_compiles_all_timecodes_and_audio(client):
    p=ready(client);p['run_id']='one-film';calls=[]
    tool=CreativeVideoTool(None,'unused')
    async def request(method,path,**kw):
        calls.append(kw);return types.SimpleNamespace(json=lambda:{'id':'whole-film'})
    tool.request=request
    asyncio.run(tool.submit_film(p))
    assert len(calls)==1
    body=calls[0]['json']
    assert body['target']['duration_seconds']==15
    assert body['enable_audio'] is True and body['prefer_multi_shots'] is True
    assert all(f'[{n}–{n+5} seconds]' in body['prompt'] for n in (0,5,10))
    assert calls[0]['headers']['Idempotency-Key']=='one-film-film'
    args=kling_studio.generation_args(body)
    assert args[args.index('--enable_audio')+1]=='true'
    assert args[args.index('--prefer_multi_shots')+1]=='true'
    p['shots'][1]['start']=6
    with pytest.raises(RuntimeError):film_prompt(p)


def test_confirmed_3d_handoff_is_bounded_camera_guidance(client):
    p=ready(client)
    p['scene_render_intent']={
        'trajectory_sha256':'a'*64,
        'trajectory':{'shots':[{'shot_id':'main','duration':5,'path_points':8,'path_closed':True,'path_easing':'smooth'}]},
    }
    prompt=film_prompt(p)
    assert '3D staging handoff' in prompt and 'Trajectory lock aaaaaaaaaaaa' in prompt
    assert 'Camera main: 5s, 8 path points, closed loop, smooth easing.' in prompt
    assert 'points' not in prompt.split('Trajectory lock',1)[0]


def test_unsupported_short_or_unverified_models_rejected(client):
    for params in ({'duration':10},{'duration':20},{'model':'kling-video-v2_5'}, {'provider':'minimax-h3','model':'MiniMax-H3'}):
        assert client.post('/creative/api/projects',json={'message':'广告制作',**params}).status_code==422


@pytest.mark.parametrize('mode', [None, 'segments'])
def test_film_rejects_legacy_mode_before_paid_submission(client, mode):
    p = ready(client)
    p['generation_mode'] = mode
    tool = CreativeVideoTool(None, 'unused')
    async def request(*args, **kwargs):
        raise AssertionError('invalid film mode must never reach paid submission')
    tool.request = request
    with pytest.raises(RuntimeError, match='原生有声一次生成'):
        asyncio.run(tool.submit_film(p))


def test_resume_keeps_one_job_and_one_source(client,monkeypatch,tmp_path):
    p=ready(client);p['run_id']='film-resume';store.save(p,1)
    monkeypatch.setattr(runner,'DATA',tmp_path)
    calls=[]
    class Video:
        def __init__(self,*args):pass
        async def submit_film(self,project):calls.append('submit');return {'id':'one'}
        async def status(self,job):
            calls.append('query')
            return {'status':'completed','trajectory':{'shots':[{'id':'main','duration':5,'points':[[0,0,0],[1,0,0]],'closed':False}]}}
        async def download(self,job,path):path.write_bytes(b'source')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    monkeypatch.setattr(runner,'verify_native_audio',lambda *a:{'audio':True})
    attempts=[]
    def render(project,path):
        attempts.append(path)
        assert sorted(f.name for f in path.glob('*.mp4'))==['film.mp4']
        if len(attempts)==1:raise RuntimeError('renderer interrupted')
        (path/'final.mp4').write_bytes(b'final');return {'audio':True,'technical':'passed'}
    monkeypatch.setattr(runner,'render',render)
    asyncio.run(runner.production(None,p,1,'unused'))
    p=store.load(p['id'],1)
    assert p['state']=='paused' and p['film']['job_id']=='one'
    assert store.present(p)['quote']['credits']==0
    asyncio.run(runner.production(None,p,1,'unused'))
    assert calls==['submit','query']
    p=store.load(p['id'],1)
    assert p['state']=='completed' and not p['training_eligible']
    assert p['film']['provider_trajectory']['source']=='provider_status'
    assert 'points' not in p['film']['provider_trajectory']['shots'][0]
    assert p['film']['provider_poll']['status']=='completed'
    assert p['film']['provider_resolution']=='source_verified'
    assert attempts[0]!=attempts[1]
    shots=p['shots'][::-1]
    assert client.patch('/creative/api/projects/'+p['id']+'/timeline',json={'revision':p['revision'],'shots':shots}).status_code==409


def test_silent_source_never_delivers_or_retries(client,monkeypatch,tmp_path):
    p=ready(client);p['run_id']='silent';p['film']={'job_id':'existing','state':'generating'};store.save(p,1)
    monkeypatch.setattr(runner,'DATA',tmp_path)
    class Video:
        def __init__(self,*a):pass
        async def status(self,job):return {'status':'completed'}
        async def download(self,job,path):path.write_bytes(b'silent')
        async def submit_film(self,*a):raise AssertionError('must not resubmit')
    def reject(*a):raise RuntimeError('整片缺少完整音轨，不能交付。')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    monkeypatch.setattr(runner,'verify_native_audio',reject)
    asyncio.run(runner.production(None,p,1,'unused'))
    p=store.load(p['id'],1)
    assert p['state']=='paused' and not p.get('artifact') and '音轨' in p['error']


@pytest.mark.parametrize('sound,passes',[('anullsrc=r=16000:cl=mono',False),('sine=frequency=440:sample_rate=16000',True)])
def test_actual_audio_gate_detects_silence(tmp_path,monkeypatch,sound,passes):
    import subprocess
    from harness.tools import creative_render
    ffmpeg='/opt/visualstation/creative-runtime/bin/ffmpeg'
    monkeypatch.setenv('CREATIVE_FFMPEG',ffmpeg)
    monkeypatch.setattr(creative_render,'FFPROBE','/opt/visualstation/creative-runtime/bin/ffprobe')
    file=tmp_path/'audio-gate.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=black:s=32x32:r=10','-f','lavfi','-i',sound,'-t','15','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(file)],check=True,timeout=30)
    if passes:assert creative_render.verify_native_audio(file,15)['audio']
    else:
        with pytest.raises(RuntimeError,match='静音'):creative_render.verify_native_audio(file,15)


def test_native_delivery_records_real_artifact_digest_without_training_approval(client,monkeypatch,tmp_path):
    import hashlib
    from harness.learning.episodes import inspect_episode
    p=ready(client);p['run_id']='captured-film';store.save(p,1)
    monkeypatch.setattr(runner,'DATA',tmp_path)
    class Video:
        def __init__(self,*args):pass
        async def submit_film(self,project):return {'id':'private-job-id'}
        async def status(self,job):return {'status':'completed'}
        async def download(self,job,path):path.write_bytes(b'source')
    monkeypatch.setattr(runner,'CreativeVideoTool',Video)
    monkeypatch.setattr(runner,'verify_native_audio',lambda *a:{'audio':True})
    def render(project,path):
        (path/'final.mp4').write_bytes(b'final-native-film')
        return {'audio':True,'technical':'passed','duration':15,'width':1280,'height':720}
    monkeypatch.setattr(runner,'render',render)
    asyncio.run(runner.production(None,p,1,'private-authorization'))
    report=inspect_episode(p['id'],1);revision=report['revisions'][-1]
    assert revision['missing_evidence']==[]
    assert revision['artifacts'][0]['artifact_sha256']==hashlib.sha256(b'final-native-film').hexdigest()
    assert not revision['training_eligible']
    assert all(e['code']!='artifact_capture_failed' for e in store.present(p)['events'])
    assert 'private-job-id' not in str(report) and 'private-authorization' not in str(report)
