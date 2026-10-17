from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.core.state import RunState

from .schema import SCHEMA_VERSION

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
_URL = re.compile(r"https?://[^\s\"'<>]+", re.I)
_SECRET_KEYS = ('api_key', 'apikey', 'credential', 'secret', 'token', 'signed_url',
                'base_url', 'authorization', 'cookie', 'password')
_PROMPT_KEYS = ('prompt', 'negative_prompt', 'audio_prompt')
_DROP_KEYS = ('raw_payload', 'provider_payload', 'provider_response', 'response_body')


def _safe_text(value):
    """Redact contact data and URLs before trajectory persistence."""
    text = _EMAIL.sub('<redacted-email>', str(value or ''))
    text = _PHONE.sub('<redacted-phone>', text)
    return _URL.sub('<redacted-url>', text)


def _safe_value(value, key=None, depth=0):
    """Bound trajectory values; preserve metrics while excluding raw payloads."""
    lowered = str(key or '').lower()
    if any(fragment in lowered for fragment in _SECRET_KEYS):
        return '<redacted>'
    if lowered in _DROP_KEYS:
        return '<omitted>'
    if lowered in _PROMPT_KEYS and isinstance(value, str):
        return {'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest(),
                'characters': len(value)}
    if depth > 5:
        return '<depth-limited>'
    if isinstance(value, dict):
        return {str(k): _safe_value(v, k, depth + 1) for k, v in list(value.items())[:128]}
    if isinstance(value, (list, tuple)):
        return [_safe_value(v, key, depth + 1) for v in list(value)[:128]]
    if isinstance(value, str):
        return _safe_text(value)[:4000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _safe_text(value)


class TrajectoryRecorder:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self, state: RunState, *, status: str | None = None,
        evaluation: dict[str, Any] | None = None,
    ) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{state.run_id}.json"
        payload = {
            "schema": SCHEMA_VERSION, "run_id": state.run_id, "task_id": state.task_id,
            "objective": _safe_text(state.objective), "inputs": _safe_value(state.inputs),
            "constraints": _safe_value(state.constraints), "metadata": _safe_value(state.metadata),
            "status": status, "steps": _safe_value(state.steps), "final": _safe_value(state.final),
            "evaluation": _safe_value(evaluation), "recorded_at": datetime.now(timezone.utc).isoformat(),
            "training_eligible": False, "human_review": "pending",
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target
