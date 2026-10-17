import asyncio
import io
import json
import sqlite3
import time
import types
import pytest
from PIL import Image
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from harness.studio import api,store,image_api
from test_creative_studio import client,ready


def test_image_variant_uses_selected_node_source(tmp_path,monkeypatch):
    from harness.tools import creative_image
    from harness.tools.creative_canvas import save_asset,asset_directory
    monkeypatch.setattr(store,'DATA',tmp_path)
    raw=io.BytesIO();Image.new('RGB',(64,64),'blue').save(raw,'PNG')
    p={'id':'c'*24};asset=save_asset(p,raw.getvalue(),'image');p['canvas_assets']={asset['id']:asset}
    seen=[]
    def generate(model,prompt,aspect,output,reference):seen.append(reference);return raw.getvalue()
    monkeypatch.setattr(creative_image,'generate',generate)
    p['aspect']='1:1'
    result=creative_image.create_image(p,{'model':'hunyuan-image-v2.0-general-edit','prompt':'侧光','id':'d'*32,'source_asset':asset['id']})
    assert seen==[asset_directory(p,asset['id'])/asset['filename']]
    assert result['id']!=asset['id']
    assert result['provenance']['sources']==[asset['id']] and result['provenance']['kind']=='image_edit'


def test_model_switch_invalidates_plan_and_checks_owner_revision(client):
    p=ready(client);path='/creative/api/projects/'+p['id'];body={'revision':p['revision'],'model':'kling-video-v3_0_omni'}
    assert client.put(path+'/model',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.put(path+'/model',json={**body,'model':'fake'}).status_code==422
    changed=client.put(path+'/model',json=body).json()
    assert changed['state']=='intake' and changed['shots']==[] and changed['provider']=='kling'
    assert client.put(path+'/model',json=body).status_code==409
    assert client.post(path+'/execute',json={'revision':changed['revision'],'approved_credits':100}).status_code==409


def test_image_task_credits_idempotency_ownership_and_recovery(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'creative');store.RUNNING.clear();store.LOCKS.clear()
    dbpath=tmp_path/'gateway.sqlite3'
    def db():return sqlite3.connect(dbpath)
    with db() as c:
        c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)')
        c.execute('INSERT INTO users VALUES(1,1,0,2)')
    def auth(value):
        if value not in ('Bearer one','Bearer two'):raise HTTPException(401)
        return {'id':1 if value=='Bearer one' else 2}
    calls=[]
    def generate(p,t):
        calls.append(t['id']);time.sleep(.15)
        raw=io.BytesIO();Image.new('RGB',(512,512),'green').save(raw,'PNG')
        from harness.tools.creative_canvas import save_asset
        return save_asset(p,raw.getvalue(),'image')
    monkeypatch.setattr(image_api,'create_image',generate)
    monkeypatch.setattr(image_api,'image_models',lambda:[{'id':'text','available':True,'mode':'text'},{'id':'edit','available':True,'mode':'edit'}])
    app=FastAPI();api.install(types.SimpleNamespace(app=app,require_session=auth,db=db))
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer one'
        p=c.post('/creative/api/projects',json={'message':'产品参考','aspect':'1:1'}).json();path='/creative/api/projects/'+p['id']
        body={'revision':0,'model':'text','prompt':'绿色产品','request_id':'a'*32,'approved_credits':1}
        assert c.post(path+'/images',json=body,headers={'Authorization':'Bearer two'}).status_code==404
        assert c.post(path+'/images',json={**body,'model':'edit'}).status_code==422
        assert c.post(path+'/images',json=body).status_code==200
        assert c.post(path+'/images',json=body).status_code==200
        assert c.put(path+'/model',json={'revision':1,'model':'kling-video-v3_0_omni'}).status_code==409
        for _ in range(60):
            result=c.get(path).json()
            if result['image_task']['state']!='running':break
            time.sleep(.02)
        assert result['image_task']['state']=='completed'
        assert len(result['canvas']['nodes'])==1 and len(calls)==1
        aid=result['image_task']['asset']
        assert c.get(path+'/canvas/assets/'+aid+'/preview',headers={'Authorization':'Bearer two'}).status_code==404
        with db() as conn:assert conn.execute('SELECT used FROM users').fetchone()[0]==1
        # Restart receipt: uncertainty is displayed, never silently submitted again.
        saved=store.load(p['id'],1);saved['image_task']['state']='running';store.save(saved,1)
        assert c.get(path).json()['image_task']['state']=='needs_review'
        assert c.post(path+'/images',json=body).status_code==200 and len(calls)==1
        assert all('绿色产品' not in str(e) for e in result['events'])

        # A failed project write cannot leave a paid call or a second debit on replay.
        real_save=store.save
        def fail_save(*args):raise OSError('simulated disk failure')
        monkeypatch.setattr(store,'save',fail_save)
        failed={**body,'revision':saved['revision'],'request_id':'b'*32}
        assert c.post(path+'/images',json=failed).status_code==503
        monkeypatch.setattr(store,'save',real_save)
        assert c.post(path+'/images',json=failed).status_code==409
        with db() as conn:
            assert conn.execute('SELECT used FROM users').fetchone()[0]==1
            assert conn.execute("SELECT state,credits FROM creative_image_requests WHERE request=?",('b'*32,)).fetchone()==('not_submitted',0)
        assert len(calls)==1
        with db() as conn:conn.execute('UPDATE users SET quota=1')
        assert c.post(path+'/images',json={**failed,'request_id':'c'*32}).status_code==402
        with db() as conn:
            assert conn.execute('SELECT count(*) FROM creative_image_requests WHERE request=?',('c'*32,)).fetchone()[0]==0
