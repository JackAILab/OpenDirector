"""Fixed CodeBuddy protocols. One paid attempt, no provider fallback or retry."""
import json
import os
from pathlib import Path
import subprocess

CLI = '/usr/local/bin/codebuddy-image'
IMAGE_MODELS = (
    {'id':'hunyuan-image-v3.0','label':'混元 Image 3.0','mode':'text','credits':1,'max_references':0},
    {'id':'hunyuan-image-v2.0-general-edit','label':'混元 Image 2.0 · 参考图编辑','mode':'edit','credits':1,'max_references':3,'region_composite':True,'region_brush':True},
)


def image_models():
    configured = (os.getenv('OPENAI_IMAGE_MODEL') in ('gpt-image-2','gp2/gpt-image-2')
                  and all(os.getenv(k) for k in ('OPENAI_BASE_URL','OPENAI_API_KEY'))
                  and os.getenv('CREATIVE_GPT_IMAGE_ENABLED')=='1')
    from harness.models.kling_studio_image import catalog
    return catalog()+[dict(m, available=os.access(CLI, os.X_OK)) for m in IMAGE_MODELS]+[
        {'id':'gpt-image-2','label':'GPT Image 2 · 真实 GPT 接口','mode':'text','credits':1,'max_references':0,
         'available':bool(configured),'limitation':'' if configured else '等待真实接口配置与验证'}]


def generate(model, prompt, aspect, output, reference=None):
    references=list(reference) if isinstance(reference,(list,tuple)) else [reference] if reference else []
    if len(references)>3 or len(set(map(str,references)))!=len(references):
        raise ValueError('参考图片最多三张，不可重复')
    if model.startswith('kling-image-'):
        from harness.models.kling_studio_image import generate as kling_generate
        return kling_generate(model,prompt,aspect,output,references)
    if model=='gpt-image-2':
        if not next(m for m in image_models() if m['id']==model)['available']:
            raise RuntimeError('真实 GPT 图像接口尚未配置，不会改用其他模型')
        if references:raise ValueError('当前 GPT 入口仅支持文字生成')
        from harness.models.openai_image import OpenAIImageModel
        from harness.models.base import ImageRequest
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
        (output/'attempt.json').write_text(json.dumps({'model':os.environ['OPENAI_IMAGE_MODEL'],'automatic_retry':False}))
        result=OpenAIImageModel(expected_model=os.environ['OPENAI_IMAGE_MODEL']).create(ImageRequest(
            prompt=prompt,output=output/'image.png',model=os.environ['OPENAI_IMAGE_MODEL'],
            size={'16:9':'1824x1024','9:16':'1024x1824','1:1':'1024x1024'}[aspect]))
        return result.output.read_bytes()
    spec=next(m for m in IMAGE_MODELS if m['id']==model)
    if (spec['mode']=='edit') != bool(references):
        raise ValueError('图片模型与输入模式不匹配')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'attempt.json').write_text(json.dumps({'model':model,'automatic_retry':False}))
    args=[CLI,'--prompt',prompt,'--size',{'16:9':'1024x576','9:16':'576x1024','1:1':'1024x1024'}[aspect],'--output-dir',str(output)]
    for path in references: args+=['--reference-image',str(path)]
    result=subprocess.run(args,capture_output=True,text=True,timeout=600)
    if result.returncode: raise RuntimeError('图片服务未完成，可能已消耗额度，请核对后明确新建一次生成')
    paths=json.loads(result.stdout)['outputs']
    if len(paths)!=1: raise RuntimeError('图片服务输出数量异常')
    path=Path(paths[0]['path']).resolve()
    if not path.is_relative_to(output.resolve()) or not path.is_file(): raise RuntimeError('图片输出不可读取')
    return path.read_bytes()
