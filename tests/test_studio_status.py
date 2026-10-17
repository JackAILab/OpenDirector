"""Deployment connectivity must not claim paid-provider readiness or leak internals."""
import asyncio

import httpx
import pytest

from harness.models import studio_status
from test_creative_studio import client


@pytest.mark.parametrize('body,status', [
    ({'status': 'ok', 'active': False}, 'reachable'),
    ({'status': 'ok', 'active': True}, 'busy'),
    ({'ok': True, 'busy': True}, 'busy'),
    ({'login': 'required'}, 'unavailable'),
    ([], 'unavailable'),
])
def test_probe_sanitizes_and_requires_health_evidence(monkeypatch, body, status):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {'timeout': 3, 'trust_env': False}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            calls.append(url)
            return httpx.Response(200, json=body, request=httpx.Request('GET', url))
    monkeypatch.setattr(studio_status.httpx, 'AsyncClient', Client)
    result = asyncio.run(studio_status.check_service('http://private-worker'))
    assert calls == ['http://private-worker/health']
    assert result['service_status'] == status
    assert result['provider_authorization'] == result['provider_balance'] == 'unchecked'
    assert 'private-worker' not in str(result)
    assert set(result) == {'service_status', 'checked_at', 'scope', 'provider_authorization', 'provider_balance'}


def test_pool_prefers_idle_service_and_sanitizes_failure(monkeypatch):
    async def probe(url, external):
        return {'service_status': url, 'checked_at': 123}
    monkeypatch.setattr(studio_status, 'check_service', probe)
    assert asyncio.run(studio_status.check_pool([('unavailable', False), ('busy', True), ('reachable', True)]))['service_status'] == 'reachable'
    assert asyncio.run(studio_status.check_pool([]))['service_status'] == 'unconfigured'


def test_status_requires_session_and_cannot_enable_unverified_model(client, monkeypatch):
    calls = []
    async def pool(endpoints):
        calls.append(endpoints)
        return {'service_status': 'unconfigured', 'checked_at': 123, 'scope': 'deployment',
                'provider_authorization': 'unchecked', 'provider_balance': 'unchecked'}
    monkeypatch.setattr(studio_status, 'check_pool', pool)
    assert client.get('/creative/api/model-status', headers={'Authorization': 'invalid'}).status_code == 401
    first = client.get('/creative/api/model-status')
    assert first.status_code == 200
    assert len(first.json()['models']) == 4
    assert client.get('/creative/api/model-status').json() == first.json()
    assert len(calls) == 2  # One probe per provider; second request uses 30-second cache.
    assert client.post('/creative/api/projects', json={'message': '广告制作', 'provider': 'minimax-h3', 'model': 'MiniMax-H3'}).status_code == 422
