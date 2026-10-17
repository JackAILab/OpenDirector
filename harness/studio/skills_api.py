"""Private Skill authoring shared by the home UI and bounded agent clients."""
from fastapi import Header,HTTPException,Query,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from harness.studio import store,skill_store

class NewSkill(BaseModel):
    content:dict
    parent_id:str|None=Field(default=None,max_length=80)
    parent_version:int|None=Field(default=None,ge=1,le=100)

class Revision(BaseModel):
    base_version:int=Field(ge=1,le=100)
    content:dict

class Favorite(BaseModel):
    enabled:bool


def install(gateway):
    app=gateway.app
    def owner(auth): return gateway.require_session(auth)['id']
    def skill(sid,uid,version=None):
        from harness.studio.templates import find_skill
        return find_skill(sid,uid,version)
    def call(fn,*args):
        try:return fn(*args)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc

    @app.get('/creative/skills.{ext}',include_in_schema=False)
    def asset(ext:str):
        if ext not in ('js','css'):raise HTTPException(404)
        return FileResponse(store.ROOT/f'tools/agent_studio/skills.{ext}',headers={'Cache-Control':'no-store'})

    @app.get('/creative/api/skills/mine')
    def mine(authorization:str|None=Header(None)):return skill_store.mine(owner(authorization))

    @app.post('/creative/api/skills')
    def create(body:NewSkill,authorization:str|None=Header(None)):
        uid=owner(authorization);parent=skill(body.parent_id,uid,body.parent_version) if body.parent_id else None
        return call(skill_store.create,uid,body.content,parent)

    @app.get('/creative/api/skills/{sid}/versions')
    def versions(sid:str,authorization:str|None=Header(None)):
        return {'versions':skill_store.history(sid,owner(authorization))}

    @app.get('/creative/api/skills/{sid}')
    def read(sid:str,request:Request,version:int|None=Query(default=None,ge=1,le=100),authorization:str|None=Header(None)):
        if sid.startswith('reference-'):
            gateway.require_site_access(request)
            return skill(sid,None,version)
        return skill(sid,owner(authorization),version)

    @app.put('/creative/api/skills/{sid}')
    def update(sid:str,body:Revision,authorization:str|None=Header(None)):
        return call(skill_store.update,sid,owner(authorization),body.base_version,body.content)

    @app.put('/creative/api/skills/{sid}/favorite')
    def favorite(sid:str,body:Favorite,authorization:str|None=Header(None)):
        uid=owner(authorization);skill(sid,uid)
        return skill_store.favorite(sid,uid,body.enabled)
