from contextlib import contextmanager
import json
import sqlite3
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from harness.studio import management_api, store

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'projects')
    @contextmanager
    def db():
        c=sqlite3.connect(tmp_path/'accounts.db');c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally:c.close()
    with db() as c:
        c.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,role TEXT,verified INTEGER,quota INTEGER,used INTEGER,created_at INTEGER);
        CREATE TABLE usage_events(id INTEGER PRIMARY KEY,user_id INTEGER,delta INTEGER,reason TEXT,created_at INTEGER,job_id TEXT);
        INSERT INTO users VALUES(1,'admin@example.test','admin',1,-1,4,1),(2,'user@example.test','user',1,0,0,1),(3,'other@example.test','user',1,0,0,1);
        ''')
    def session(auth):
        uid={'Bearer admin':1,'Bearer user':2,'Bearer other':3}.get(auth)
        if not uid:raise HTTPException(401)
        with db() as c:return c.execute('select * from users where id=?',(uid,)).fetchone()
    def admin(auth):
        u=session(auth)
        if u['role']!='admin':raise HTTPException(403)
        return u
    app=FastAPI();management_api.install(SimpleNamespace(app=app,db=db,require_session=session,require_admin=admin))
    with TestClient(app) as client:yield client,db

def test_private_endpoints_and_own_requests(setup):
    c,db=setup
    for path in ['/management/api/overview','/management/api/users','/management/api/requests','/management/api/users/2']:
        assert c.get(path).status_code==401
        assert c.get(path,headers={'Authorization':'Bearer user'}).status_code==403
    assert c.post('/credits/requests',headers={'Authorization':'Bearer user'},json={'amount':30,'reason':'test creation'}).status_code==200
    assert c.get('/credits/requests',headers={'Authorization':'Bearer other'}).json()=={'requests':[]}
    assert c.post('/credits/requests',headers={'Authorization':'Bearer user'},json={'amount':30,'reason':'test creation'}).status_code==409

def test_allocation_is_atomic_and_replay_safe(setup):
    c,db=setup;c.headers['Authorization']='Bearer user'
    rid=c.post('/credits/requests',json={'amount':30,'reason':'test creation'}).json()['id']
    body={'user_id':2,'amount':30,'reason':'approved','operation_id':'a'*32,'request_id':rid}
    assert c.post('/management/api/allocate',json=body).status_code==403
    c.headers['Authorization']='Bearer admin'
    assert c.post('/management/api/allocate',json=body).status_code==200
    assert c.post('/management/api/allocate',json=body).json()['replayed']
    assert c.post('/management/api/allocate',json={**body,'amount':31}).status_code==409
    assert c.post('/management/api/allocate',json={**body,'operation_id':'b'*32}).status_code==409
    with db() as dbh:
        assert dbh.execute('select quota from users where id=2').fetchone()[0]==30
        assert dbh.execute('select count(*) from credit_allocations').fetchone()[0]==1
    assert c.post('/management/api/allocate',json={**body,'user_id':1,'request_id':None,'operation_id':'c'*32}).status_code==409

def test_activity_and_project_projection(setup):
    c,db=setup
    store.save({'id':'fixture','state':'draft','prompt':'private prompt','reference':{'url':'private url'},'creation_mode':'image'},2)
    assert c.post('/credits/activity',headers={'Authorization':'Bearer user'}).status_code==200
    c.headers['Authorization']='Bearer admin'
    overview=c.get('/management/api/overview').json();assert overview['active_24h']==1 and overview['projects']==1
    d=c.get('/management/api/users/2').json()
    assert d['projects'][0]['id']=='fixture'
    assert 'private' not in json.dumps(d)
    assert 'password' not in c.get('/management/api/users').text

def test_reject_does_not_grant_and_cannot_be_reapproved(setup):
    c,db=setup;c.headers['Authorization']='Bearer user'
    rid=c.post('/credits/requests',json={'amount':30,'reason':'test'}).json()['id']
    c.headers['Authorization']='Bearer admin'
    assert c.post(f'/management/api/requests/{rid}/reject',json={'reason':'needs details'}).status_code==200
    assert c.post('/management/api/allocate',json={'user_id':2,'amount':30,'reason':'test','operation_id':'c'*32,'request_id':rid}).status_code==409
    with db() as x:assert x.execute('select quota from users where id=2').fetchone()[0]==0
