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
    async def complete(self, messages: list[dict]) -> dict:
        key = Path(os.environ['CREATIVE_MODEL_KEY_FILE']).read_text().strip()
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            response = await client.post(os.environ['CREATIVE_MODEL_URL'].rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + key}, json={
                    'model': os.environ.get('CREATIVE_MODEL', 'cb-gpt-5.6-sol'),
                    'messages': messages, 'stream': False, 'max_tokens': 10000})
        if not response.is_success:
            raise PlanningServiceError('创作模型暂时不可用（HTTP %s），尚未提交视频生成。' % response.status_code)
        try:
            choice = response.json()['choices'][0]
            if not isinstance(choice, dict): raise TypeError()
        except (ValueError, KeyError, IndexError, TypeError):
            raise PlanningResponseError('response_envelope') from None
        if choice.get('finish_reason') == 'length':
            raise PlanningResponseError('output_truncated')
        try:
            content = choice['message']['content']
            if isinstance(content, list): content = ''.join(x.get('text', '') for x in content)
            if not isinstance(content, str): raise TypeError()
        except (KeyError, TypeError, AttributeError):
            raise PlanningResponseError('response_content') from None
        content = content.strip()
        if content.startswith('```') and '\n' in content:
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        try:
            return json.loads(content)
        except ValueError:
            raise PlanningResponseError('invalid_json') from None
