from __future__ import annotations

from typing import Any

from harness.core.types import Observation

from .base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def execute(self, name: str, arguments: dict[str, Any]) -> Observation:
        tool = self._tools.get(name)
        if not tool:
            return Observation(ok=False, content={}, error=f"unknown tool: {name}")
        try:
            return tool.invoke(arguments)
        except Exception as exc:
            content = {"exception_type": type(exc).__name__}
            generation_id = getattr(exc, "generation_id", None)
            if isinstance(generation_id, str) and generation_id:
                content["generation_id"] = generation_id
            return Observation(
                ok=False, content=content,
                error=str(exc),
            )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
