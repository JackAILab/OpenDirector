from __future__ import annotations

from typing import Any

from harness.core.state import RunState

from .base import Evaluator


class CompositeEvaluator(Evaluator):
    def __init__(self, evaluators: dict[str, Evaluator]) -> None:
        self.evaluators = evaluators

    def evaluate(self, state: RunState) -> dict[str, Any]:
        stages = {name: evaluator.evaluate(state) for name, evaluator in self.evaluators.items()}
        return {"passed": all(stage.get("passed", False) for stage in stages.values()), "stages": stages}
