import copy
import json
import subprocess
import pytest
from harness.tools.creative_edit import validate_edit
from harness.evaluators.creative_edit import evaluate_edit_proposal
from test_creative_edit import client,source_project


def caption():
    return dict(start=.5,end=2,text='Hello jacket.',track=0,word_highlight=True,
                words=[dict(text='Hello',start=0,end=.4),dict(text=' jacket.',start=.6,end=1.1)])


def document():
    return dict(source_sha256='hash',clips=[dict(start=0,end=4)],captions=[caption()])


def test_words_roundtrip_and_move_preserve_relative_cadence():
    clean=validate_edit(document(),4,'hash');assert clean['version']==5
    c=clean['captions'][0];assert c['words']==caption()['words']
    c.update(start=2,end=3.5)
    assert validate_edit(clean,4,'hash')['captions'][0]['words']==caption()['words']
    c['end']=2.8
    with pytest.raises(ValueError,match='逐词时间'):validate_edit(clean,4,'hash')


@pytest.mark.parametrize('mutation',[
 lambda c:c.update(words=[]),lambda c:c.update(words='bad'),lambda c:c.update(word_highlight=1),
 lambda c:c.update(words=None),lambda c:c.update(text='different'),
 lambda c:c['words'][0].update(start=-.1),lambda c:c['words'][0].update(end=float('nan')),
 lambda c:c['words'][0].update(start=True),lambda c:c['words'][0].update(end=.01),
 lambda c:c['words'][1].update(start=.3),lambda c:c['words'][1].update(end=2),
 lambda c:c['words'][1].update(text=' '),lambda c:c.update(words=[{}]*121),
])
def test_reject_corrupt_or_invented_alignment(mutation):
    d=document();mutation(d['captions'][0])
    with pytest.raises(ValueError):validate_edit(d,4,'hash')


def test_agent_must_preserve_word_corrections_and_highlight():
    original=validate_edit(document(),4,'hash');catalog={'primary':dict(sha256='hash',kind='video',duration=4,has_audio=True)}
    for field in ('word_highlight','words','drop'):
        spec=copy.deepcopy(original)
        if field=='drop':spec['captions'][0].pop('words');spec['captions'][0].pop('word_highlight')
        elif field=='words':spec['captions'][0]['words'][0]['end']=.3
        else:spec['captions'][0][field]=False
        with pytest.raises(ValueError,match='逐词'):evaluate_edit_proposal(dict(spec=spec),original,catalog,[])


def test_word_drafts_save_reload_ownership_and_revision(client,monkeypatch):
    p=source_project(client,monkeypatch);url='/creative/api/projects/'+p['id']+'/edit'
    spec=client.get(url).json()['spec'];spec['captions']=[caption()]
    response=client.put(url,json=dict(revision=p['revision'],spec=spec));assert response.status_code==200
    returned=client.get(url).json()['spec']['captions'][0]
    assert returned['words']==caption()['words'] and returned['word_highlight']
    assert client.put(url,json=dict(revision=p['revision'],spec=spec)).status_code==409
    assert client.get(url,headers={'Authorization':'Bearer two'}).status_code==404


def test_word_highlight_boundaries_gaps_reverse_seek_and_no_guessing():
    script="""global.window={};require('./tools/agent_studio/editor-captions.js');
    const c=JSON.parse(process.argv[1]),e=window.EditCaptions;
    console.log(JSON.stringify({indices:[.49,.5,.899,.9,1,1.1,1.6,2,1.3,.5].map(t=>e.activeWord(c,t)),plain:e.activeWord({...c,words:undefined},1),off:e.activeWord({...c,word_highlight:false},1.3),short:e.wordsFit({...c,end:1})}));"""
    r=json.loads(subprocess.check_output(['node','-e',script,json.dumps(caption())],text=True))
    assert r['indices']==[-1,0,0,-1,-1,1,-1,-1,1,0]
    assert r['plain']==r['off']==-1 and not r['short']
