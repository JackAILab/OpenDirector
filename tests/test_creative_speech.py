import copy
import json
import time
import asyncio
import pytest
from harness.studio import store,edit_api
from harness.core import creative_speech_runner as runner
from harness.tools.creative_transcript import normalize_transcript,caption_plan,speech_findings,evidence_for
from harness.tools.creative_edit import validate_edit
from test_creative_edit import client,source_project


def speech():
    return normalize_transcript({'language':'en','language_probability':.99,'segments':[{'words':[
        {'start':1,'end':1.6,'text':'Hello','probability':.99}, {'start':1.7,'end':2.2,'text':' jacket.','probability':.8}]}]},5)


def job(sha='hash'):
    return {'id':'a'*32,'source':'primary','source_sha256':sha,'model':'fixture','language':'en','state':'completed','result':speech()}


def test_transcript_rejects_bad_timing_music_and_normalizes_without_raw_payload():
    clean=speech();assert len(clean['words'])==2 and clean['segments'][0]['text']=='Hello jacket.'
    assert clean['training_eligible'] is False
    for word in [dict(start=-1,end=1,text='bad',probability=.9),dict(start=1,end=9,text='bad',probability=.9),dict(start=1,end=2,text='♪',probability=.9),dict(start=float('nan'),end=2,text='bad',probability=.9)]:
        with pytest.raises(ValueError):normalize_transcript(dict(language='en',language_probability=.9,segments=[dict(words=[word])]),5)
    assert normalize_transcript(dict(language='en',language_probability=.9,segments=[]),5)['words']==[]


def test_caption_projection_reorder_preserves_other_text_and_omits_cut_words():
    spec=validate_edit(dict(source_sha256='hash',clips=[dict(start=3,end=5),dict(start=.5,end=2.5)],captions=[dict(start=2.5,end=4,text='Original',track=0)]),5,'hash')
    before=copy.deepcopy(spec)
    p={'edit_transcriptions':{'a':job()}};catalog={'primary':dict(sha256='hash',duration=5,kind='video',has_audio=True)}
    plan=caption_plan(p,spec,catalog);assert plan['added']==1
    assert plan['spec']['captions'][-1]==dict(start=2.5,end=3.7,text='Hello jacket.',track=1,word_highlight=True,words=[dict(text='Hello',start=0,end=.6),dict(text=' jacket.',start=.7,end=1.2)],appearance={'preset':'plain','size':'medium','motion':'none'})
    assert plan['spec']['captions'][0]==before['captions'][0] and spec==before
    assert not evidence_for({'edit_transcriptions':{'a':job('old')}},spec)
    clipped=validate_edit(dict(source_sha256='hash',clips=[dict(start=1.4,end=2.5)]),5,'hash')
    result=caption_plan(p,clipped,catalog)
    assert result['omitted_words']==1 and result['spec']['captions'][0]['text']=='jacket.'
    assert speech_findings(clipped,evidence_for(p,clipped))[0]['kind']=='word_cut'


def test_caption_plan_cannot_overwrite_occupied_tracks():
    spec=validate_edit(dict(source_sha256='hash',clips=[dict(start=0,end=4)],captions=[dict(start=0,end=4,text=str(i),track=i) for i in range(3)]),5,'hash')
    with pytest.raises(ValueError,match='三层'):caption_plan({'edit_transcriptions':{'a':job()}},spec,{'primary':dict(sha256='hash',duration=5,kind='video',has_audio=True)})


def test_transcription_jobs_are_owned_idempotent_hash_bound_and_not_auto_subtitles(client,monkeypatch):
    p=source_project(client,monkeypatch);base='/creative/api/projects/'+p['id']+'/edit';calls=[]
    monkeypatch.setattr(edit_api,'speech_settings',lambda:dict(available=True,model='fixture',local=True))
    def transcribe(*args):calls.append(1);time.sleep(.08);return speech()
    monkeypatch.setattr(runner,'transcribe_source',transcribe)
    before=client.get(base).json()['spec'];body=dict(revision=p['revision'],request_id='a'*32,source='primary',language='en')
    assert client.post(base+'/transcriptions',json=body).status_code==200
    assert client.post(base+'/transcriptions',json=body).status_code==200
    path=base+'/transcriptions/'+body['request_id']
    for _ in range(100):
        r=client.get(path).json()
        if r['state']!='running':break
        time.sleep(.02)
    assert r['state']=='completed' and len(calls)==1
    assert client.get(base).json()['spec']==before
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(base+'/transcriptions',json=dict(body,language='zh')).status_code==409
    spec=dict(before,captions=[])
    plan=client.post(base+'/caption-plan',json=dict(revision=p['revision'],spec=spec));assert plan.status_code==200
    assert plan.json()['added']==1 and 'edit' not in store.load(p['id'],1)
    (store.DATA/'artifacts/existing/film.mp4').write_bytes(b'changed')
    assert client.get(path).json()['stale']
    assert client.post(base+'/caption-plan',json=dict(revision=p['revision'],spec=spec)).status_code==422
    with store.connection() as c:events=c.execute('select data from projects').fetchall()
    assert store.present(store.load(p['id'],1))['events'][-1]['code']=='edit_speech_recognized'


