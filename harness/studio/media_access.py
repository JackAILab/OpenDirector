"""Short-lived, asset-scoped browser playback grants; never persisted in trajectories."""
import base64
import hashlib
import hmac
import json
import secrets
import time

_SECRET = secrets.token_bytes(32)
TTL = 900
COOKIE = 'creative_media_preview'


def issue(uid, pid, aid):
    payload = base64.urlsafe_b64encode(json.dumps([uid, pid, aid, int(time.time()) + TTL], separators=(',', ':')).encode()).decode().rstrip('=')
    return payload + '.' + hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def verify(token, pid, aid):
    try:
        if not token or len(token) > 2048:
            return None
        payload, signature = token.split('.')
        expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        uid, project, asset, expiry = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if project != pid or asset != aid or not isinstance(expiry, int) or expiry <= time.time():
            return None
        return uid if type(uid) in (str, int) and uid else None
    except (ValueError, TypeError, UnicodeError):
        return None
