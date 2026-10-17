"""Bounded O3 base-video editing through Kling's MCP protocol.

The official 0.1.4 CLI exposes discovery but has no omni_ref_video command.
Let that CLI refresh OAuth once, then use the discovered MCP tool contract.
Credentials, upload tickets, URLs and raw responses remain in memory. This
adapter runs inside the existing serialized, quota-accounted Kling worker.
"""
from contextlib import contextmanager
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import httpx

MODEL = 'kling-video-v3_0_omni'
BASE_URL = 'https://klingai.com'  # Same endpoint as the installed CN CLI.


class PreflightError(RuntimeError):
    pass


def spool_root():
    return Path(os.getenv('CREATIVE_RETAKE_INPUT_DIR', '/var/lib/visualstation-local/retake-inputs'))


def input_path(reference, sha256):
    """A private unguessable capability, never a caller-supplied URL/path."""
    if not isinstance(reference, str) or not re.fullmatch('[a-f0-9]{64}', reference):
        raise ValueError('Invalid retake reference')
    if not isinstance(sha256, str) or not re.fullmatch('[a-f0-9]{64}', sha256):
        raise ValueError('Invalid retake digest')
    root = spool_root().resolve()
    folder = root / reference
    path = folder / 'base.mp4'
    if folder.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Invalid retake reference')
    if not path.is_file() or not 1024 <= path.stat().st_size <= 60 * 1024 * 1024:
        raise ValueError('Retake input unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError('Retake input has changed')
    return path


def validate_request(body):
    if set(body) - {'task', 'model', 'prompt', 'conditions', 'target', 'enable_audio', 'prefer_multi_shots'}:
        raise ValueError('Unsupported retake parameter')
    if body.get('task') != 'v2v_edit' or body.get('model') != MODEL:
        raise ValueError('Base-video editing requires Kling O3')
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2400:
        raise ValueError('Invalid retake prompt')
    if body.get('enable_audio') is not False or body.get('prefer_multi_shots') is not False:
        raise ValueError('Retake cannot generate new audio or multiple shots')
    target = body.get('target')
    if not isinstance(target, dict) or set(target) != {'duration_seconds', 'short_edge', 'aspect_ratio'}:
        raise ValueError('Invalid retake target')
    seconds = target['duration_seconds']
    if type(seconds) is not int or not 3 <= seconds <= 10 or target['short_edge'] != 720 or target['aspect_ratio'] != 'auto':
        raise ValueError('Retake requires 3–10 seconds, 720p, source aspect')
    conditions = body.get('conditions')
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        raise ValueError('Exactly one base video is required')
    c = conditions[0]
    if set(c) != {'type', 'role', 'reference', 'sha256'} or c['type'] != 'video' or c['role'] != 'base':
        raise ValueError('Invalid base-video condition')
    return input_path(c['reference'], c['sha256'])


def _rpc(client, headers, payload):
    """One HTTP attempt; support JSON and finite SSE replies, with a size cap."""
    with client.stream('POST', BASE_URL + '/mcp', headers=headers, json=payload) as r:
        r.raise_for_status()
        session = r.headers.get('mcp-session-id')
        if session:
            headers['Mcp-Session-Id'] = session
        if 'id' not in payload:
            return None
        if 'text/event-stream' in r.headers.get('content-type', ''):
            size = 0
            data = []
            for line in r.iter_lines():
                size += len(line)
                if size > 4 * 1024 * 1024:
                    raise RuntimeError('MCP response too large')
                if line.startswith('data:'):
                    data.append(line[5:].lstrip())
                elif not line and data:
                    message = json.loads('\n'.join(data)); data = []
                    if message.get('id') == payload['id']:
                        break
            else:
                raise RuntimeError('MCP result missing')
        else:
            raw = bytearray()
            for chunk in r.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 4 * 1024 * 1024:
                    raise RuntimeError('MCP response too large')
            message = json.loads(raw)
        if message.get('id') != payload['id'] or 'error' in message:
            raise RuntimeError('MCP request did not return a result')
        return message['result']


@contextmanager
def connection():
    # Authentication refresh is owned by the CLI, called by submit() first.
    path = Path(os.getenv('KLING_HOME', str(Path.home() / '.kling'))) / '.credentials'
    config = configparser.ConfigParser(interpolation=None)
    config.read(path)
    section = config[urlparse(BASE_URL).netloc]
    token = section.get('ACCESS_TOKEN', '').strip().strip('"\'')
    expires = float(section.get('EXPIRES_AT', '0').strip('"\''))
    if not token or expires and expires < time.time() * 1000:
        raise PreflightError('Kling 登录需要更新')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream',
               'X-Kling-Cli-Name': '@klingai/cli-cn', 'X-Kling-Cli-Version': '0.1.4'}
    with httpx.Client(timeout=360, follow_redirects=False) as client:
        initialized = _rpc(client, headers, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'visualagent-retake', 'version': '1.0.0'}}})
        headers['MCP-Protocol-Version'] = initialized['protocolVersion']
        _rpc(client, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        def call(name, arguments):
            result = _rpc(client, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                            'params': {'name': name, 'arguments': arguments}})
            if result.get('isError'):
                raise RuntimeError('Kling tool did not return success')
            if 'structuredContent' in result:
                return result['structuredContent']
            content = result.get('content', [])
            if len(content) == 1 and content[0].get('type') == 'text':
                return json.loads(content[0]['text'])
            raise RuntimeError('Kling result cannot be confirmed')
        yield call, client


