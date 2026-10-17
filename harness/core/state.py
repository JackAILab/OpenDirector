from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any

from .types import AgentAction, Observation


@dataclass
class RunState:
    run_id: str
    task_id: str
    objective: str
    inputs: dict[str, Any]
    constraints: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    final: dict[str, Any] | None = None

    @staticmethod
    def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        secret_fragments = ("api_key", "credential", "token", "signed_url", "base_url")
        for key, value in arguments.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in secret_fragments):
                safe[key] = "<redacted>"
            elif lowered in {"prompt", "negative_prompt"} and isinstance(value, str):
                safe[key] = {
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    "characters": len(value),
                }
            else:
                safe[key] = value
        return safe

    @staticmethod
    def _safe_error(error: str | None) -> str | None:
        if not error:
            return error
        return re.sub(r"https?://[^\s\"'<>]+", "<temporary-url-redacted>", error)

    def record(self, action: AgentAction, observation: Observation) -> None:
        self.steps.append({
            "step_id": len(self.steps),
            "action": {
                "kind": action.kind,
                "tool_name": action.tool_name,
                "arguments": self._safe_arguments(action.arguments),
                "rationale": action.rationale,
            },
            "observation": {"ok": observation.ok, "content": observation.content, "error": self._safe_error(observation.error)},
        })
