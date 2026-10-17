"""Admin review of explicitly opted-in current films, separate from owner approval."""
import asyncio
import json
import time
from fastapi import Header,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,StrictBool,StrictInt
from typing import Literal
from harness.studio import store
from harness.learning import governance,review,curation,edit_review


class Rating(BaseModel):
    score:StrictInt=Field(ge=0,le=5)
    evidence:str=Field(min_length=5,max_length=500)


class Checks(BaseModel):
    full_video_watched:StrictBool
    audio_listened:StrictBool
    product_facts_checked:StrictBool


class Assessment(BaseModel):
    revision:int
    artifact_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    decision:Literal['passed','needs_changes','rejected']
    ratings:dict[str,Rating]
    checks:Checks


class EditAssessment(BaseModel):
    export_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    revision: int
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['passed','needs_changes','rejected']
    ratings: dict[str,Rating]
    checks: Checks


def install(gateway):
    app=gateway.app
    def admin(auth):
        if not hasattr(gateway,'require_admin'):raise HTTPException(403,'需要管理员审阅权限')
        return gateway.require_admin(auth)['id']
    def project(pid,actor):
        with store.connection() as c:row=c.execute('SELECT owner,data FROM projects WHERE id=?',(pid,)).fetchone()
        if not row:raise HTTPException(404,'项目不存在')
        if row[0]==actor:raise HTTPException(403,'请由另一位审阅者独立审阅')
        return json.loads(row[1]),row[0]
    async def approved(p,owner):
        try:artifact=await asyncio.to_thread(governance.current_artifact,p)
        except ValueError:raise HTTPException(409,'当前成片文件不可读取')
        if not artifact or not governance.status(p,owner,artifact)['training']:raise HTTPException(403,'当前成片未授权训练审阅')
        return artifact

    @app.get('/creative/review',include_in_schema=False)
    def page():return FileResponse(store.ROOT/'tools/agent_studio/review.html',headers={'Cache-Control':'no-store'})

    @app.get('/creative/edit-review', include_in_schema=False)
    def edit_review_page():
        return FileResponse(store.ROOT/'tools/agent_studio/edit-review.html', headers={'Cache-Control':'no-store'})

    @app.get('/creative/api/admin/learning/queue')
    def queue(cursor:int=0,authorization:str|None=Header(None)):
        actor=admin(authorization)
        if cursor<0:raise HTTPException(422,'分页位置无效')
        c=governance.connection()
        try:
            rows=c.execute('''SELECT seq,project,owner,revision,data FROM learning_controls x
                WHERE kind='consent' AND (?=0 OR seq<?) AND seq=(SELECT MAX(seq) FROM learning_controls y
                WHERE y.project=x.project AND y.owner=x.owner AND y.revision=x.revision AND y.kind='consent')
                ORDER BY seq DESC LIMIT 100''',(cursor,cursor)).fetchall()
        finally:c.close()
        items=[]
        for seq,pid,uid,revision,data in rows:
            receipt=json.loads(data)
            if uid==actor or receipt.get('training') is not True:continue
            try:p=store.load(pid,uid)
            except HTTPException:continue
            if p['revision']!=revision or p.get('state')!='completed':continue
            # Queue membership is an index, not proof; detail rehashes the actual file.
            if not governance.status(p,uid,receipt.get('artifact_sha256'))['training']:continue
            items.append({'project':pid,'revision':revision,'title':p.get('brief',{}).get('product','广告作品'),
                'artifact_sha256':receipt.get('artifact_sha256'),'digest_status':'needs_verification'})
        return {'items':items,'next_cursor':rows[-1][0] if len(rows)==100 else None}

    @app.get('/creative/api/admin/learning/projects/{pid}')
    async def details(pid:str,authorization:str|None=Header(None)):
        actor=admin(authorization)
        async with store.lock(pid):
            p,uid=project(pid,actor);artifact=await approved(p,uid)
            try:assessment=review.latest(p,uid,artifact)
            except ValueError:raise HTTPException(409,'审阅记录完整性核对失败')
            return {'project':pid,'revision':p['revision'],'artifact_sha256':artifact,
                'brief':p.get('brief',{}),'shots':p.get('shots',[]),'decisions':p.get('decisions',[]),
                'assumptions':p.get('assumptions',[]),'qa':{k:p.get('qa',{}).get(k) for k in ('technical','audio','duration','width','height','human')},
                'rubric':list(review.RUBRIC),'assessment':assessment,'curation':curation.latest(p,uid,artifact) if governance.status(p,uid,artifact)['training'] else None,'training_eligible':False}

    @app.get('/creative/api/admin/learning/projects/{pid}/media')
    async def media(pid:str,revision:int,digest:str,authorization:str|None=Header(None)):
        actor=admin(authorization)
        async with store.lock(pid):
            p,uid=project(pid,actor);artifact=await approved(p,uid)
            if p['revision']!=revision or digest!=artifact:raise HTTPException(409,'成片版本已变化')
            return FileResponse((store.DATA/p['artifact']).resolve(),media_type='video/mp4',headers={'Cache-Control':'no-store'})

    @app.post('/creative/api/admin/learning/projects/{pid}/assessment')
    async def assessment(pid:str,body:Assessment,authorization:str|None=Header(None)):
        actor=admin(authorization)
        async with store.lock(pid):
            p,uid=project(pid,actor)
            if p['revision']!=body.revision:raise HTTPException(409,'作品版本已变化')
            try:result=await asyncio.to_thread(review.record,p,uid,actor,body.artifact_sha256,body.decision,
                {k:v.model_dump() for k,v in body.ratings.items()},body.checks.model_dump())
            except ValueError as e:raise HTTPException(409,str(e))
            store.event(p,'evaluator','independent_review_recorded')
            return result

    def edit_request(p, export_id):
        request = p.get('edit_review_requests', {}).get(export_id)
        if not request:
            raise HTTPException(404, '找不到待审阅的剪辑版本')
        export = edit_review.export_record(p, export_id)
        if not export:
            raise HTTPException(404, '找不到剪辑导出记录')
        try:
            _path, artifact = edit_review.export_path(p, export)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if request.get('artifact_sha256') != artifact:
            raise HTTPException(409, '剪辑导出版本已变化，请由创作者重新申请审阅')
        return request, export, artifact

    @app.get('/creative/api/admin/learning/edit/queue')
    def edit_queue(authorization: str | None = Header(None)):
        actor = admin(authorization)
        with store.connection() as c:
            rows = c.execute('SELECT owner,data FROM projects ORDER BY rowid DESC').fetchall()
        items = []
        for owner_id, raw in rows:
            if owner_id == actor:
                continue
            try:
                p = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            for export_id, request in p.get('edit_review_requests', {}).items():
                if request.get('status') not in ('pending_independent_review', 'needs_changes'):
                    continue
                export = edit_review.export_record(p, export_id)
                try:
                    _path, artifact = edit_review.export_path(p, export)
                except (ValueError, TypeError, KeyError):
                    continue
                if request.get('artifact_sha256') != artifact:
                    continue
                items.append({'project': p['id'], 'export_id': export_id,
                              'title': p.get('brief', {}).get('product', '剪辑作品'),
                              'revision': export.get('revision'),
                              'artifact_sha256': artifact, 'status': request.get('status'),
                              'training_eligible': False})
        return {'items': items}

    @app.get('/creative/api/admin/learning/edit/projects/{pid}/exports/{export_id}')
    async def edit_details(pid: str, export_id: str, authorization: str | None = Header(None)):
        actor = admin(authorization)
        async with store.lock(pid):
            p, owner_id = project(pid, actor)
            request, export, artifact = edit_request(p, export_id)
            try:
                assessment = edit_review.latest(p, owner_id, export_id, artifact)
            except ValueError:
                raise HTTPException(409, '剪辑独立审阅记录完整性核对失败')
            return {
                'project': pid, 'export_id': export_id, 'revision': export.get('revision'),
                'artifact_sha256': artifact, 'title': p.get('brief', {}).get('product', '剪辑作品'),
                'brief': {'product': p.get('brief', {}).get('product', '')},
                'qa': {k: export.get('qa', {}).get(k) for k in ('technical', 'audio', 'duration', 'width', 'height')},
                'content_tasks': request.get('content_tasks', []),
                'rubric': list(review.RUBRIC), 'request': request, 'assessment': assessment,
                'training_eligible': False,
            }

    @app.get('/creative/api/admin/learning/edit/projects/{pid}/exports/{export_id}/media')
    async def edit_media(pid: str, export_id: str, revision: int, digest: str,
                         authorization: str | None = Header(None)):
        actor = admin(authorization)
        async with store.lock(pid):
            p, _owner_id = project(pid, actor)
            _request, export, artifact = edit_request(p, export_id)
            if export.get('revision') != revision or artifact != digest:
                raise HTTPException(409, '剪辑版本已变化，请重新选择审阅项')
            path, _ = edit_review.export_path(p, export)
            return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'no-store'})

    @app.post('/creative/api/admin/learning/edit/projects/{pid}/exports/{export_id}/assessment')
    async def edit_assessment(pid: str, export_id: str, body: EditAssessment,
                              authorization: str | None = Header(None)):
        actor = admin(authorization)
        if body.export_id != export_id:
            raise HTTPException(409, '审阅目标不一致')
        async with store.lock(pid):
            p, owner_id = project(pid, actor)
            request, export, artifact = edit_request(p, export_id)
            if export.get('revision') != body.revision or artifact != body.artifact_sha256:
                raise HTTPException(409, '剪辑版本已变化，请重新审阅')
            try:
                result = await asyncio.to_thread(edit_review.record, p, owner_id, actor, export,
                    body.artifact_sha256, body.decision,
                    {k: v.model_dump() for k, v in body.ratings.items()}, body.checks.model_dump())
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            request = dict(request, status={
                'passed': 'independent_passed',
                'needs_changes': 'needs_changes',
                'rejected': 'rejected',
            }[body.decision], assessment_receipt_id=result['receipt_id'],
                           reviewed_at=time.time(), training_eligible=False)
            p.setdefault('edit_review_requests', {})[export_id] = request
            store.save(p, owner_id); store.event(p, 'evaluator', 'edit_independent_review_recorded')
            return result
