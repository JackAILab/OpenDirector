import asyncio
import copy
import json
import subprocess
import time
import pytest
from harness.studio import store
from harness.core import creative_edit_runner as runner
from harness.evaluators.creative_edit import evaluate_edit_proposal
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_timing import schedule
from test_creative_edit import client, source_project


def base_spec():
    return dict(source_sha256='hash',clips=[dict(start=1,end=5,transition=dict(kind='dissolve',duration=1)),dict(start=7,end=10)],captions=[],audio=[],volume=1)


def test_transitions_overlap_clock_and_invalid_cases():
    spec=base_spec();clean=validate_edit(spec,15,'hash')
    assert clean['duration']==6 and schedule(clean['clips'])[1]['at']==3
    bads=[]
    for transition in [dict(kind='cut',duration=.5),dict(kind='unknown',duration=1),dict(kind='dissolve',duration=2),dict(kind='dissolve',duration=float('nan')),dict(kind='dissolve',duration=-1)]:
        bad=copy.deepcopy(spec);bad['clips'][0]['transition']=transition;bads.append(bad)
    bad=copy.deepcopy(spec);bad['clips'][1]['transition']=dict(kind='fade_black',duration=.2);bads.append(bad)
    bad=copy.deepcopy(spec);bad['captions']=[dict(start=5.9,end=6.5,text='outside new clock')];bads.append(bad)
    for bad in bads:
        with pytest.raises(ValueError):validate_edit(bad,15,'hash')


def test_python_and_preview_clocks_agree_and_dissolve_has_no_black_dip():
    clips=validate_edit(base_spec(),15,'hash')['clips']
    script="global.window={};require('./tools/agent_studio/editor-timing.js');console.log(JSON.stringify({schedule:EditTiming.schedule(CLIPS),poses:EditTiming.poses(CLIPS,3.5)}))".replace('EditTiming','window.EditTiming').replace('CLIPS',json.dumps(clips))
    result=json.loads(subprocess.check_output(['node','-e',script],text=True))
    assert result['schedule']==schedule(clips)
    assert [p['opacity'] for p in result['poses']]==[1,.5]
    assert [p['gain'] for p in result['poses']]==[.5,.5]
    assert [p['source'] for p in result['poses']]==[4.5,7.5]


def response(original):
    return dict(spec=copy.deepcopy(original),summary='保留片段，采样尚不足以证明口播可裁切。',reasons=[dict(text='首帧展示商品。',frames=['frame_1'])])


def test_evaluator_rejects_new_words_sources_gain_and_unobserved_windows():
    original=validate_edit(dict(source_sha256='hash',clips=[dict(start=2,end=8)],captions=[dict(start=0,end=2,text='保留文字')]),15,'hash')
    catalog={'primary':dict(sha256='hash',duration=15,kind='video',has_audio=True)}
    frames=[dict(id='frame_1',source='primary',time=3)]
    assert evaluate_edit_proposal(response(original),original,catalog,frames)['qa']['training_eligible'] is False
    bads=[]
    bad=response(original);bad['spec']['clips'][0]['start']=1;bads.append(bad)
    bad=response(original);bad['spec']['clips'][0]['gain']=.3;bads.append(bad)
    bad=response(original);bad['spec']['captions'][0]['text']='invented';bads.append(bad)
    bad=response(original);bad['reasons'][0]['frames']=['unknown'];bads.append(bad)
    for bad in bads:
        with pytest.raises(ValueError):evaluate_edit_proposal(bad,original,catalog,frames)


def prepare(client,monkeypatch):
    p=source_project(client,monkeypatch);base='/creative/api/projects/'+p['id']+'/edit'
    spec=client.get(base).json()['spec'];saved=client.put(base,json=dict(revision=p['revision'],spec=spec)).json()
    monkeypatch.setattr(runner,'observe_edit',lambda *args:[dict(id='frame_1',source='primary',time=1,image='data:image/jpeg;base64,fixture')])
    return p,base,saved


def wait_for(client,path):
    for _ in range(150):
        job=client.get(path).json()
        if job['state']!='running':return job
        time.sleep(.01)
    pytest.fail('job did not finish')


def test_suggestion_is_single_attempt_owned_non_applying_and_revision_bound(client,monkeypatch):
    p,base,saved=prepare(client,monkeypatch);calls=[]
    async def propose(original,*args):
        calls.append(1);await asyncio.sleep(.1);return response(original)
    monkeypatch.setattr(runner,'propose_edit',propose)
    body=dict(revision=saved['revision'],request_id='1'*32,intent='保留商品展示')
    r=client.post(base+'/suggestions',json=body);assert r.status_code==200
    assert client.put(base,json=dict(revision=saved['revision'],spec=saved['spec'])).status_code==409
    assert client.post(base+'/suggestions',json=body).json()['id']==body['request_id']
    path=base+'/suggestions/'+body['request_id'];job=wait_for(client,path)
    assert job['state']=='completed' and len(calls)==1
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    current=store.load(p['id'],1)
    assert current['edit']==saved['spec'] and current['revision']==saved['revision']
    assert current['artifact']==p['artifact'] and client.app.state.test_account_limits['used']==0
    assert client.post(base+'/suggestions',json=dict(body,intent='changed')).status_code==409
    assert client.post(base+'/suggestions',json=body).status_code==200 and len(calls)==1
    assert client.put(base,json=dict(revision=saved['revision'],spec=saved['spec'])).status_code==200
    assert client.get(path).json()['stale'] is True
    events=store.present(current)['events']
    assert all('保留商品展示' not in json.dumps(e) and 'data:image' not in json.dumps(e) for e in events)


def test_failed_suggestion_does_not_retry_or_leak_provider_payload(client,monkeypatch):
    p,base,saved=prepare(client,monkeypatch);calls=[]
    async def fail(*args):calls.append(1);raise RuntimeError('provider-secret-payload')
    monkeypatch.setattr(runner,'propose_edit',fail)
    body=dict(revision=saved['revision'],request_id='2'*32,intent='更紧凑')
    client.post(base+'/suggestions',json=body);job=wait_for(client,base+'/suggestions/'+body['request_id'])
    assert job['state']=='failed' and 'secret' not in json.dumps(job)
    client.post(base+'/suggestions',json=body)
    assert len(calls)==1 and store.load(p['id'],1)['edit']==saved['spec']


def test_actual_agent_passes_sparse_observations_to_model_once(monkeypatch):
    from harness.agents.creative_editor import propose_edit, CreativeDirectorModel
    calls=[]
    async def complete(self,messages):calls.append(messages);return {'fixture':True}
    monkeypatch.setattr(CreativeDirectorModel,'complete',complete)
    original=validate_edit(base_spec(),15,'hash')
    result=asyncio.run(propose_edit(original,[dict(id='frame_1',source='primary',time=1,image='data:image/jpeg;base64,fixture')],'快节奏',{}))
    assert result=={'fixture':True} and len(calls)==1
    assert calls[0][1]['content'][-1]['image_url']['url'].startswith('data:image/jpeg')
    assert '未听到音频' in calls[0][0]['content']
