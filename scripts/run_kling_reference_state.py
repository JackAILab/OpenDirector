#!/usr/bin/env python3
"""Submit exactly one non-overwriting paid Kling reference-state job."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner
from harness.evaluators.image import ImageArtifactEvaluator
from harness.models import KlingImageModel
from harness.tasks import Task
from harness.tools import GPTImageTool, ToolRegistry
from harness.trajectory import TrajectoryRecorder


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_id")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks/cybercab_live_60s_v1.generation.json")
    parser.add_argument("--budget-limit", type=int, required=True)
    parser.add_argument("--budget-used", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.budget_limit <= 9 or not 0 <= args.budget_used < args.budget_limit:
        raise ValueError("paid budget must authorize this one call within the 9-call case limit")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    state = next(item for item in config["reference_states"] if item["id"] == args.state_id)
    output_root = ROOT / "outputs/artifacts"
    relative_output = Path(config["case_id"]) / "reference_states" / f"{state['id']}.png"
    output = output_root / relative_output
    registry = ToolRegistry()
    registry.register(GPTImageTool(
        KlingImageModel(executable="kling"), output_root=output_root,
    ))
    action = AgentAction.tool("generate_image", {
        "prompt": state["prompt"], "output": str(relative_output),
        "reference_images": [str(ROOT / value) for value in state["references"]],
        "model": config["image_model"], "operation": "image_to_image",
        "size": "1152x2048", "quality": "high",
        "metadata": {"case_id": config["case_id"], "state_id": state["id"],
                     "task_trace_id": config["task_trace_id"], "training_eligible": False},
    }, rationale="Generate one neural physical-scene boundary state; all readable UI remains code-owned.")
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(ROOT / "outputs/trajectories")).run(
        task=Task(
            f"{config['case_id']}:{state['id']}", f"Generate boundary state {state['id']}",
            constraints={"paid_generation_budget": {"scope": "cybercab_live_60s_v1", "max_calls_without_confirmation": args.budget_limit, "used": args.budget_used},
                         "automatic_retry": False, "model_substitution": False},
            metadata={"task_trace_id": config["task_trace_id"], "training_eligible": False},
        ),
        agent=ScriptedAgent([action, AgentAction.finish({"artifact": str(output), "training_eligible": False})]),
        evaluator=ImageArtifactEvaluator([output], expected_model=config["image_model"], min_mean_luma=45.0, max_dark_pixel_ratio=0.65),
        max_steps=2,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.status == "completed" and result.evaluation and result.evaluation.get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
