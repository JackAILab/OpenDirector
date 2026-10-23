import asyncio
import copy
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from harness.models.creative_director import CreativeDirectorModel, PlanningResponseError


@pytest.fixture
def configured(monkeypatch, tmp_path):
    key = tmp_path / 'key'
    key.write_text('test-key')
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE', str(key))
    monkeypatch.setenv('CREATIVE_MODEL_URL', 'https://example.invalid')
    monkeypatch.setenv('CREATIVE_MODEL', 'selected-model')


def test_nonstream_continues_cut_string_without_output_cap(configured, monkeypatch):
    result = {'reply': '已完成', 'shots': [{'prompt': 'Detailed scene ' * 9000}]}
    content = json.dumps(result, ensure_ascii=False)
    # Deliberately cut inside a JSON string and exceed the old character limit.
    pieces = [content[:45001], content[45001:]]
    requests = []
    async def post(self, *args, **kwargs):
        requests.append(copy.deepcopy(kwargs['json']))
        piece = pieces.pop(0)
        return httpx.Response(200, json={'choices': [{'message': {'content': piece},
            'finish_reason': 'length' if pieces else 'stop'}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    messages = [{'role': 'user', 'content': 'Make a 60 second ad'}]
    original = copy.deepcopy(messages)
    assert asyncio.run(CreativeDirectorModel().complete(messages)) == result
    assert messages == original
    assert len(requests) == 2
    assert requests[1]['messages'][-2] == {'role': 'assistant', 'content': content[:45001]}
    for request in requests:
        assert request['model'] == 'selected-model'
        assert not {'max_tokens', 'max_output_tokens', 'max_completion_tokens'} & request.keys()


def test_stream_keeps_terminal_delta_and_emits_decisions_once(configured, monkeypatch):
    decision = {'title': 'Use product reference', 'reason': 'Preserve geometry'}
    result = {'decisions': [decision], 'shots': [{'prompt': 'scene ' * 19000}]}
    content = json.dumps(result)
    pieces = [content[:50001], content[50001:]]
    seen, requests = [], []
    class Response:
        is_success = True
        def __init__(self, piece, finish): self.piece, self.finish = piece, finish
        async def aiter_lines(self):
            yield 'data: ' + json.dumps({'choices': [{'delta': {
                'reasoning_content': 'private reasoning', 'content': self.piece[:-7]}}]})
            # Continuation must include content carried in the terminal event.
            yield 'data: ' + json.dumps({'choices': [{'delta': {'content': self.piece[-7:]},
                'finish_reason': self.finish}]})
            yield 'data: [DONE]'
    @asynccontextmanager
    async def stream(self, *args, **kwargs):
        requests.append(copy.deepcopy(kwargs['json']))
        piece = pieces.pop(0)
        yield Response(piece, 'length' if pieces else 'stop')
    monkeypatch.setattr(httpx.AsyncClient, 'stream', stream)
    assert asyncio.run(CreativeDirectorModel().complete([], seen.append)) == result
    assert seen == [decision]
    assert requests[1]['messages'][-2]['content'] == content[:50001]
    assert all('max_tokens' not in r for r in requests)
    assert 'private reasoning' not in str(requests)


def test_repeated_provider_truncation_is_bounded(configured, monkeypatch):
    calls = []
    async def post(self, *args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json={'choices': [{'message': {
            'content': '{"reply":"' if len(calls) == 1 else 'more'}, 'finish_reason': 'length'}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    with pytest.raises(PlanningResponseError, match='^output_truncated$'):
        asyncio.run(CreativeDirectorModel().complete([]))
    assert len(calls) == 3


def test_transport_failure_does_not_restart_generation(configured, monkeypatch):
    calls = []
    async def post(self, *args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout('private connection details')
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(CreativeDirectorModel().complete([]))
    assert len(calls) == 1
