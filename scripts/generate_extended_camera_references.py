#!/usr/bin/env python3
"""Generate one non-overwriting GPT Image 2 boundary state for an extended live case."""

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
from harness.models import OpenAIImageModel
from harness.tasks import Task
from harness.tools import GPTImageTool, ToolRegistry
from harness.trajectory import TrajectoryRecorder
from harness.utils.config import load_json


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_id")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorize-paid-generation", action="store_true")
    args = parser.parse_args()

    config = load_json(resolve(args.config))
    matches = [state for state in config["states"] if state["id"] == args.state_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate state id: {args.state_id}")
    state = matches[0]
    references = [resolve(path) for path in config["reference_images"]]
    missing = [str(path) for path in references if not path.is_file()]
    if missing:
        raise FileNotFoundError("reference assets are required: " + ", ".join(missing))

    image_config = load_json(ROOT / "configs/models/gpt_image_2.json")
    env = image_config["environment"]
    registry = ToolRegistry()
    registry.register(GPTImageTool(OpenAIImageModel(
        model_env=env["model"], base_url_env=env["base_url"], api_key_env=env["api_key"],
        expected_model=config["image_model"],
    ), output_root=ROOT / "outputs/artifacts"))

    relative_output = Path(config["case_id"]) / "camera_references" / f"{state['id']}.png"
    action = AgentAction.tool("generate_image", {
        "prompt": state["prompt"],
        "output": str(relative_output),
        "operation": "edit",
        "reference_images": [str(path.resolve()) for path in references],
        "model": config["image_model"],
        "size": config["frame_size"],
        "quality": "high",
        "metadata": {
            "case_id": config["case_id"],
            "state_id": state["id"],
            "timeline_time": state["time"],
            "role": "extended_camera_reference",
            "human_review_required": True,
            "training_eligible": False,
        },
    }, rationale="Generate one independently reviewable extended boundary state with GPT Image 2; paid, non-overwriting, and never automatically retried.")
    finish = AgentAction.finish({
        "state_id": state["id"], "output": str(ROOT / "outputs/artifacts" / relative_output),
        "human_review": "pending", "training_eligible": False,
    })
    constraints = dict(config["constraints"])
    constraints["paid_generation_authorized"] = args.authorize_paid_generation
    task = Task(
        f"{config['case_id']}:{state['id']}",
        f"Generate extended camera reference {state['id']}",
        inputs={"config": str(resolve(args.config)), "references": [str(path) for path in references]},
        constraints=constraints,
        metadata={"model": config["image_model"], "state_id": state["id"], "timeline_time": state["time"]},
    )
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(ROOT / "outputs/trajectories")).run(
        task=task, agent=ScriptedAgent([action, finish]), max_steps=2,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.status == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
