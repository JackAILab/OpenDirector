from __future__ import annotations

from abc import ABC, abstractmethod

from harness.core.state import RunState
from harness.core.types import AgentAction, Observation


class Agent(ABC):
    @abstractmethod
    def next_action(self, state: RunState) -> AgentAction: ...

    def observe(self, state: RunState, action: AgentAction, observation: Observation) -> None:
        return None

    def can_recover(self, state: RunState, observation: Observation) -> bool:
        return False
