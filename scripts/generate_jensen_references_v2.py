#!/usr/bin/env python3
"""Generate GPT Image 2 reference elements and frames through the harness.

The two stages are intentionally separate so a human can review the independent
host, product and set elements before any compositing spend.
"""

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


def action(prompt: str, output: str, *, model: str, size: str, role: str, references: list[Path] | None = None) -> AgentAction:
    refs = references or []
    return AgentAction.tool(
        "generate_image",
        {
            "prompt": prompt,
            "output": output,
            "operation": "edit" if refs else "generate",
            "reference_images": [str(path.resolve()) for path in refs],
            "model": model,
            "size": size,
            "quality": "high",
            "metadata": {
                "role": role,
                "synthetic_public_figure": role == "host_element" or role.startswith("camera_reference_"),
                "human_review_required": True,
                "training_eligible": False,
            },
        },
        rationale=f"Generate independently reviewable {role} with GPT Image 2; paid, non-overwriting, and never automatically retried.",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks/jensen_rtx5090_reference_v2.json")
    parser.add_argument("--stage", choices=("elements", "first-frame", "first-frame-repair", "state-075", "state-150", "state-150-repair", "state-150-regenerate", "state-225", "state-300", "state-075-dynamic-v2", "state-150-dynamic-v2", "state-225-dynamic-v2", "state-300-dynamic-v2", "tail-frame"), required=True)
    parser.add_argument("--authorize-paid-generation", action="store_true")
    args = parser.parse_args()

    config = load_json(resolve(args.config))
    output_root = ROOT / "outputs/artifacts"
    relative = Path(config["output_dir"])
    run_root = output_root / relative
    prompts = config["prompts"]

    image_config = load_json(ROOT / "configs/models/gpt_image_2.json")
    env = image_config["environment"]
    registry = ToolRegistry()
    registry.register(GPTImageTool(OpenAIImageModel(
        model_env=env["model"], base_url_env=env["base_url"], api_key_env=env["api_key"],
        expected_model=config["image_model"],
    ), output_root=output_root))

    host = run_root / "reference_elements/host.png"
    gpu = run_root / "reference_elements/gpu.png"
    studio = run_root / "reference_elements/studio.png"
    first = run_root / "camera_references/first.png"
    first_v2 = run_root / "camera_references/first-v2.png"
    state_075 = run_root / "camera_references/state-075.png"
    state_150 = run_root / "camera_references/state-150.png"
    state_150_v2 = run_root / "camera_references/state-150-v2.png"
    state_150_v3 = run_root / "camera_references/state-150-v3.png"
    state_150_v5 = run_root / "camera_references/state-150-v5.png"
    state_225 = run_root / "camera_references/state-225.png"
    tail = run_root / "camera_references/tail.png"

    if args.stage == "elements":
        actions = [
            action(prompts["host_element"], str(relative / "reference_elements/host.png"), model=config["image_model"], size=config["element_size"], role="host_element"),
            action(prompts["gpu_element"], str(relative / "reference_elements/gpu.png"), model=config["image_model"], size=config["element_size"], role="gpu_element"),
            action(prompts["set_element"], str(relative / "reference_elements/studio.png"), model=config["image_model"], size=config["frame_size"], role="studio_element"),
            AgentAction.finish({"stage": "elements", "human_review": "required_before_frames", "training_eligible": False}),
        ]
    elif args.stage == "first-frame":
        missing = [str(path) for path in (host, gpu, studio) if not path.is_file()]
        if missing:
            raise FileNotFoundError("reference elements must be generated and approved first: " + ", ".join(missing))
        actions = [
            action(prompts["first_frame"], str(relative / "camera_references/first.png"), model=config["image_model"], size=config["frame_size"], role="camera_reference_first", references=[host, gpu, studio]),
            AgentAction.finish({"stage": "first-frame", "human_review": "required_before_tail_frame", "training_eligible": False}),
        ]
    elif args.stage == "first-frame-repair":
        missing = [str(path) for path in (first, host, gpu, studio) if not path.is_file()]
        if missing:
            raise FileNotFoundError("first frame and reference elements are required for lighting repair: " + ", ".join(missing))
        actions = [
            action(prompts["first_frame_lighting_repair"], str(relative / "camera_references/first-v2.png"), model=config["image_model"], size=config["frame_size"], role="camera_reference_first_lighting_repair", references=[first, host, gpu, studio]),
            AgentAction.finish({"stage": "first-frame-repair", "human_review": "required_before_tail_frame", "training_eligible": False}),
        ]
    elif args.stage == "state-150-regenerate":
        required = [state_075, host, gpu, studio]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("7.5-second state and references are required: " + ", ".join(missing))
        actions = [
            action(prompts["state_150_regenerate"], str(relative / "camera_references/state-150-v3.png"), model=config["image_model"], size=config["frame_size"], role="camera_reference_state_150_regenerate", references=[state_075, host, gpu, studio]),
            AgentAction.finish({"stage": args.stage, "human_review": "required_before_next_state", "training_eligible": False}),
        ]
    elif args.stage == "state-150-repair":
        required = [state_150, host, gpu, studio]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("15-second state and references are required: " + ", ".join(missing))
        actions = [
            action(prompts["state_150_lighting_repair"], str(relative / "camera_references/state-150-v2.png"), model=config["image_model"], size=config["frame_size"], role="camera_reference_state_150_lighting_repair", references=[state_150, host, gpu, studio]),
            AgentAction.finish({"stage": args.stage, "human_review": "required_before_next_state", "training_eligible": False}),
        ]
    elif args.stage in {"state-075-dynamic-v2", "state-150-dynamic-v2", "state-225-dynamic-v2", "state-300-dynamic-v2"}:
        prompt_key = args.stage.replace("-", "_")
        required = [first_v2, host, gpu, studio]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("approved opening state and references are required: " + ", ".join(missing))
        actions = [
            action(prompts[prompt_key], str(relative / f"camera_references/{args.stage}.png"), model=config["image_model"], size=config["frame_size"], role=f"camera_reference_{prompt_key}", references=required),
            AgentAction.finish({"stage": args.stage, "human_review": "required_before_segment_config", "training_eligible": False}),
        ]
    elif args.stage in {"state-075", "state-150", "state-225", "state-300"}:
        state_plan = {
            "state-075": (first_v2, "state_075", "state-075.png", [host, gpu]),
            "state-150": (state_075, "state_150", "state-150.png", [host, gpu, studio]),
            "state-225": (state_150_v5 if state_150_v5.is_file() else (state_150_v3 if state_150_v3.is_file() else (state_150_v2 if state_150_v2.is_file() else state_150)), "state_225", "state-225.png", [host, gpu]),
            "state-300": (state_225, "state_300", "state-300.png", [host, gpu]),
        }
        source, prompt_key, filename, supporting = state_plan[args.stage]
        required = [source, *supporting]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("previous approved state and references are required: " + ", ".join(missing))
        actions = [
            action(prompts[prompt_key], str(relative / f"camera_references/{filename}"), model=config["image_model"], size=config["frame_size"], role=f"camera_reference_{prompt_key}", references=[source, *supporting]),
            AgentAction.finish({"stage": args.stage, "human_review": "required_before_next_state", "training_eligible": False}),
        ]
    else:
        approved_first = first_v2 if first_v2.is_file() else first
        missing = [str(path) for path in (approved_first, host, gpu) if not path.is_file()]
        if missing:
            raise FileNotFoundError("first frame and reference elements must be generated and approved first: " + ", ".join(missing))
        actions = [
            action(prompts["tail_frame"], str(relative / "camera_references/tail.png"), model=config["image_model"], size=config["frame_size"], role="camera_reference_tail", references=[approved_first, host, gpu]),
            AgentAction.finish({"stage": "tail-frame", "human_review": "required_before_kling", "training_eligible": False}),
        ]

    constraints = dict(config["constraints"])
    constraints["paid_generation_authorized"] = args.authorize_paid_generation
    task = Task(
        f"{config['task_id']}_{args.stage}",
        config["objective"],
        inputs={"config": str(resolve(args.config)), "stage": args.stage},
        constraints=constraints,
        metadata={
            "model": config["image_model"],
            "output_dir": config["output_dir"],
            "pipeline": "reference_elements_then_first_tail_frames",
        },
    )
    result = HarnessRunner(
        registry, recorder=TrajectoryRecorder(ROOT / "outputs/trajectories")
    ).run(task=task, agent=ScriptedAgent(actions), max_steps=len(actions))
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.status == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
