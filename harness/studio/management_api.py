"""Private account operations. Operational data never enters agent trajectories."""
import json
import time
from typing import Literal
from fastapi import Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from harness.studio import store

class CreditRequest(BaseModel):
    amount: int = Field(ge=1, le=100000)
    reason: str = Field(min_length=2, max_length=500)

class Allocation(BaseModel):
    user_id: int
    amount: int = Field(ge=1, le=1000000)
    reason: str = Field(min_length=2, max_length=500)
    operation_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    request_id: int | None = None

class Decision(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


def schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS account_activity(user_id INTEGER PRIMARY KEY, last_seen INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS account_active_days(user_id INTEGER, day TEXT, PRIMARY KEY(user_id,day));
    CREATE TABLE IF NOT EXISTS credit_requests(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL, reviewed_at INTEGER, review_note TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS one_pending_credit_request ON credit_requests(user_id) WHERE state='pending';
    CREATE TABLE IF NOT EXISTS credit_allocations(id INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL,
        admin_id INTEGER NOT NULL, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, before_quota INTEGER NOT NULL,
        after_quota INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL, request_id INTEGER);
    ''')


def install(gateway):
    app = gateway.app
    # Lazy migration keeps application import free of database side effects.
    def connection():
        return gateway.db()

    def prepare():
        with connection() as c: schema(c)

    @app.get('/management', include_in_schema=False)
    def page():
        return FileResponse(store.ROOT/'tools/agent_studio/management.html', headers={'Cache-Control':'no-store'})

    @app.post('/credits/activity')
    def activity(authorization: str | None = Header(None)):
        user = gateway.require_session(authorization)
        prepare()
        now = int(time.time())
        with connection() as c:
            c.execute('INSERT INTO account_activity VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen', (user['id'], now))
            c.execute("INSERT OR IGNORE INTO account_active_days VALUES(?,date(?,'unixepoch','+8 hours'))", (user['id'], now))
        return {'ok': True}

    @app.get('/credits/requests')
    def requests(authorization: str | None = Header(None)):
        user = gateway.require_session(authorization); prepare()
        with connection() as c:
            rows = c.execute('SELECT id,amount,reason,state,created_at,reviewed_at,review_note FROM credit_requests WHERE user_id=? ORDER BY id DESC LIMIT 50', (user['id'],)).fetchall()
        return {'requests': [dict(r) for r in rows]}

    @app.post('/credits/requests')
    def request(body: CreditRequest, authorization: str | None = Header(None)):
        user = gateway.require_session(authorization); prepare()
        if user['quota'] < 0: raise HTTPException(409, '无限积分账户无需申请')
        with connection() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM credit_requests WHERE user_id=? AND state='pending'", (user['id'],)).fetchone():
                raise HTTPException(409, '已有待审核申请，请等待管理员处理')
            if c.execute('SELECT COUNT(*) FROM credit_requests WHERE user_id=? AND created_at>?',(user['id'],int(time.time())-86400)).fetchone()[0]>=5:
                raise HTTPException(429, '今日申请次数已达上限')
            cur = c.execute('INSERT INTO credit_requests(user_id,amount,reason,created_at) VALUES(?,?,?,?)', (user['id'], body.amount, body.reason.strip(), int(time.time())))
        return {'id': cur.lastrowid, 'state': 'pending'}

    @app.get('/management/api/overview')
    def overview(authorization: str | None = Header(None)):
        gateway.require_admin(authorization); prepare()
        with connection() as c:
            users = c.execute('SELECT COUNT(*),COALESCE(SUM(used),0) FROM users').fetchone()
            active = c.execute('SELECT COUNT(*) FROM account_activity WHERE last_seen>=?', (int(time.time())-86400,)).fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM credit_requests WHERE state='pending'").fetchone()[0]
            days = c.execute("SELECT day,COUNT(*) AS users FROM account_active_days WHERE day>=date('now','+8 hours','-29 days') GROUP BY day ORDER BY day DESC").fetchall()
        with store.connection() as c: projects = c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        return {'users':users[0], 'used':users[1], 'active_24h':active, 'pending':pending, 'projects':projects, 'daily':[dict(r) for r in days]}

    @app.get('/management/api/users')
    def users(q: str = Query('', max_length=320), offset: int = Query(0,ge=0), authorization: str | None = Header(None)):
        gateway.require_admin(authorization); prepare()
        with connection() as c:
            rows = c.execute('SELECT u.id,u.email,u.role,u.verified,u.quota,u.used,u.created_at,a.last_seen FROM users u LEFT JOIN account_activity a ON a.user_id=u.id WHERE instr(lower(u.email),lower(?))>0 ORDER BY u.id DESC LIMIT 50 OFFSET ?', (q,offset)).fetchall()
        return {'users':[dict(r) for r in rows]}

    @app.get('/management/api/requests')
    def pending(state: Literal['pending','approved','rejected'] = 'pending', authorization: str | None = Header(None)):
        gateway.require_admin(authorization); prepare()
        with connection() as c:
            rows = c.execute('SELECT r.*,u.email FROM credit_requests r JOIN users u ON u.id=r.user_id WHERE r.state=? ORDER BY r.id DESC LIMIT 100',(state,)).fetchall()
        return {'requests':[dict(r) for r in rows]}

    @app.post('/management/api/allocate')
    def allocate(body: Allocation, authorization: str | None = Header(None)):
        admin = gateway.require_admin(authorization); prepare()
        with connection() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM credit_allocations WHERE operation_id=?',(body.operation_id,)).fetchone()
            if old:
                if any(old[k]!=v for k,v in {'admin_id':admin['id'],'user_id':body.user_id,'amount':body.amount,'reason':body.reason.strip(),'request_id':body.request_id}.items()): raise HTTPException(409,'操作编号已用于其他分配')
                return {'ok':True,'allocation_id':old['id'],'replayed':True}
            user = c.execute('SELECT * FROM users WHERE id=?',(body.user_id,)).fetchone()
            if not user: raise HTTPException(404,'用户不存在')
            if user['quota'] < 0: raise HTTPException(409,'此账户已是无限积分')
            after = user['quota']+body.amount
            if after > 2147483647: raise HTTPException(422,'额度超出范围')
            if body.request_id is not None:
                row = c.execute("SELECT * FROM credit_requests WHERE id=? AND user_id=? AND state='pending'",(body.request_id,body.user_id)).fetchone()
                if not row: raise HTTPException(409,'申请已处理或不属于该账户')
                c.execute("UPDATE credit_requests SET state='approved',reviewed_at=?,review_note=? WHERE id=?",(int(time.time()),body.reason.strip(),body.request_id))
            c.execute('UPDATE users SET quota=? WHERE id=?',(after,body.user_id))
            cur=c.execute('INSERT INTO credit_allocations(operation_id,admin_id,user_id,amount,before_quota,after_quota,reason,created_at,request_id) VALUES(?,?,?,?,?,?,?,?,?)',(body.operation_id,admin['id'],body.user_id,body.amount,user['quota'],after,body.reason.strip(),int(time.time()),body.request_id))
        return {'ok':True,'allocation_id':cur.lastrowid}

    @app.post('/management/api/requests/{rid}/reject')
    def reject(rid: int, body: Decision, authorization: str | None = Header(None)):
        gateway.require_admin(authorization); prepare()
        with connection() as c:
            cur=c.execute("UPDATE credit_requests SET state='rejected',reviewed_at=?,review_note=? WHERE id=? AND state='pending'",(int(time.time()),body.reason.strip(),rid))
            if cur.rowcount!=1: raise HTTPException(409,'申请不存在或已处理')
        return {'ok':True}

    @app.get('/management/api/users/{uid}')
    def details(uid: int, authorization: str | None = Header(None)):
        gateway.require_admin(authorization); prepare()
        with connection() as c:
            user = c.execute('SELECT id,email,quota,used FROM users WHERE id=?',(uid,)).fetchone()
            if not user: raise HTTPException(404,'用户不存在')
            events=c.execute('SELECT delta,reason,created_at,job_id FROM usage_events WHERE user_id=? ORDER BY id DESC LIMIT 100',(uid,)).fetchall()
            allocations=c.execute('SELECT amount,before_quota,after_quota,reason,created_at FROM credit_allocations WHERE user_id=? ORDER BY id DESC LIMIT 100',(uid,)).fetchall()
            image_table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='creative_image_requests'").fetchone()
            images=c.execute('SELECT project,state,credits FROM creative_image_requests WHERE owner=? LIMIT 500',(uid,)).fetchall() if image_table else []
        # Expose a bounded metadata projection, never prompts, reference media or provider payloads.
        with store.connection() as c:
            rows=c.execute('SELECT id,data FROM projects WHERE owner=? ORDER BY json_extract(data,\'$.updated_at\') DESC LIMIT 100',(uid,)).fetchall()
        projects=[]
        for pid,raw in rows:
            p=json.loads(raw); projects.append({'id':pid,'state':p.get('state'),'mode':p.get('creation_mode','agent'),'updated_at':p.get('updated_at'),'model':p.get('model')})
        return {'user':dict(user),'events':[dict(r) for r in events],'allocations':[dict(r) for r in allocations],'images':[dict(r) for r in images],'projects':projects}
