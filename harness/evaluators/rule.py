from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harness.core.state import RunState

from .base import Evaluator


class RuleEvaluator(Evaluator):
    def __init__(self, rules: dict[str, Callable[[RunState], bool]]) -> None:
        self.rules = rules

    def evaluate(self, state: RunState) -> dict[str, Any]:
        checks = {name: bool(rule(state)) for name, rule in self.rules.items()}
        return {"passed": all(checks.values()), "checks": checks}
