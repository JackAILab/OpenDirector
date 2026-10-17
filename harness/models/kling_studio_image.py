"""Explicit canonical Kling image model, bounded inputs, one paid attempt."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
from PIL import Image
from harness.models.kling_retake import connection
from harness.models.kling_video import _first, _task_status
from harness.models.kling_session import session_lock
from harness.models.generation_progress import report

MODELS=(
 ('kling-image-v3_0','Kling Image 3.0','强化一致性，自由多参考图'),
 ('kling-image-v3_0_omni','Kling Image 3.0 Omni','强化叙事感；本入口输出单张 2K 图片'),
 ('kling-image-o1','Kling Image O1','高特征一致性，精准细节修改，风格迁移'),
 ('kling-image-v2_1','Kling Image 2.1','指令遵循强，出图稳定；参考生成至少两张图'),
)

def catalog():
    available=bool(shutil.which(os.getenv('KLING_CLI','kling')))
    return [dict(id=i,label=n,description=d,mode='both',credits=1,max_references=3,max_reference_bytes=30*1024*1024,
                 min_edit_references=2 if i.endswith('v2_1') else 1,
                 region_composite=not i.endswith('v2_1'),region_brush=not i.endswith('v2_1'),
                 available=available,service_status='unchecked') for i,n,d in MODELS]

def arguments(model,prompt,aspect,references):
    if model not in {v[0] for v in MODELS}:raise ValueError('未接入此 Kling 生图模型')
    if len(references)>3 or model.endswith('v2_1') and len(references)==1:
        raise ValueError('Kling Image 2.1 参考生成至少需要两张图片；最多支持三张参考')
    task='image_to_image' if references else 'text_to_image'
    args=[{'name':'prompt','value':prompt},{'name':'aspect_ratio','value':aspect},{'name':'imageCount','value':'1'}]
    if not (references and model.endswith('v2_1')):args.append({'name':'img_resolution','value':'2k'})
    if references and model.endswith('v3_0_omni'):args.append({'name':'story_mode','value':'false'})
    return task,{'model':model,'arguments':args,'inputs':[{'inputType':'URL','name':f'subject_image_{i}' if model.endswith('v2_1') else f'image_{i+1}','url':u} for i,u in enumerate(references)],'rationale':'One explicitly approved image with the selected model and ordered references.'}

def cli(args):
    result=subprocess.run([os.getenv('KLING_CLI','kling'),*args,'--quiet'],capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError('Kling 图片服务未返回确定结果；未重试')
    return json.loads(result.stdout)

def generate(model,prompt,aspect,output,references):
    task,payload=arguments(model,prompt,aspect,references)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    record={'model':model,'operation':task,'automatic_retry':False,'training_eligible':False}
    def save(): (output/'attempt.json').write_text(json.dumps(record))
    save();paid=False
    try:
        report("queued")
        with session_lock():
            report("preparing")
            discovery=cli(['who_am_i'])['body']['availableModels'][task]['models']
            spec=next(m for m in discovery if m['model']==model)
            declared={a['name']:a for a in spec['arguments']}
            for arg in payload['arguments']:
                values=declared[arg['name']].get('allowedValues')
                if values and arg['value'] not in values:raise ValueError('模型参数已变化')
            if any(i['name'] not in {v['name'] for v in spec['inputs']} for i in payload['inputs']):raise ValueError('参考输入能力已变化')
            with connection() as (call,client):
                for item,path in zip(payload['inputs'],references):
                    path=Path(path)
                    with Image.open(path) as img: mime=Image.MIME[img.format]
                    ticket=call('file_upload',{'filename':'reference'+path.suffix,'contentType':mime,'size':path.stat().st_size})
                    with path.open('rb') as f:
                        response=client.post(ticket.get('uploadUrl') or ticket.get('upload_url'),data={'ticket':ticket['ticket']},files={'file':('reference'+path.suffix,f,mime)})
                    response.raise_for_status()
                    url=_first(response.json(),('url','file_url','fileUrl','resource_url','resourceUrl'))
                    if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('参考上传未完成')
                    item['url']=url
                report("submitting")
                paid=True
                submitted=call(task,payload)
        generation_id=_first(submitted,('generation_id','generationId','task_id'))
        if not isinstance(generation_id,str) or not generation_id:raise ValueError('无生成编号')
        record.update(generation_id=generation_id,state='running');save()
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            with session_lock(): result=cli(['query_tasks','--poll','0',generation_id])
            status=_task_status(result)
            percent=_first(result,("progress_percent","progressPercent","progress"))
            report("queued" if status in {"QUEUED","PENDING"} else "generating",percent)
            if status in {'FAILED','ERROR','CANCELLED','REJECTED'}:raise RuntimeError('供应商确认图片生成失败')
            if status in {'COMPLETED','SUCCEEDED','SUCCESS','FINISHED'}:
                url=_first(result,('urlWithoutWatermark','url_without_watermark','image_url','url'))
                if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('图片结果缺失')
                report('downloading')
                with urllib.request.urlopen(url,timeout=120) as r:data=r.read(32*1024*1024+1)
                if len(data)>32*1024*1024:raise ValueError('图片结果过大')
                with Image.open(io.BytesIO(data)) as img:img.verify()
                record['state']='completed';save();return data
            time.sleep(5)
        raise TimeoutError()
    except Exception as exc:
        record['state']='uncertain' if paid else 'not_submitted';save()
        raise RuntimeError('Kling 图片任务未取得完整结果，请核对任务后明确重新生成；不会自动重试' if paid else 'Kling 图片能力或参考上传校验未通过，未提交生成') from exc
