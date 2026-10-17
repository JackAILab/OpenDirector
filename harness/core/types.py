from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class AgentAction:
    kind: Literal["tool", "finish"]
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    final: dict[str, Any] | None = None
    rationale: str | None = None

    @classmethod
    def tool(cls, name: str, arguments: dict[str, Any], *, rationale: str | None = None) -> "AgentAction":
        return cls(kind="tool", tool_name=name, arguments=arguments, rationale=rationale)

    @classmethod
    def finish(cls, final: dict[str, Any]) -> "AgentAction":
        return cls(kind="finish", final=final)


@dataclass(frozen=True)
class Observation:
    ok: bool
    content: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: Literal["completed", "failed", "max_steps"]
    final: dict[str, Any]
    trajectory_path: str | None
    evaluation: dict[str, Any] | None
