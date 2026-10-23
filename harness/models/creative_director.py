"""Bounded JSON planning adapter. Credentials never leave this boundary."""
import json
import os
from pathlib import Path
import httpx


class PlanningServiceError(RuntimeError):
    pass


class PlanningResponseError(ValueError):
    """Only bounded codes may cross the provider boundary."""
    def __init__(self, code):
        self.code = code if code in {'output_truncated', 'response_envelope', 'response_content', 'invalid_json'} else 'response_content'
        super().__init__(self.code)


class CreativeDirectorModel:
    async def complete(self, messages: list[dict], on_decision=None) -> dict:
        key = Path(os.environ['CREATIVE_MODEL_KEY_FILE']).read_text().strip()
        # Do not impose a smaller output allowance than the provider supports.
        # Partial JSON exists only within this call, never in a trajectory.
        payload = {'model': os.environ.get('CREATIVE_MODEL', 'cb-gpt-5.6-sol'),
                   'messages': list(messages), 'stream': bool(on_decision)}
        url = os.environ['CREATIVE_MODEL_URL'].rstrip('/') + '/chat/completions'
        headers = {'Authorization': 'Bearer ' + key}
        content = ''
        emitted = 0
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            # Bounded provider continuations, not retries with another model or
            # a new creative plan. The original request remains authoritative.
            for continuation in range(3):
                if on_decision:
                    fragment, finish, emitted = await self._stream(
                        client, url, headers, payload, content, emitted, on_decision)
                else:
                    fragment, finish = await self._response(client, url, headers, payload)
                if not fragment or (content and fragment == content):
                    raise PlanningResponseError('output_truncated' if finish == 'length' else 'response_content')
                content += fragment
                if finish != 'length':
                    return parse_content(content)
                # A valid complete JSON document with a length finish is still
                # rejected: it may omit required fields. Only incomplete JSON
                # with a real prefix can be continued safely.
                prefix = content.lstrip()
                if not prefix.startswith('{') or continuation == 2:
                    raise PlanningResponseError('output_truncated')
                try:
                    json.loads(prefix)
                except ValueError:
                    pass
                else:
                    raise PlanningResponseError('output_truncated')
                payload['messages'] = [*messages,
                    {'role': 'assistant', 'content': content},
                    {'role': 'user', 'content': (
                        'The previous JSON response was cut off by the provider output limit. '
                        'Continue immediately after its last character, including inside an unfinished '
                        'string if necessary. Return ONLY the remaining JSON suffix. Do not repeat '
                        'the prefix, restart the object, add markdown, or change any earlier decision. '
                        'Complete the original requested plan and close the JSON object.')}]

    async def _stream(self, client, url, headers, payload, prefix, emitted, on_decision):
        fragment = ''
        finish = None
        async with client.stream('POST', url, headers=headers, json=payload) as response:
            if not response.is_success:
                raise PlanningServiceError('创作模型暂时不可用')
            async for line in response.aiter_lines():
                if not line.startswith('data:'): continue
                data = line[5:].strip()
                if data == '[DONE]': break
                try:
                    choices = json.loads(data).get('choices', [])
                    if not choices: continue
                    choice = choices[0]
                    # A terminal chunk can carry the final text as well as its
                    # finish reason; keep that text before deciding to resume.
                    delta = choice.get('delta', {}).get('content')
                    if isinstance(delta, str): fragment += delta
                    if choice.get('finish_reason') is not None:
                        finish = choice['finish_reason']
                except (ValueError, TypeError, KeyError, AttributeError):
                    raise PlanningResponseError('response_envelope') from None
                for decision in public_decisions(prefix + fragment)[emitted:]:
                    on_decision(decision)
                    emitted += 1
        if finish not in ('stop', 'length'):
            raise PlanningResponseError('response_content')
        return fragment, finish, emitted

    async def _response(self, client, url, headers, payload):
        response = await client.post(url, headers=headers, json=payload)
        if not response.is_success:
            raise PlanningServiceError('创作模型暂时不可用（HTTP %s），尚未提交视频生成。' % response.status_code)
        try:
            choice = response.json()['choices'][0]
            if not isinstance(choice, dict): raise TypeError()
        except (ValueError, KeyError, IndexError, TypeError):
            raise PlanningResponseError('response_envelope') from None
        try:
            content = choice['message']['content']
            if isinstance(content, list): content = ''.join(x.get('text', '') for x in content)
            if not isinstance(content, str): raise TypeError()
        except (KeyError, TypeError, AttributeError):
            raise PlanningResponseError('response_content') from None
        return content, choice.get('finish_reason')


def parse_content(content):
    content = content.strip()
    if content.startswith('```') and '\n' in content:
        content = content.split('\n', 1)[1].rsplit('```', 1)[0]
    try:
        return json.loads(content)
    except ValueError:
        raise PlanningResponseError('invalid_json') from None


def public_decisions(content):
    """Read complete objects in the top-level decisions array, even mid-stream.

    Parse keys/values structurally so quoted prompt text cannot impersonate a key.
    Partial decisions stay private until both title and reason are complete.
    """
    content = content.strip()
    if content.startswith('```') and '\n' in content: content = content.split('\n', 1)[1]
    if not content.startswith('{'): return []
    decoder = json.JSONDecoder()
    pos = 1
    try:
        while True:
            while pos < len(content) and content[pos] in ' \r\n\t,': pos += 1
            key, pos = decoder.raw_decode(content, pos)
            while pos < len(content) and content[pos].isspace(): pos += 1
            if content[pos] != ':': return []
            pos += 1
            while pos < len(content) and content[pos].isspace(): pos += 1
            if key == 'decisions':
                if content[pos] != '[': return []
                pos += 1
                result = []
                while len(result) < 8:
                    while pos < len(content) and content[pos] in ' \r\n\t,': pos += 1
                    try: item, pos = decoder.raw_decode(content, pos)
                    except ValueError: break
                    if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ('title', 'reason')): break
                    result.append({'title': item['title'][:100], 'reason': item['reason'][:800]})
                return result
            _, pos = decoder.raw_decode(content, pos)
    except (ValueError, IndexError):
        return []
