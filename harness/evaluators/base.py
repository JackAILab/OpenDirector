from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from harness.core.state import RunState


class Evaluator(ABC):
    @abstractmethod
    def evaluate(self, state: RunState) -> dict[str, Any]: ...
