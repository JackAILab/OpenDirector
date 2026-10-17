"""Account-scoped optional learning controls; never authorize a paid action."""
import asyncio
from fastapi import Header,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,StrictBool
from harness.learning import governance, feedback
from harness.studio import store


class SeriesCreate(BaseModel):
    label:str=Field(min_length=1,max_length=80)


class Family(BaseModel):
    revision:int
    series_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{24}$')


class Consent(BaseModel):
    revision:int
    artifact_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    policy:str=Field(max_length=80)
    policy_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    training:StrictBool
    public_dataset:StrictBool


class PlanFeedback(BaseModel):
    revision: int
    decision: str
    rating: int = Field(ge=1, le=5)
    strategy_indices: list[int] = Field(default_factory=list, max_length=3)
    changed_dimensions: list[str] = Field(default_factory=list, max_length=8)
    note: str = Field(default='', max_length=500)


def install(gateway):
    app=gateway.app
    def owner(auth):return gateway.require_session(auth)['id']

    @app.get('/creative/api/learning/mechanisms')
    def mechanisms(authorization:str|None=Header(None)):
        """Return generic reference mechanisms without exposing source media."""
        owner(authorization)
        from harness.library.mechanism_report import build_mechanism_report
        from harness.library.playbook import compact
        return build_mechanism_report(compact().get('evidence_summary', {}))

    @app.get('/creative/learning.js',include_in_schema=False)
    def script():return FileResponse(store.ROOT/'tools/agent_studio/learning.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/creative/api/learning/series')
    def series(authorization:str|None=Header(None)):return governance.list_series(owner(authorization))

    @app.post('/creative/api/learning/series')
    def new_series(body:SeriesCreate,authorization:str|None=Header(None)):
        uid=owner(authorization)
        try:return governance.create_series(uid,body.label)
        except ValueError as e:raise HTTPException(422,str(e))

    async def view(p,uid):
        try:artifact=await asyncio.to_thread(governance.current_artifact,p)
        except ValueError as e:raise HTTPException(409,str(e))
        return governance.status(p,uid,artifact)

    @app.get('/creative/api/projects/{pid}/learning')
    async def learning(pid:str,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):return await view(store.load(pid,uid),uid)

    @app.get('/creative/api/projects/{pid}/learning/feedback')
    async def feedback_history(pid:str,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid)
            try:
                return feedback.summary(p,uid)
            except ValueError as e:
                raise HTTPException(409,str(e))

    @app.post('/creative/api/projects/{pid}/learning/feedback')
    async def feedback_create(pid:str,body:PlanFeedback,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid)
            if p['revision']!=body.revision:
                raise HTTPException(409,'方案已更新，请重新查看后反馈')
            try:
                result=feedback.record(p,uid,body.decision,body.rating,
                    body.strategy_indices,body.changed_dimensions,body.note)
            except ValueError as e:
                raise HTTPException(422,str(e))
            store.event(p,'learning','plan_feedback_recorded')
            return result

    @app.put('/creative/api/projects/{pid}/learning/family')
    async def family(pid:str,body:Family,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid)
            if p['revision']!=body.revision:raise HTTPException(409,'作品已更新，请重新查看')
            try:governance.set_family(p,uid,body.series_id)
            except KeyError:raise HTTPException(404,'系列不存在')
            store.event(p,'learning','family_updated')
            return await view(p,uid)

    @app.post('/creative/api/projects/{pid}/learning/consent')
    async def consent(pid:str,body:Consent,authorization:str|None=Header(None)):
        uid=owner(authorization)
        async with store.lock(pid):
            p=store.load(pid,uid)
            if p['revision']!=body.revision:raise HTTPException(409,'作品已更新，请重新查看')
            try:await asyncio.to_thread(governance.set_consent,p,uid,body.artifact_sha256,body.training,body.public_dataset,body.policy,body.policy_sha256)
            except ValueError as e:raise HTTPException(409,str(e))
            store.event(p,'learning','consent_updated')
            return await view(p,uid)