def test_failure_has_no_payload_or_automatic_retry(client,monkeypatch):
    p=source_project(client,monkeypatch);base='/creative/api/projects/'+p['id']+'/edit'
    monkeypatch.setattr(edit_api,'speech_settings',lambda:dict(available=True,model='fixture',local=True));calls=[]
    def fail(*args):calls.append(1);raise ValueError('private raw transcript')
    monkeypatch.setattr(runner,'transcribe_source',fail)
    body=dict(revision=p['revision'],request_id='b'*32,source='primary',language='auto')
    client.post(base+'/transcriptions',json=body)
    for _ in range(100):
        r=client.get(base+'/transcriptions/'+body['request_id']).json()
        if r['state']!='running':break
        time.sleep(.01)
    assert r['state']=='failed' and 'private' not in json.dumps(r)
    client.post(base+'/transcriptions',json=body);assert len(calls)==1


def test_agent_receives_only_selected_speech_as_unreviewed_evidence(monkeypatch):
    from harness.agents import creative_editor
    received=[]
    async def complete(self,messages):received.append(messages);return {'fixture':True}
    monkeypatch.setattr(creative_editor.CreativeDirectorModel,'complete',complete)
    spec={'sources':{'primary':'hash'},'clips':[{'source':'primary','start':1,'end':2.5}]}
    obs={'primary':{'words':speech()['words']+[{'start':4,'end':4.5,'text':'outside'}]}}
    result=asyncio.run(creative_editor.propose_edit(spec,[],'test',{'primary':{'kind':'video','duration':5,'has_audio':True}},obs))
    data=json.loads(received[0][1]['content'][0]['text'])
    assert result=={'fixture':True} and data['speech']['primary']['review']=='pending'
    assert len(data['speech']['primary']['words'])==2 and 'outside' not in json.dumps(data)


def test_word_projection_uses_transition_clock_and_repeated_source_occurrences():
    catalog={'primary':dict(sha256='hash',duration=5,kind='video',has_audio=True)}
    spec=dict(source_sha256='hash',clips=[dict(start=.5,end=2.5,transition=dict(kind='dissolve',duration=.4)),dict(start=.5,end=2.5)])
    captions=caption_plan({'edit_transcriptions':{'a':job()}},spec,catalog)['spec']['captions']
    assert [(c['start'],c['end']) for c in captions]==[(.5,1.7),(2.1,3.3)]
    assert captions[0]['words']==captions[1]['words']==[dict(text='Hello',start=0,end=.6),dict(text=' jacket.',start=.7,end=1.2)]


def test_legacy_speech_caption_upgrades_without_duplicate_or_restyling():
    catalog={'primary':dict(sha256='hash',duration=5,kind='video',has_audio=True)}
    old=dict(start=1,end=2.2,text='Hello jacket.',track=2,appearance=dict(preset='box',size='large',motion='rise'))
    spec=dict(source_sha256='hash',clips=[dict(start=0,end=4)],captions=[old],caption_visibility=[True,True,False])
    result=caption_plan({'edit_transcriptions':{'a':job()}},spec,catalog)
    assert result['added']==0 and result['upgraded']==1 and result['first_index']==0
    assert len(result['spec']['captions'])==1 and 'words' not in old
    c=result['spec']['captions'][0]
    assert c['appearance']==old['appearance'] and c['track']==2 and len(c['words'])==2
    assert result['spec']['caption_visibility']==[True,True,False]
    with pytest.raises(ValueError,match='已加入'):caption_plan({'edit_transcriptions':{'a':job()}},result['spec'],catalog)
