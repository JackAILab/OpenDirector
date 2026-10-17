"""Admin-only privacy/rights/sanitization curation, separate from quality review."""
import asyncio
from fastapi import Header,HTTPException
from pydantic import BaseModel,Field,StrictBool
from harness.studio import store
from harness.learning import governance,curation


class Curation(BaseModel):
    revision:int
    artifact_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    privacy_review:StrictBool
    rights_review:StrictBool
    sanitized_context_review:StrictBool
    note:str=Field(min_length=10,max_length=1000)


def install(gateway):
    app=gateway.app
    def admin(auth):
        if not hasattr(gateway,'require_admin'):raise HTTPException(403,'需要管理员策展权限')
        return gateway.require_admin(auth)['id']
    def project(pid,actor):
        with store.connection() as c:row=c.execute('SELECT owner,data FROM projects WHERE id=?',(pid,)).fetchone()
        if not row:raise HTTPException(404,'项目不存在')
        if row[0]==actor:raise HTTPException(403,'请由另一位策展人独立核对')
        return __import__('json').loads(row[1]),row[0]
    async def digest(p,owner):
        try:actual=await asyncio.to_thread(governance.current_artifact,p)
        except ValueError:raise HTTPException(409,'成片文件不可读取')
        if not actual or not governance.status(p,owner,actual)['training']:raise HTTPException(403,'当前成片未授权训练策展')
        return actual

    @app.get('/creative/api/admin/learning/projects/{pid}/curation')
    async def get(pid:str,authorization:str|None=Header(None)):
        actor=admin(authorization)
        async with store.lock(pid):
            p,owner=project(pid,actor);actual=await digest(p,owner)
            try:latest=curation.latest(p,owner,actual)
            except ValueError:raise HTTPException(409,'策展记录完整性核对失败')
            return {'project':pid,'revision':p['revision'],'artifact_sha256':actual,'gates':list(curation.GATES),
                'curation':latest,'training_eligible':False}

    @app.post('/creative/api/admin/learning/projects/{pid}/curation')
    async def post(pid:str,body:Curation,authorization:str|None=Header(None)):
        actor=admin(authorization)
        async with store.lock(pid):
            p,owner=project(pid,actor)
            if p['revision']!=body.revision:raise HTTPException(409,'作品版本已变化')
            try:result=await asyncio.to_thread(curation.record,p,owner,actor,body.artifact_sha256,
                {k:getattr(body,k) for k in curation.GATES},body.note)
            except ValueError as e:raise HTTPException(409,str(e))
            store.event(p,'evaluator','curation_recorded')
            return result
