"""Actual pixels and owned/non-overwriting API behavior for deterministic reframing."""
import io
import hashlib
import pytest
from PIL import Image, ImageDraw
from test_creative_studio import client, ready


def source(c):
    p=ready(c);url='/creative/api/projects/'+p['id']
    image=Image.new('RGB',(400,200),'white');d=ImageDraw.Draw(image)
    d.rectangle((0,0,199,99),fill='red');d.rectangle((200,0,399,99),fill='green');d.rectangle((0,100,199,199),fill='blue')
    raw=io.BytesIO();image.save(raw,format='PNG')
    r=c.post(url+'/canvas/assets',params={'kind':'image','revision':p['revision']},content=raw.getvalue()).json()
    p=r['project'];aid=r['asset']['id']
    p=c.put(url+'/canvas',json={'revision':p['revision'],'nodes':[{'id':'original','asset':aid,'kind':'image','label':'四色原图','x':40,'y':30}],'edges':[]}).json()
    return p,url,aid


def test_pixels_source_preservation_lineage_and_idempotency(client):
    p,url,aid=source(client);original=client.get(url+'/canvas/assets/'+aid+'/source').content
    body={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'crop':[0,0,.5,.5],'rotation':90,'mirror':True}
    response=client.post(url+'/image-reframe',json=body);assert response.status_code==200,response.text
    data=response.json();q=data['project'];result=data['edit']['result_asset']
    assert result!=aid and q['revision']==p['revision']+1
    assert q['state']==p['state'] and q['shots']==p['shots'] and q['canvas']['edges']==p['canvas']['edges']
    assert q['canvas_lineage'][result]['kind']=='image_reframe'
    assert q['canvas_lineage'][result]['sources']==[aid]
    assert data['edit']['training_eligible'] is False
    assert data['edit']['source_sha256']==hashlib.sha256(original).hexdigest()
    out=Image.open(io.BytesIO(client.get(url+'/canvas/assets/'+result+'/source').content))
    assert out.size==(100,200)
    r,g,b=out.getpixel((50,100));assert r>220 and g<20 and b<20
    assert client.get(url+'/canvas/assets/'+aid+'/source').content==original
    again=client.post(url+'/image-reframe',json=body);assert again.status_code==200
    assert again.json()['edit']['result_asset']==result and len(again.json()['project']['canvas_assets'])==2
    assert client.post(url+'/image-reframe',json={**body,'rotation':180}).status_code==409
    assert client.post(url+'/image-reframe',json={**body,'request_id':'b'*32}).status_code==409
    assert client.post(url+'/image-reframe',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.app.state.test_account_limits['used']==0


@pytest.mark.parametrize('crop', [[-.1,0,.5,.5],[0,0,1.1,1],[.8,0,.5,.5],[0,0,0,1],[0,0,.001,.001]])
def test_bounds_reject_without_asset_creation(client,crop):
    p,url,aid=source(client)
    r=client.post(url+'/image-reframe',json={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'crop':crop})
    assert r.status_code==422,r.text
    after=client.get(url).json();assert after['revision']==p['revision'] and len(after['canvas_assets'])==1


def test_foreign_source_and_busy_state(client):
    from harness.studio import store
    p,url,aid=source(client);body={'revision':p['revision'],'asset':'f'*32,'request_id':'a'*32,'crop':[0,0,1,1]}
    assert client.post(url+'/image-reframe',json=body).status_code==422
    saved=store.load(p['id'],1);saved['image_task']={'state':'running'};store.save(saved,1)
    assert client.post(url+'/image-reframe',json={**body,'asset':aid}).status_code==409
