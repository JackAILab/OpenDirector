"""Single-call research adapter with explicit model and no retries/fallbacks."""
import json
import os
from pathlib import Path
import httpx


class IncompletePlanningError(ValueError):
    def __init__(self, finish_reason, usage):
        super().__init__('planning_incomplete')
        self.diagnostics = {'finish_reason':finish_reason if finish_reason in ('length','content_filter','tool_calls','function_call') else 'other'}
        self.usage = usage


class ResearchPlanner:
    def __init__(self, model, max_tokens=2200):
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, messages):
        key = Path(os.environ['CREATIVE_MODEL_KEY_FILE']).read_text().strip()
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            response = await client.post(os.environ['CREATIVE_MODEL_URL'].rstrip('/')+'/chat/completions',
                headers={'Authorization':'Bearer '+key},
                json={'model':self.model,'messages':messages,'max_tokens':self.max_tokens,
                      'temperature':0,'stream':False})
        if response.status_code != 200:
            raise RuntimeError('planning_http_'+str(response.status_code))
        raw = response.json(); choice = raw['choices'][0]
        usage = raw.get('usage') or {}
        safe_usage = {k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(usage.get(k)) is int}
        if choice.get('finish_reason') != 'stop':
            raise IncompletePlanningError(choice.get('finish_reason'),safe_usage)
        text = choice['message']['content'].strip()
        if text.startswith('```'):
            text = text.split('\n',1)[1].rsplit('```',1)[0]
        return json.loads(text), safe_usage
