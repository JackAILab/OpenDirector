"""Review and save video input selection; saving never authorizes generation."""
from fastapi import Header,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from typing import Literal
from harness.studio import store
from harness.studio.image_api import ImageReference
from harness.tools.creative_video_inputs import prepare
from harness.tools.creative_image_inputs import content_hash


class ManualDraft(BaseModel):
    model_config={'extra':'forbid'}
    prompt:str=Field(max_length=4000)
    duration:int=Field(ge=3,le=30)


class Selection(BaseModel):
    model_config={'extra':'forbid'}
    manual:ManualDraft|None=None
    revision:int
    model:Literal['kling-video-v3_0','kling-video-v3_0_omni','kling-video-v4_0','kling-video-v2_5','kling-video-v2_6','kling-video-o1','kling-video-v3_0_turbo']
    mode:Literal['text','first_frame','first_last','references']
    references:list[ImageReference]=Field(default_factory=list,max_length=7)


class Confirm(Selection):
    input_hash:str=Field(pattern=r'^[a-f0-9]{64}$')


def install(gateway):
    @gateway.app.get('/creative/video-inputs.js',include_in_schema=False)
    def script():return FileResponse(store.ROOT/'tools/agent_studio/video-inputs.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    def resolve(p,body):
        if p['revision']!=body.revision or p['id'] in store.RUNNING or p['state'] in ('running','rendering','planning'):
            raise HTTPException(409,'项目已变化或正在制作，请重新核对')
        if p.get('film') and p['film'].get('state') not in ('planned','completed','failed'):
            raise HTTPException(409,'原任务尚未结束，请恢复查询后再修改输入')
        if p.get('campaign') and p['state']!='completed':raise HTTPException(409,'已有章节任务，请恢复查询或新建项目；不能修改已批准的输入')
        if p.get('generation_mode')=='chaptered_native' and (body.model not in ('kling-video-v4_0','kling-video-v3_0_omni') or len(body.references)>6):raise HTTPException(422,'多章节需多图参考模型，并保留一个尾帧输入位置')
        if body.manual and p.get('creation_mode')!='video':raise HTTPException(422,'仅手动视频可保存节点草稿')
        from harness.models.video_catalog import model_spec
        spec=model_spec('kling',body.model)
        if p.get('creation_mode')!='video' and not spec['single_film']:raise HTTPException(422,'Agent 方案需要 15 秒有声模型')
        if p.get('creation_mode')=='video' and (body.manual.duration if body.manual else p['duration']) not in spec['manual_durations']:raise HTTPException(422,'请先选择支持当前时长的模型')
        try:return prepare(p,body.model,body.mode,[r.model_dump() for r in body.references])
        except (ValueError,OSError) as exc:raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else '参考图暂不可读取') from exc

    def review_hash(inputs,body):
        return content_hash(dict(inputs=inputs['input_hash'],manual=body.manual.model_dump())) if body.manual else inputs['input_hash']

    @gateway.app.post('/creative/api/projects/{pid}/video-inputs/preview')
    async def preview(pid:str,body:Selection,authorization:str|None=Header(None)):
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid);inputs=resolve(p,body)
            return dict(inputs,input_hash=review_hash(inputs,body),requires_plan=p.get('creation_mode')!='video' and p.get('video_inputs')!=inputs)

    @gateway.app.put('/creative/api/projects/{pid}/video-inputs')
    async def save(pid:str,body:Confirm,authorization:str|None=Header(None)):
        uid=gateway.require_session(authorization)['id']
        async with store.lock(pid):
            p=store.load(pid,uid);inputs=resolve(p,body)
            if body.input_hash!=review_hash(inputs,body):raise HTTPException(409,'输入与核对版本不一致，请重新预览')
            if p.get('video_inputs')!=inputs or (body.manual and (body.manual.duration!=p['duration'] or body.manual.prompt!=p.get('direct_prompt'))):
                store.archive_render(p)
                p.update(state='intake',shots=[],questions=[],error='',provider='kling',model=body.model,generation_mode='chaptered_native' if p.get('generation_mode')=='chaptered_native' else 'single_native',duration=(body.manual.duration if body.manual else p['duration']) if p.get('creation_mode')=='video' or p.get('generation_mode')=='chaptered_native' else 15)
                if body.manual:p['direct_prompt']=body.manual.prompt
                for key in ('run_id','artifact','qa','film','stop_requested','auto_approval','campaign'):p.pop(key,None)
                if p.get('creation_mode')=='video' and p.get('direct_prompt'):
                    p.update(state='ready',shots=[{'id':'shot_1','start':0,'duration':p['duration'],'title':'视频节点 1',
                        'prompt':p['direct_prompt'],'audio_prompt':'按用户描述生成同步声音',
                        'caption':'','state':'planned','rationale':'用户直接描述'}])
            p.update(video_inputs=inputs,video_inputs_product=p.get('brief',{}).get('product',''))
            p['revision']+=1;store.save(p,uid);store.event(p,'task','video_inputs_confirmed')
            return store.present(p)
