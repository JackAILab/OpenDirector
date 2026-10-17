"""Read-only deployment probes. Never authenticate, generate or expose endpoints."""
import asyncio
import time

import httpx


async def check_service(url, external=False):
    checked = int(time.time())
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(url.rstrip('/') + ('/healthz' if external else '/health'))
        response.raise_for_status()
        body = response.json()
        # A 200 from a proxy/login page is not evidence of a running adapter.
        if not isinstance(body, dict) or not (body.get('status') == 'ok' or body.get('ok') is True):
            raise ValueError('invalid health response')
        busy = body.get('active') is True or body.get('busy') is True
        status = 'busy' if busy else 'reachable'
    except (httpx.HTTPError, ValueError, TypeError):
        status = 'unavailable'
    return {'service_status': status, 'checked_at': checked, 'scope': 'deployment',
            'provider_authorization': 'unchecked', 'provider_balance': 'unchecked'}


async def check_pool(endpoints):
    if not endpoints:
        return {'service_status': 'unconfigured', 'checked_at': int(time.time()),
                'scope': 'deployment', 'provider_authorization': 'unchecked',
                'provider_balance': 'unchecked'}
    results = await asyncio.gather(*(check_service(url, external) for url, external in endpoints))
    for status in ('reachable', 'busy', 'unavailable'):
        selected = next((r for r in results if r['service_status'] == status), None)
        if selected:
            return selected
