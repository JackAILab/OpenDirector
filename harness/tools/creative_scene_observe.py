"""Bounded browser observations for one saved scene; pixels are not trusted renders."""
import base64
import hashlib
import io
from typing import Literal
from PIL import Image
from pydantic import Field
from harness.tools.creative_scene import Strict, shot_at


class SceneFrame(Strict):
    kind: Literal['overview', 'camera']
    shot_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    at: float = Field(ge=0, le=60, allow_inf_nan=False)
    png: str = Field(min_length=1, max_length=2_800_000)


class SceneSuggestionRequest(Strict):
    revision: int = Field(ge=0)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    scene_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    intent: str = Field(min_length=1, max_length=1000)
    selected_object: str | None = Field(default=None, max_length=48)
    selected_shot: str = Field(max_length=48)
    frames: list[SceneFrame] = Field(min_length=1, max_length=4)


def observe_scene(spec, request):
    """Validate every frame and bound model input, without writing uploaded pixels."""
    if not request.intent.strip(): raise ValueError('请描述希望调整的场景或运镜')
    if request.selected_shot not in {s['id'] for s in spec['shots']}:
        raise ValueError('选中的镜头不存在')
    if request.selected_object is not None and request.selected_object not in {o['id'] for o in spec['objects']}:
        raise ValueError('选中的对象不存在')
    observations = []
    for i, frame in enumerate(request.frames):
        state = shot_at(spec, frame.at)
        if state['shot']['id'] != frame.shot_id: raise ValueError('截图时间与镜头不一致')
        try:
            raw = base64.b64decode(frame.png, validate=True)
            if len(raw)>2_000_000: raise ValueError()
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG' or max(im.size)>1920 or min(im.size)<128: raise ValueError()
                if frame.kind=='camera':
                    w,h=map(int,spec['aspect'].split(':'))
                    if abs(im.width/im.height/(w/h)-1)>.02: raise ValueError()
                im.load(); im=im.convert('RGB'); im.thumbnail((640,640))
                output=io.BytesIO();im.save(output,'JPEG',quality=70)
            pixels=output.getvalue()
            if len(pixels)>85_000: raise ValueError()
        except Exception as exc: raise ValueError('场景截图无效或过大，请重新请求建议') from exc
        observations.append(dict(id=f'view_{i+1}',kind=frame.kind,shot_id=frame.shot_id,
                                 at=frame.at,sha256=hashlib.sha256(pixels).hexdigest(),verified_render=False,
                                 image='data:image/jpeg;base64,'+base64.b64encode(pixels).decode()))
    return observations