def provider_arguments(body, uploaded_url):
    values = {'prompt': body['prompt'], 'duration': str(body['target']['duration_seconds']),
              'aspect_ratio': 'auto', 'resolution': '720p', 'imageCount': '1',
              'prefer_multi_shots': 'false', 'enable_audio': 'false', 'keepOriginalSound': 'false'}
    return {'model': MODEL, 'arguments': [{'name': k, 'value': v} for k, v in values.items()],
            'inputs': [{'inputType': 'URL', 'name': 'video_1', 'url': uploaded_url}],
            'rationale': 'User explicitly approved one base-video visual edit. Preserve timing; original audio is restored locally after review.'}


def submit(body, cli_result, cli):
    from harness.models.kling_video import _first
    try:
        path = validate_request(body)
        discovery = cli_result([cli, 'who_am_i', '--quiet'])
        models = discovery['body']['availableModels']['omni_ref_video']['models']
        if not any(m.get('model') == MODEL for m in models):
            raise PreflightError('当前账户未开放视频编辑')
        # Recheck actual media, so a forged capability cannot underquote a longer input.
        from harness.tools.creative_edit_media import media_probe
        probe = media_probe(path)
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        length = float(video.get('duration', probe['format']['duration']))
        from fractions import Fraction
        fps = float(Fraction(video['avg_frame_rate']))
        if not 3 <= length <= 10.001 or length > body['target']['duration_seconds'] + .001 or not 24 <= fps <= 60:
            raise PreflightError('原片段时长或帧率不符合视频编辑要求')
        if min(video['width'], video['height']) < 720 or max(video['width'], video['height']) > 2160:
            raise PreflightError('原片段尺寸不符合视频编辑要求')
    except Exception as exc:
        raise PreflightError('重拍输入或账户能力检查未通过，未提交生成') from exc
    paid_call_started = False
    try:
        with connection() as (call, client):
            ticket = call('file_upload', {'filename': 'base.mp4', 'contentType': 'video/mp4', 'size': path.stat().st_size})
            url = ticket.get('uploadUrl') or ticket.get('upload_url')
            if not isinstance(url, str) or not url.startswith('https://'):
                raise ValueError('Invalid upload ticket')
            with path.open('rb') as stream:
                response = client.post(url, data={'ticket': ticket['ticket']}, files={'file': ('base.mp4', stream, 'video/mp4')})
            response.raise_for_status()
            uploaded = _first(response.json(), ('url', 'file_url', 'fileUrl', 'resource_url', 'resourceUrl'))
            if not isinstance(uploaded, str) or not uploaded.startswith('https://'):
                raise ValueError('Upload did not return a resource')
            # The only paid tool call. No retries, fallback parameters or model switch.
            paid_call_started = True
            return call('omni_ref_video', provider_arguments(body, uploaded))
    except Exception as exc:
        if not paid_call_started:
            raise PreflightError('原片段上传或账户检查未完成，未提交生成') from exc
        raise RuntimeError('重拍提交结果待核对，未重新生成') from exc
