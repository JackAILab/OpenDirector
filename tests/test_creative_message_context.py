"""Historical context is immutable private UI data, not a new model/paid input."""
import io
import pytest
from PIL import Image
from harness.studio import api, store
from harness.tools.creative_message_context import record_message_context
from test_creative_studio import client, ready


def test_new_message_snapshots_actual_inputs_without_changing_conversation(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    assert p['message_contexts']['0']['skill']['title']==p['skill_title']
    assert set(p['messages'][0])=={'role','content'}
    a,b='a'*32,'b'*32
    p=store.load(p['id'],1)
    p.update(canvas_assets={a:{'kind':'image'},b:{'kind':'image'}},
             canvas={'nodes':[{'id':'a','kind':'image','asset':a,'label':'夹克原图','role':'product','x':0,'y':0},{'id':'b','kind':'image','asset':b,'label':'导演辅助','role':'reference','x':300,'y':0}],'edges':[]},
             video_inputs={'model':p['model'],'mode':'references','references':[{'asset':a,'role':'product','instruction':'保留拉链','sha256':'c'*64,'transport_sha256':'d'*64}]},
             video_inputs_product=p['brief']['product'])
    store.save(p,1)
    result=client.post(url+'/message',json={'revision':p['revision'],'text':'请保留这件夹克的结构','request_id':'1234567890abcdef1234567890abcdef','mode':'plan'})
    assert result.status_code==200
    saved=result.json();index=len(p['messages']);snapshot=saved['message_contexts'][str(index)]
    assert snapshot['references']==[{'asset':a,'role':'product','label':'夹克原图'}]
    assert not snapshot['needs_review'] and '导演辅助' not in str(snapshot)
    assert snapshot['revision']==p['revision']
    assert all(set(m)=={'role','content'} for m in saved['messages'])
    again=client.post(url+'/message',json={'revision':p['revision'],'text':'请保留这件夹克的结构','request_id':'1234567890abcdef1234567890abcdef','mode':'plan'}).json()
    assert again['message_contexts']==saved['message_contexts']
    current=store.load(p['id'],1);current['model']='kling-video-v3_0_omni';current['video_inputs']['references']=[];current['canvas']['nodes'][0]['label']='新名字';store.save(current,1)
    assert client.get(url).json()['message_contexts'][str(index)]==snapshot
    assert all('夹克原图' not in str(e) for e in saved['events'])


def test_explicit_text_mode_and_foreign_inputs_are_not_historical_attachments():
    p={'messages':[{'role':'user','content':'hello'}],'provider':'kling','model':'kling-video-v3_0_omni',
       'reference':{'id':'b'*32},'video_inputs':{'model':'kling-video-v3_0_omni','mode':'text','references':[]}}
    record_message_context(p);assert p['message_contexts']['0']['references']==[]
    p['video_inputs']={'model':'old','mode':'references','references':[{'asset':'foreign','role':'product'}]}
    record_message_context(p);assert not p['message_contexts']['0']['needs_review']
    p['messages'].append({'role':'user','content':'next'})
    record_message_context(p);snapshot=p['message_contexts']['1'];assert snapshot['needs_review'] and snapshot['references']==[]


def test_legacy_reference_history_is_owned_and_survives_replacement(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    def upload(p,color):
        raw=io.BytesIO();Image.new('RGB',(320,180),color).save(raw,format='PNG')
        response=client.post(url+'/reference',params={'revision':p['revision']},content=raw.getvalue())
        assert response.status_code==200,response.text
        return response.json()
    p=upload(p,'red');index=len(p['messages'])-1;path=url+f'/messages/{index}/references/0'
    original=client.get(path);assert original.status_code==200
    assert original.headers['cache-control']=='private, no-store'
    p=upload(p,'blue');assert client.get(path).content==original.content
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(url+'/messages/0/references/0').status_code==404
    assert client.get(url+f'/messages/{index}/references/-1').status_code==404
    assert client.get(url+f'/messages/{index}/references/7').status_code==404
    from harness.tools.creative_reference import reference_path
    historical=p['message_contexts'][str(index)]['references'][0]
    reference_path({**p,'reference':{'id':historical['reference_id']}}).unlink()
    assert client.get(path).status_code==404


def test_context_survives_planning_failure_without_backfilling_old_messages(client,monkeypatch):
    p=ready(client);url='/creative/api/projects/'+p['id']
    p=store.load(p['id'],1);p.pop('message_contexts',None);store.save(p,1)
    async def failed(*args):raise RuntimeError('fixture failed')
    monkeypatch.setattr(api,'direct',failed)
    assert client.post(url+'/message',json={'revision':p['revision'],'text':'需要更清楚的拉链动作','mode':'plan'}).status_code==502
    saved=store.load(p['id'],1);assert list(saved['message_contexts'])==[str(len(p['messages']))]
    assert saved['training_eligible'] is False


def test_canvas_history_preview_survives_node_removal_but_requires_owned_asset(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(240,180),'green').save(raw,format='PNG')
    uploaded=client.post(url+'/canvas/assets',params={'kind':'image','revision':p['revision']},content=raw.getvalue()).json()
    p=store.load(p['id'],1);aid=uploaded['asset']['id'];p['model']='kling-video-v3_0_omni'
    p['video_inputs']={'model':p['model'],'mode':'references','references':[{'asset':aid,'role':'product'}]}
    p['messages'].append({'role':'user','content':'保留这张参考'})
    index=len(p['messages'])-1;record_message_context(p);p['canvas']={'nodes':[],'edges':[]};store.save(p,1)
    path=url+f'/messages/{index}/references/0'
    result=client.get(path);assert result.status_code==200
    assert result.content==client.get(url+'/canvas/assets/'+aid+'/preview').content
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    p['canvas_assets']={};store.save(p,1)
    assert client.get(path).status_code==404
