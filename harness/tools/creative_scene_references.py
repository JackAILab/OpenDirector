"""Publish reviewed browser frames with explicit shot provenance; no model calls."""
import base64
import copy
import hashlib
import io
import shutil
import secrets
from PIL import Image
from pydantic import BaseModel,ConfigDict,Field
from harness.tools.creative_scene import validate_scene,scene_hash,shot_at,shot_note
from harness.tools.creative_canvas import save_asset,asset_directory,validate_graph,next_position


class Frame(BaseModel):
    model_config=ConfigDict(extra='forbid')
    shot_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    at:float=Field(ge=0,le=60,allow_inf_nan=False)
    png:str=Field(min_length=1,max_length=2_800_000)


class FrameBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int
    request_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{8,64}$')
    scene_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    connect_to_director:bool=False
    frames:list[Frame]=Field(min_length=1,max_length=6)


def request_hash(batch):
    return hashlib.sha256(batch.model_dump_json().encode()).hexdigest()


def publish_frames(project,batch):
    """Validate the complete batch before any asset write, then return a new project."""
    if not project.get('scene3d'):raise ValueError('请先保存场景')
    spec=validate_scene(project['scene3d'],project.get('scene_assets',{}))
    if scene_hash(spec)!=batch.scene_hash:raise ValueError('场景已变化，请重新核对镜头')
    graph=project.get('canvas',{'nodes':[],'edges':[]});count=len(batch.frames)
    if len(graph['nodes'])+count>16 or len(project.get('canvas_assets',{}))+count>32:raise ValueError('画布空间不足，请先整理素材')
    linked={e['source'] for e in graph['edges']}
    if batch.connect_to_director and sum(n['kind']!='text' for n in graph['nodes'] if n['id'] in linked)+count>6:raise ValueError('导演最多连接 6 个图片或视频参考')
    if len({f.shot_id for f in batch.frames})!=count:raise ValueError('每个镜头只能选择一张参考帧')
    decoded=[];aspect={'16:9':16/9,'9:16':9/16,'1:1':1}[spec['aspect']]
    for frame in batch.frames:
        state=shot_at(spec,frame.at)
        if state['shot']['id']!=frame.shot_id:raise ValueError('帧时间与镜头不一致')
        try:
            raw=base64.b64decode(frame.png,validate=True)
            if len(raw)>2_000_000:raise ValueError()
            with Image.open(io.BytesIO(raw)) as img:
                if img.format!='PNG' or max(img.size)>1920 or min(img.size)<128 or abs(img.width/img.height/aspect-1)>.02:raise ValueError()
                img.verify()
        except Exception as exc:raise ValueError('参考帧需为画幅一致、2 MB 以内的有效 PNG') from exc
        decoded.append((frame,state,raw))
    decoded.sort(key=lambda item:item[1]['index'])
    result=copy.deepcopy(project);graph=result.setdefault('canvas',{'nodes':[],'edges':[]});created=[]
    try:
        x=max([40]+[n['x']+310 for n in graph['nodes']]);records=[]
        for i,(frame,state,raw) in enumerate(decoded):
            asset=save_asset(result,raw,'image',max_bytes=2_000_000);created.append(asset['id'])
            asset['provenance']=dict(kind='scene_browser_preview',scene_hash=batch.scene_hash,shot_id=frame.shot_id,
                shot_name=state['shot']['name'],shot_index=state['index'],at=frame.at,local_time=state['local'],
                camera=state['shot']['camera'],verified_render=False,training_eligible=False)
            result.setdefault('canvas_assets',{})[asset['id']]=asset
            nid='scene_'+secrets.token_hex(6)
            position={'x':x+i*310,'y':30} if x+i*310<=9000 else next_position(graph)
            node=dict(id=nid,kind='image',role='scene',label=f"镜头 {state['index']+1} · {state['shot']['name']}"[:80],
                text=shot_note(spec,frame.at),asset=asset['id'],**position)
            graph['nodes'].append(node)
            if batch.connect_to_director:graph['edges'].append(dict(source=nid,target='director'))
            records.append(dict(asset=asset['id'],node=nid,shot_id=frame.shot_id,at=frame.at))
        result['canvas']=validate_graph(graph,result['canvas_assets'])
        return result,records
    except Exception:
        for aid in created:shutil.rmtree(asset_directory(result,aid),ignore_errors=True)
        raise
