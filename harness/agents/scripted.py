from __future__ import annotations

from collections.abc import Iterable

from harness.core.state import RunState
from harness.core.types import AgentAction

from .base import Agent


class ScriptedAgent(Agent):
    """Deterministic policy for reproducible tool/evaluator smoke runs."""

    def __init__(self, actions: Iterable[AgentAction]) -> None:
        self._actions = iter(actions)

    def next_action(self, state: RunState) -> AgentAction:
        try:
            return next(self._actions)
        except StopIteration:
            return AgentAction.finish({"steps_completed": len(state.steps)})
