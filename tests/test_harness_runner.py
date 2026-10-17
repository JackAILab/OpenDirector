import json
from pathlib import Path

from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner, Observation
from harness.evaluators import CompositeEvaluator, RuleEvaluator
from harness.tasks import Task
from harness.tools import Tool, ToolRegistry
from harness.trajectory import TrajectoryRecorder, load_trajectory


class EchoTool(Tool):
    name = "echo"

    def invoke(self, arguments):
        return Observation(ok=True, content={"value": arguments["value"]})


class PaidTool(Tool):
    name = "paid"
    paid = True
    layer = "camera"

    def invoke(self, arguments):
        raise AssertionError("paid tool must not execute without task authorization")


class CountingPaidTool(Tool):
    name = "counting_paid"
    paid = True
    layer = "camera"

    def __init__(self):
        self.calls = 0

    def invoke(self, arguments):
        self.calls += 1
        return Observation(ok=True, content={"call": self.calls, "generation_id": f"g-{self.calls}"})


class SubmittedThenFailedPaidTool(Tool):
    name = "submitted_then_failed"
    paid = True
    layer = "camera"

    def invoke(self, arguments):
        raise RuntimeError("provider generation_id=job_failed_1 ended with status FAIL")


def test_runner_records_and_evaluates(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = ScriptedAgent([AgentAction.tool("echo", {"value": 7}), AgentAction.finish({"answer": 7})])
    evaluator = RuleEvaluator({"one_step": lambda state: len(state.steps) == 1})
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task("echo-task", "echo a value"), agent=agent, evaluator=evaluator, max_steps=2,
    )
    assert result.status == "completed"
    assert result.evaluation == {"passed": True, "checks": {"one_step": True}}
    payload = load_trajectory(Path(result.trajectory_path))
    assert payload["status"] == "completed"
    assert payload["steps"][0]["observation"]["content"]["value"] == 7
    assert payload["training_eligible"] is False


def test_unknown_tool_fails_without_crashing_registry():
    observation = ToolRegistry().execute("missing", {})
    assert not observation.ok
    assert observation.error == "unknown tool: missing"


def test_composite_evaluator_requires_every_stage():
    state = type("State", (), {"steps": []})()
    evaluation = CompositeEvaluator({
        "pass": RuleEvaluator({"yes": lambda _: True}),
        "fail": RuleEvaluator({"no": lambda _: False}),
    }).evaluate(state)
    assert evaluation["passed"] is False


def test_max_steps_is_explicit(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task("loop", "keep going"),
        agent=ScriptedAgent([AgentAction.tool("echo", {"value": 1})]),
        max_steps=1,
    )
    assert result.status == "max_steps"
    assert result.final["reason"] == "max_steps_reached"
    assert load_trajectory(Path(result.trajectory_path))["status"] == "max_steps"


def test_failed_execution_does_not_receive_quality_evaluation(tmp_path: Path):
    evaluator = RuleEvaluator({"must_not_run": lambda _: (_ for _ in ()).throw(AssertionError())})
    result = HarnessRunner(ToolRegistry(), recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task("fail", "unknown tool"),
        agent=ScriptedAgent([AgentAction.tool("missing", {})]),
        evaluator=evaluator,
        max_steps=1,
    )
    assert result.status == "failed"
    assert result.evaluation is None


def test_runner_blocks_paid_tool_without_explicit_task_authorization():
    registry = ToolRegistry()
    registry.register(PaidTool())
    result = HarnessRunner(registry).run(
        task=Task("paid", "generate", constraints={"paid_generation_authorized": False}),
        agent=ScriptedAgent([AgentAction.tool("paid", {})]), max_steps=1,
    )
    assert result.status == "failed"
    assert "paid_generation_authorized" in result.final["error"]


def test_research_budget_allows_three_paid_calls_and_blocks_fourth(tmp_path: Path):
    tool = CountingPaidTool()
    registry = ToolRegistry()
    registry.register(tool)
    actions = [AgentAction.tool("counting_paid", {}) for _ in range(4)]
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task(
            "research-three", "bounded paid research",
            constraints={"paid_generation_budget": {
                "scope": "case_or_segment", "max_calls_without_confirmation": 3, "used": 0,
            }},
        ),
        agent=ScriptedAgent(actions), max_steps=4,
    )
    assert result.status == "failed"
    assert tool.calls == 3
    assert "budget exhausted" in result.final["error"]
    payload = load_trajectory(Path(result.trajectory_path))
    budget = payload["metadata"]["paid_generation_budget"]
    assert budget["attempts_in_run"] == 3
    assert budget["generation_ids_observed"] == 3
    assert payload["steps"][-1]["observation"]["content"]["paid_generation_budget"]["remaining"] == 0


def test_non_paid_actions_do_not_consume_research_budget(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task(
            "research-free", "free work",
            constraints={"paid_generation_budget": {
                "scope": "case_or_segment", "max_calls_without_confirmation": 3, "used": 2,
            }},
        ),
        agent=ScriptedAgent([AgentAction.tool("echo", {"value": 1}), AgentAction.finish({})]),
        max_steps=2,
    )
    assert result.status == "completed"
    budget = load_trajectory(Path(result.trajectory_path))["metadata"]["paid_generation_budget"]
    assert budget["attempts_in_run"] == 0
    assert budget["used_at_start"] == 2


def test_failed_paid_job_still_records_observed_generation_id(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(SubmittedThenFailedPaidTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task(
            "submitted-failure", "record provider job before terminal failure",
            constraints={"paid_generation_budget": {
                "scope": "case_or_segment", "max_calls_without_confirmation": 3, "used": 0,
            }},
        ),
        agent=ScriptedAgent([AgentAction.tool("submitted_then_failed", {})]), max_steps=1,
    )
    budget = load_trajectory(Path(result.trajectory_path))["metadata"]["paid_generation_budget"]
    assert result.status == "failed"
    assert budget["attempts_in_run"] == 1
    assert budget["generation_ids_observed"] == 1


def test_trajectory_redacts_prompts_and_credentials(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task("safe", "safe trajectory"),
        agent=ScriptedAgent([
            AgentAction.tool("echo", {"value": 1, "prompt": "secret creative prompt", "api_key": "nope"}),
            AgentAction.finish({}),
        ]), max_steps=2,
    )
    payload = load_trajectory(Path(result.trajectory_path))
    arguments = payload["steps"][0]["action"]["arguments"]
    assert arguments["api_key"] == "<redacted>"
    assert "secret creative prompt" not in json.dumps(payload)


def test_trajectory_redacts_temporary_urls_from_tool_errors(tmp_path: Path):
    class FailingTool(Tool):
        name = "failing"

        def invoke(self, arguments):
            raise RuntimeError("upload failed at https://provider.example/file?signature=secret")

    registry = ToolRegistry()
    registry.register(FailingTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task("redact", "redact provider URL"),
        agent=ScriptedAgent([AgentAction.tool("failing", {})]), max_steps=1,
    )
    payload = load_trajectory(Path(result.trajectory_path))
    serialized = json.dumps(payload)
    assert "provider.example" not in serialized
    assert "<temporary-url-redacted>" in serialized
