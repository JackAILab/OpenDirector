from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from harness.core.types import Observation


class Tool(ABC):
    name: str
    layer: str = "generic"
    paid: bool = False

    @abstractmethod
    def invoke(self, arguments: dict[str, Any]) -> Observation: ...
