"""Kling 4.0 Omni: one explicit submission in the serialized studio worker.

Discovery, upload tickets and provider URLs stay in memory. No fallback/retry.
This bounded entry supports text and up to seven images, one 3–15s output.
"""
from harness.models.kling_retake import connection, PreflightError
from harness.models.kling_video import _first

MODEL = 'kling-video-v4_0'


def provider_arguments(request, urls):
    values = {'prompt': request['prompt'], 'duration': str(request['duration']),
              'aspect_ratio': request['aspect'], 'resolution': request['resolution'],
              'imageCount': '1', 'prefer_multi_shots': 'true',
              'enable_audio': str(request['audio']).lower(), 'keepOriginalSound': 'false'}
    return {'model': MODEL, 'arguments': [{'name': k, 'value': v} for k, v in values.items()],
            'inputs': [{'inputType': 'URL', 'name': f'image_{i+1}', 'url': url}
                       for i, url in enumerate(urls)],
            'rationale': 'One user-approved video with the selected model, duration, aspect and ordered image references.'}


def submit(request, cli_result, cli):
    paid = False
    try:
        discovery = cli_result([cli, 'who_am_i', '--quiet'])
        models = discovery['body']['availableModels']['omni_ref_video']['models']
        spec = next(m for m in models if m['model'] == MODEL)
        declared = {arg['name']: arg for arg in spec['arguments']}
        for arg in provider_arguments(request, [])['arguments']:
            allowed = declared[arg['name']].get('allowedValues')
            if allowed and arg['value'] not in allowed:
                raise ValueError('Model capability changed')
        if len(request['paths']) > 7 or any(f'image_{i+1}' not in {v['name'] for v in spec['inputs']}
                                            for i in range(len(request['paths']))):
            raise ValueError('Unsupported image inputs')
        with connection() as (call, client):
            urls = []
            for path in request['paths']:
                ticket = call('file_upload', {'filename': 'reference.jpg', 'contentType': 'image/jpeg',
                                              'size': path.stat().st_size})
                url = ticket.get('uploadUrl') or ticket.get('upload_url')
                if not isinstance(url, str) or not url.startswith('https://'):
                    raise ValueError('Invalid upload ticket')
                with path.open('rb') as stream:
                    response = client.post(url, data={'ticket': ticket['ticket']},
                                           files={'file': ('reference.jpg', stream, 'image/jpeg')})
                response.raise_for_status()
                uploaded = _first(response.json(), ('url', 'file_url', 'fileUrl', 'resource_url', 'resourceUrl'))
                if not isinstance(uploaded, str) or not uploaded.startswith('https://'):
                    raise ValueError('Upload did not return a resource')
                urls.append(uploaded)
            paid = True
            return call('omni_ref_video', provider_arguments(request, urls))
    except Exception as exc:
        if not paid:
            raise PreflightError('Kling 4.0 能力或参考上传检查未完成，未提交生成') from exc
        raise RuntimeError('Kling 4.0 提交结果待核对，未重新生成') from exc
