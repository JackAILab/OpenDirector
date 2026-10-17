from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from harness.agents.base import Agent
from harness.evaluators.base import Evaluator
from harness.tasks.base import Task
from harness.tools.registry import ToolRegistry
from harness.trajectory.recorder import TrajectoryRecorder

from .state import RunState
from .types import Observation, RunResult


def _generation_ids(observation: Observation) -> set[str]:
    """Read provider job IDs from a bounded Observation, including safe failure text."""
    found: set[str] = set()

    def visit(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
        elif key in {"generation_id", "generationId"} and isinstance(value, (str, int)):
            if str(value).strip():
                found.add(str(value).strip())

    visit(observation.content)
    if observation.error:
        found.update(re.findall(r"\bgeneration[_ ]?id\s*[:=]\s*([A-Za-z0-9_-]+)", observation.error, re.I))
    return found


class HarnessRunner:
    """Own the Agent → Tool → Observation loop and its durable trajectory."""

    def __init__(self, tools: ToolRegistry, *, recorder: TrajectoryRecorder | None = None) -> None:
        self.tools = tools
        self.recorder = recorder

    def run(self, *, task: Task, agent: Agent, evaluator: Evaluator | None = None, max_steps: int = 8) -> RunResult:
        state = RunState(
            run_id=uuid4().hex, task_id=task.task_id, objective=task.objective,
            inputs=dict(task.inputs), constraints=dict(task.constraints), metadata=dict(task.metadata),
        )
        status = "max_steps"
        paid_budget = task.constraints.get("paid_generation_budget")
        paid_calls_used = int(paid_budget.get("used", 0)) if isinstance(paid_budget, dict) else 0
        paid_call_limit = int(paid_budget.get("max_calls_without_confirmation", 0)) if isinstance(paid_budget, dict) else 0
        if isinstance(paid_budget, dict):
            state.metadata["paid_generation_budget"] = {
                "scope": paid_budget.get("scope", "case_or_segment"),
                "max_calls_without_confirmation": paid_call_limit,
                "used_at_start": paid_calls_used,
                "attempts_in_run": 0,
                "generation_ids_observed": 0,
                "automatic_retry": False,
                "model_substitution": False,
            }
        for _ in range(max_steps):
            action = agent.next_action(state)
            if action.kind == "finish":
                state.final = action.final or {}
                status = "completed"
                break
            if not action.tool_name:
                observation = Observation(ok=False, content={}, error="tool action omitted tool_name")
            else:
                tool = self.tools.get(action.tool_name)
                if tool and tool.paid and isinstance(paid_budget, dict):
                    if paid_call_limit < 1 or paid_calls_used >= paid_call_limit:
                        observation = Observation(
                            ok=False,
                            content={
                                "tool": action.tool_name, "layer": tool.layer,
                                "paid_generation_budget": {
                                    "used": paid_calls_used, "limit": paid_call_limit,
                                    "remaining": max(0, paid_call_limit - paid_calls_used),
                                },
                            },
                            error="paid generation budget exhausted; renewed human confirmation is required",
                        )
                    else:
                        paid_calls_used += 1
                        state.metadata["paid_generation_budget"]["attempts_in_run"] += 1
                        state.metadata["paid_generation_budget"]["used_after_attempt"] = paid_calls_used
                        observation = self.tools.execute(action.tool_name, action.arguments)
                        state.metadata["paid_generation_budget"]["generation_ids_observed"] += len(
                            _generation_ids(observation)
                        )
                elif tool and tool.paid and not task.constraints.get("paid_generation_authorized", False):
                    observation = Observation(
                        ok=False, content={"tool": action.tool_name, "layer": tool.layer},
                        error="paid tool requires an explicit paid_generation_budget or paid_generation_authorized=true",
                    )
                else:
                    observation = self.tools.execute(action.tool_name, action.arguments)
            state.record(action, observation)
            agent.observe(state, action, observation)
            if not observation.ok and not agent.can_recover(state, observation):
                state.final = {"error": state._safe_error(observation.error), "last_observation": observation.content}
                status = "failed"
                break
        else:
            state.final = {"steps": len(state.steps), "reason": "max_steps_reached"}
        if state.final is None:
            state.final = {"steps": len(state.steps)}
        evaluation = evaluator.evaluate(state) if evaluator and status == "completed" else None
        trajectory_path = self.recorder.write(state, status=status, evaluation=evaluation) if self.recorder else None
        return RunResult(
            run_id=state.run_id, status=status, final=state.final,
            trajectory_path=str(trajectory_path) if trajectory_path else None, evaluation=evaluation,
        )
