"""Loop policies shared by runners and experiment configurations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoopPolicy:
    max_steps: int = 8
    stop_on_tool_error: bool = True
    retry_limit: int = 0
