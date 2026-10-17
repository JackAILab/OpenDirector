"""Curated template projection: never expose private projects or provider records."""
import json
import re
import secrets
import fcntl
import hashlib
import shutil
from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from harness.studio import store
from harness.models.video_catalog import model_spec


def find_skill(skill_id,owner=None,version=None):
    if skill_id.startswith('custom-'):
        from harness.studio.skill_store import get
        if owner is None: raise HTTPException(404,'找不到这个 Skill')
        return get(skill_id,owner,version)
    if skill_id.startswith('reference-'):
        from harness.studio.reference_skills import find
        result=find(skill_id)
    else:
        result=next((s for s in skills() if s['id']==skill_id),None)
    if not result: raise HTTPException(422, '请选择已发布的创作 Skill')
    if version is not None and result['version']!=version: raise HTTPException(409,'公开 Skill 已更新，请重新选择版本')
    return result


def skills():
    from harness.core.creative_skills import builtin_skills, from_template
    from harness.studio.reference_skills import summaries
    return builtin_skills()+[from_template(t) for t in catalog()['templates']]+summaries()


class UseTemplate(BaseModel):
    product: str = Field(min_length=1,max_length=200)
    requirements: str = Field(default='',max_length=3000)
    model: str = Field(default='kling-video-v3_0', min_length=1, max_length=100)
    aspect: Literal['16:9','9:16','1:1'] | None = None
    approval_mode: Literal['manual','auto'] = 'manual'


def catalog():
    path=store.DATA/'templates'/'catalog.json'
    return json.loads(path.read_text()) if path.exists() else {'templates':[]}


def publish_template(case, project, source, poster, audio, review_note):
    """Serialize curated exports; retain prior publications and completed files."""
    from pathlib import Path
    tid=case['id']
    if not re.fullmatch(r'[a-z0-9-]{1,60}',tid): raise ValueError('Invalid template id')
    sources=[Path(source).resolve(),Path(poster).resolve()]
    if any(not p.is_file() or not p.is_relative_to(store.DATA.resolve()) for p in sources):
        raise ValueError('Template sources must be local reviewed artifacts')
    if project.get('qa',{}).get('technical')!='passed': raise ValueError('Technical QA required')
    directory=store.DATA/'templates';directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.publish.lock').open('a') as lock_file:
        fcntl.flock(lock_file,fcntl.LOCK_EX)
        current=catalog()
        if any(t['id']==tid for t in current['templates']):return False
        target=directory/tid;target.mkdir(exist_ok=True)
        for source,name in zip(sources,('final.mp4','poster.jpg')):
            final=target/name
            if final.exists():
                if hashlib.sha256(final.read_bytes()).digest()!=hashlib.sha256(source.read_bytes()).digest():
                    raise ValueError('Existing unpublished media differs; explicit reconciliation required')
            else:
                temporary=target/(name+'.'+secrets.token_hex(6)+'.part')
                shutil.copyfile(source,temporary);temporary.replace(final)
        item={k:case[k] for k in ('id','title','category','product','scene','provider','model','aspect','duration')}
        item.update(model_label=model_spec(project['provider'],project.get('model'))['label'],audio=audio,
                    storyboard=[{k:s.get(k,'') for k in ('title','caption','rationale')} for s in project['shots']],
                    review_note=review_note,training_eligible=False)
        current['templates'].append(item)
        temporary=directory/('catalog.'+secrets.token_hex(6)+'.tmp')
        temporary.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
        temporary.replace(directory/'catalog.json')
        return True


def find(tid):
    if not re.fullmatch(r'[a-z0-9-]{1,60}',tid): raise HTTPException(404,'找不到模板')
    item=next((t for t in catalog()['templates'] if t['id']==tid),None)
    if not item: raise HTTPException(404,'模板尚未发布')
    return item


def install(gateway):
    app=gateway.app
    from harness.studio.skills_api import install as install_skills
    install_skills(gateway)

    @app.get('/creative/discover',include_in_schema=False)
    def discover():
        return FileResponse(store.ROOT/'tools/agent_studio/discover.html',headers={'Cache-Control':'no-store'})

    @app.get('/creative/api/templates')
    def templates(request: Request):
        gateway.require_site_access(request)
        return catalog()

    @app.get('/creative/api/skills')
    def skill_catalog(request: Request,authorization: str|None=Header(None)):
        gateway.require_site_access(request)
        personal=[]
        if authorization:
            from harness.studio.skill_store import mine
            personal=mine(gateway.require_session(authorization)['id'])['skills']
        return {'skills':skills()+personal}

    @app.get('/creative/api/templates/{tid}/{asset}')
    def template_media(tid: str,asset: str,request: Request):
        gateway.require_site_access(request);find(tid)
        files={'poster':'poster.jpg','video':'final.mp4'}
        if asset not in files: raise HTTPException(404)
        path=store.DATA/'templates'/tid/files[asset]
        if not path.is_file(): raise HTTPException(404,'模板媒体尚未就绪')
        return FileResponse(path,media_type='image/jpeg' if asset=='poster' else 'video/mp4',headers={'Cache-Control':'private, no-store'})

    @app.post('/creative/api/templates/{tid}/use')
    def use(tid: str,body: UseTemplate,authorization: str|None=Header(None)):
        uid=gateway.require_session(authorization)['id'];t=find(tid)
        try: spec=model_spec('kling',body.model)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        if not spec.get('single_film') or not spec.get('audio'):
            raise HTTPException(422,'请选择支持15秒有声整片的视频模型')
        context=f"参考模板《{t['title']}》的结构，为产品“{body.product}”创作广告。用户补充：{body.requirements}。模板仅供风格和节奏参考；不要把原商品属性移植到新商品，缺少事实时先追问。"
        notes='模板结构：'+json.dumps(t['storyboard'],ensure_ascii=False)
        p={'id':secrets.token_hex(12),'state':'intake','revision':0,'messages':[{'role':'user','content':context+f" 新项目按15秒有声整片重新规划，所选模型为{spec['label']}；制作前确认模型及预算。"}],
           'duration':15,'generation_mode':'single_native','aspect':body.aspect or t['aspect'],'provider':spec['provider'],'model':spec['id'],
           'shots':[],'questions':[],'assumptions':[],'decisions':[],'brief':{},'training_eligible':False,
           'skill_id':'template-'+tid,'skill_title':t['title'],'skill':find_skill('template-'+tid),
           'approval_mode':body.approval_mode,
           'source_template':tid,'canvas':{'nodes':[{'id':'template-notes','kind':'text','label':'模板节奏参考','text':notes[:4000],'x':35,'y':30}],
                                        'edges':[{'source':'template-notes','target':'director'}]}}
        store.save(p,uid);store.event(p,'task','template_used')
        return store.present(p)
