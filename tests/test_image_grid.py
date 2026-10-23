"""Grid pixels, ownership, idempotency and all-or-nothing persistence."""
import io
import pytest
from PIL import Image, ImageChops
from test_creative_studio import client
from test_image_reframe import source
from harness.studio import store


def test_grid_pixels_lineage_and_idempotency(client):
    p,url,aid=source(client);raw=client.get(url+'/canvas/assets/'+aid+'/source').content
    original=Image.open(io.BytesIO(raw)).convert('RGB')
    body={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'rows':2,'columns':3}
    r=client.post(url+'/image-grid',json=body);assert r.status_code==200,r.text
    data=r.json();q=data['project'];ids=data['edit']['result_assets'];assert len(ids)==6
    assert q['revision']==p['revision']+1 and q['shots']==p['shots'] and q['state']==p['state']
    assert q['canvas']['edges']==p['canvas']['edges']
    reconstructed=Image.new('RGB',original.size)
    for result in ids:
        record=q['canvas_lineage'][result];assert record['sources']==[aid] and record['kind']=='image_grid'
        box=record['grid']['pixel_box'];out=Image.open(io.BytesIO(client.get(url+'/canvas/assets/'+result+'/source').content))
        assert out.size==(box[2]-box[0],box[3]-box[1]);reconstructed.paste(out,tuple(box[:2]))
    assert ImageChops.difference(original,reconstructed).getbbox() is None
    assert data['edit']['training_eligible'] is False
    assert client.get(url+'/canvas/assets/'+aid+'/source').content==raw
    again=client.post(url+'/image-grid',json=body);assert again.status_code==200 and again.json()['edit']==data['edit']
    assert len(again.json()['project']['canvas_assets'])==7
    assert client.post(url+'/image-grid',json={**body,'columns':2}).status_code==409
    assert client.post(url+'/image-grid',json={**body,'request_id':'b'*32}).status_code==409
    assert client.post(url+'/image-grid',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.app.state.test_account_limits['used']==0


@pytest.mark.parametrize('patch',[{'rows':3,'columns':2},{'rows':True},{'asset':'f'*32}])
def test_invalid_request_unchanged(client,patch):
    p,url,aid=source(client);body={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'rows':2,'columns':2}
    assert client.post(url+'/image-grid',json={**body,**patch}).status_code==422
    q=client.get(url).json();assert q['revision']==p['revision'] and len(q['canvas_assets'])==1


def test_capacity_and_busy(client):
    p,url,aid=source(client);body={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'rows':2,'columns':2}
    saved=store.load(p['id'],1);saved['image_task']={'state':'running'};store.save(saved,1)
    assert client.post(url+'/image-grid',json=body).status_code==409
    saved['image_task']={};saved['canvas']['nodes']=[{**saved['canvas']['nodes'][0],'id':str(i)} for i in range(13)];store.save(saved,1)
    assert client.post(url+'/image-grid',json=body).status_code==422
    assert len(client.get(url).json()['canvas_assets'])==1


def test_partial_save_failure_rolls_back(client,monkeypatch):
    from harness.studio import image_grid_api
    from harness.tools.creative_canvas import asset_directory
    p,url,aid=source(client);created=[];save=image_grid_api.save_asset
    def failing_save(*args,**kwargs):
        if created:raise ValueError('test disk failure')
        asset=save(*args,**kwargs);created.append(asset['id']);return asset
    monkeypatch.setattr(image_grid_api,'save_asset',failing_save)
    r=client.post(url+'/image-grid',json={'revision':p['revision'],'asset':aid,'request_id':'a'*32,'rows':2,'columns':2})
    assert r.status_code==422
    saved=store.load(p['id'],1);assert saved['revision']==p['revision'] and len(saved['canvas_assets'])==1
    assert not asset_directory(saved,created[0]).exists()
