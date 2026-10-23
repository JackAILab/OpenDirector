import copy
import json
import subprocess
import pytest
from harness.tools.creative_edit import validate_edit
from harness.evaluators.creative_edit import evaluate_edit_proposal
from test_creative_edit import client,source_project


def document():
    return {'source_sha256':'hash','clips':[{'start':0,'end':4}],
            'captions':[{'start':.5,'end':2,'text':'<script>literal</script>','track':0}],
            'caption_visibility':[True,False,True]}


def test_caption_presentation_is_bounded_and_legacy_visible():
    clean=validate_edit(document(),4,'hash')
    assert clean['version']==5 and clean['captions'][0]['appearance']=={'preset':'box','size':'medium','motion':'none'}
    assert clean['caption_visibility']==[True,False,True]
    old=document();old.pop('caption_visibility');assert validate_edit(old,4,'hash')['caption_visibility']==[True]*3
    for field,value in [('preset','url(x)'),('size',99),('motion','arbitrary-script'),('color','red')]:
        raw=document();raw['captions'][0]['appearance']={field:value}
        with pytest.raises(ValueError):validate_edit(raw,4,'hash')
    for visibility in [[True],['true',True,True],[1,True,True],{'0':False}]:
        with pytest.raises(ValueError):validate_edit(dict(document(),caption_visibility=visibility),4,'hash')


def test_agent_cannot_hide_reveal_or_restyle_user_captions():
    original=validate_edit(document(),4,'hash');catalog={'primary':{'sha256':'hash','kind':'video','duration':4,'has_audio':True}}
    def proposal(spec):return {'spec':spec,'summary':'Keep words','reasons':[{'text':'Sampled frame','frames':['f1']}]}
    assert evaluate_edit_proposal(proposal(original),original,catalog,[{'id':'f1','source':'primary','time':1}])
    for kind in ('visibility','style','track'):
        edited=copy.deepcopy(original)
        if kind=='visibility':edited['caption_visibility'][0]=False
        elif kind=='style':edited['captions'][0]['appearance']['motion']='rise'
        else:edited['captions'][0]['track']=1
        with pytest.raises(ValueError):evaluate_edit_proposal(proposal(edited),original,catalog,[])


def test_presentation_survives_owner_save_reload_and_conflicts(client,monkeypatch):
    p=source_project(client,monkeypatch);url='/creative/api/projects/'+p['id']+'/edit'
    spec=client.get(url).json()['spec'];spec['caption_visibility']=[False,True,True]
    spec['captions']=[{'start':1,'end':2,'text':'Preserved hidden text','track':0,'appearance':{'preset':'accent','size':'large','motion':'rise'}}]
    response=client.put(url,json={'revision':p['revision'],'spec':spec});assert response.status_code==200
    returned=client.get(url).json()['spec'];assert returned['captions']==spec['captions'] and returned['caption_visibility']==spec['caption_visibility']
    assert client.put(url,json={'revision':p['revision'],'spec':spec}).status_code==409
    assert client.get(url,headers={'Authorization':'Bearer two'}).status_code==404


def test_caption_pose_is_time_based_and_relative_to_frame_size():
    script="""global.window={};require('./tools/agent_studio/editor-captions.js');
    const c={start:1,end:2,track:0,appearance:{preset:'plain',size:'medium',motion:'rise'}},e=window.EditCaptions;
    console.log(JSON.stringify({a:e.pose(c,1.09,1280,720),b:e.pose(c,1.09,640,360),repeat:e.pose(c,1.09,1280,720),end:e.pose(c,2,1280,720),short:e.pose({...c,end:1.2},1.025,1280,720),hidden:e.visible({caption_visibility:[false,true,true]},c)}));"""
    result=json.loads(subprocess.check_output(['node','-e',script],text=True))
    assert result['a']['opacity']==pytest.approx(.75)
    assert result['a']['y']==pytest.approx(result['b']['y']*2)
    assert result['repeat']==result['a'] and result['end']['opacity']==0 and result['hidden'] is False
    assert result['short']['opacity']==pytest.approx(.75)


def test_caption_side_layout_survives_validation_and_shared_renderer():
    raw=document();raw['captions'][0]['appearance']={'align':'left','preset':'plain'}
    clean=validate_edit(raw,4,'hash')
    assert clean['captions'][0]['appearance']['align']=='left'
    raw['captions'][0]['appearance']['align']='url(external)'
    with pytest.raises(ValueError):validate_edit(raw,4,'hash')
    script="""global.window={};require('./tools/agent_studio/editor-captions.js');
    const e=window.EditCaptions,out={};
    for(const align of ['left','right','center']){const slot={style:{}},effect={style:{}};
      e.style(slot,effect,{track:2,appearance:{align,preset:'plain'}},1280,720);
      out[align]=slot.style;}
    console.log(JSON.stringify(out));"""
    rendered=json.loads(subprocess.check_output(['node','-e',script],text=True))
    assert rendered['left']['left']=='6%' and rendered['left']['width']=='40%'
    assert rendered['right']['left']=='54%' and rendered['right']['width']=='40%'
    assert rendered['center']['left']=='8%' and rendered['center']['width']=='84%'
    assert all(v['bottom']=='33%' for v in rendered.values())
