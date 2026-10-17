"""Bounded legacy Kling manual video adapter; one explicit MCP call, no fallback."""
from harness.models.kling_retake import connection, PreflightError
from harness.models.kling_video import _first

MODELS={'kling-video-v2_5','kling-video-v2_6','kling-video-o1','kling-video-v3_0_turbo'}


def payload(request, spec, urls):
    model=request['model']
    if model not in MODELS:raise ValueError('Unsupported manual model')
    values={'prompt':request['prompt'],'duration':str(request['duration']),
            'resolution':request['resolution'],'imageCount':'1'}
    declarations={a['name']:a for a in spec['arguments']}
    if 'aspect_ratio' in declarations:values['aspect_ratio']=request['aspect']
    if 'enable_audio' in declarations:values['enable_audio']=str(request['audio']).lower()
    elif request['audio']:raise ValueError('Audio unsupported')
    for name,value in values.items():
        allowed=declarations[name].get('allowedValues')
        if allowed and value not in allowed:raise ValueError('Unsupported argument')
    names=['image_'+str(i+1) for i in range(len(urls))] if model=='kling-video-o1' else ['first_image','tail_image'][:len(urls)]
    inputs={i['name']:i for i in spec.get('inputs',[])}
    if len(names)!=len(urls) or any(name not in inputs for name in names):raise ValueError('Unsupported references')
    if any(item.get('required') and name not in names for name,item in inputs.items()):raise ValueError('Missing required image')
    return {'model':model,'arguments':[{'name':k,'value':v} for k,v in values.items()],
            'inputs':[{'inputType':'URL','name':name,'url':url} for name,url in zip(names,urls)],
            'rationale':'One explicit manual generation with the user-selected model and inputs.'}


def submit(request, cli_result, cli):
    paid=False
    try:
        tool='image_to_video' if request['paths'] else 'text_to_video'
        discovery=cli_result([cli,'who_am_i','--quiet'])
        specs=discovery['body']['availableModels'][tool]['models']
        spec=next(m for m in specs if m['model']==request['model'])
        payload(request,spec,['https://validation.invalid/']*len(request['paths']))
        with connection() as (call,client):
            urls=[]
            for path in request['paths']:
                ticket=call('file_upload',{'filename':'reference.jpg','contentType':'image/jpeg','size':path.stat().st_size})
                url=ticket.get('uploadUrl') or ticket.get('upload_url')
                if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('Invalid ticket')
                with path.open('rb') as stream:
                    response=client.post(url,data={'ticket':ticket['ticket']},files={'file':('reference.jpg',stream,'image/jpeg')})
                response.raise_for_status()
                uploaded=_first(response.json(),('url','file_url','fileUrl','resource_url','resourceUrl'))
                if not isinstance(uploaded,str) or not uploaded.startswith('https://'):raise ValueError('Upload failed')
                urls.append(uploaded)
            body=payload(request,spec,urls)
            paid=True
            return call(tool,body)
    except Exception as exc:
        if not paid:raise PreflightError('Kling 模型或输入能力检查未通过，未提交生成') from exc
        raise RuntimeError('Kling 提交结果待核对，未重试或更换模型') from exc
