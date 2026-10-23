"""Deliver owned Agent media from a durable outbox, without generation calls."""
import asyncio
import contextlib
import fcntl
import json
import time
from fastapi import HTTPException
from harness.studio import store
from harness.tools.creative_workspace_result import import_assets


def _record(owner, pid, aid, state, code='', delay=0):
    with store.connection() as c:
        c.execute('UPDATE workspace_deliveries SET state=?,code=?,next_attempt=?,updated_at=? WHERE owner=? AND project=? AND asset=?',
                  (state,code,time.time()+delay,time.time(),owner,pid,aid))


async def drain(limit=16):
    """One bounded pass; the same saved assets are reused after interruptions."""
    directory=store.DATA/'execution-locks';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (directory/'workspace-delivery.lock').open('a') as lease:
        try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        delivered=0
        try:
            with store.connection() as c:
                rows=c.execute("SELECT owner,project,parent,asset FROM workspace_deliveries WHERE state='pending' AND next_attempt<=? ORDER BY updated_at LIMIT ?",
                               (time.time(),max(1,min(limit,32)))).fetchall()
            for owner,pid,parent_id,aid in rows:
                async with store.lock(parent_id):
                    try:
                        parent=store.load(parent_id,owner);child=store.load(pid,owner)
                        if parent_id in store.RUNNING or parent.get('state') in ('running','rendering','planning') or parent.get('image_task',{}).get('state')=='running':
                            _record(owner,pid,aid,'pending','workspace_busy',15);continue
                        before=json.dumps(parent,ensure_ascii=False)
                        changed=await asyncio.to_thread(import_assets,parent,child,[aid])
                        if changed:parent['revision']+=1;parent['updated_at']=time.time()
                        with store.connection() as c:
                            c.execute('BEGIN IMMEDIATE')
                            # Another process can save while media is copied. A
                            # revision/data compare prevents replacing that edit.
                            current=c.execute('SELECT data FROM projects WHERE id=? AND owner=?',(parent_id,owner)).fetchone()
                            if not current or current[0]!=before:
                                c.rollback();_record(owner,pid,aid,'pending','workspace_changed',5);continue
                            if changed:
                                c.execute('UPDATE projects SET data=? WHERE id=? AND owner=?',
                                          (json.dumps(parent,ensure_ascii=False),parent_id,owner))
                                c.execute('INSERT INTO events(project,time,stage,code,shot) VALUES(?,?,?,?,?)',
                                          (parent_id,time.time(),'tool','agent_result_delivered',None))
                            c.execute("UPDATE workspace_deliveries SET state='delivered',code='',updated_at=? WHERE owner=? AND project=? AND asset=?",
                                      (time.time(),owner,pid,aid))
                        delivered+=1
                    except HTTPException:
                        _record(owner,pid,aid,'needs_review','workspace_missing')
                    except ValueError:
                        _record(owner,pid,aid,'needs_review','workspace_inputs_or_capacity')
                    except OSError:
                        _record(owner,pid,aid,'pending','storage_unavailable',60)
            return delivered
        finally:fcntl.flock(lease,fcntl.LOCK_UN)


def install(app):
    async def work():
        while True:
            try:await drain()
            except Exception:
                # Outbox remains durable; a service/storage outage must not
                # turn a completed generation into another paid attempt.
                pass
            await asyncio.sleep(5)
    previous=app.router.lifespan_context
    @contextlib.asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            task=asyncio.create_task(work())
            app.state.workspace_delivery_task=task
            try:yield state
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):await task
    app.router.lifespan_context=lifespan
