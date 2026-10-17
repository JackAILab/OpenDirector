#!/usr/bin/env python3
"""Run a configured VisualAgent task through the standard harness loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner
from harness.evaluators import CompositeEvaluator, ImageArtifactEvaluator, RuleEvaluator, SceneRichnessEvaluator
from harness.models import OpenAIImageModel
from harness.tasks import Task
from harness.tools import GPTImageTool, ToolRegistry
from harness.trajectory import TrajectoryRecorder
from harness.utils.config import load_json


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def build_actions(task_config: dict) -> tuple[list[AgentAction], list[Path]]:
    prompt_set = load_json(_resolve(task_config["prompt_set"]))
    shared = prompt_set.get("shared_constraints", "")
    references = [str(_resolve(path)) for path in task_config.get("reference_images", [])]
    outputs: list[Path] = []
    actions: list[AgentAction] = []
    for variant in prompt_set["variants"]:
        relative_output = f"{task_config['output_dir']}/{variant['id']}.png"
        outputs.append(PROJECT_ROOT / "outputs/artifacts" / relative_output)
        actions.append(AgentAction.tool(
            "generate_image",
            {
                "prompt": variant["prompt"] + ("\n\nConstraints: " + shared if shared else ""),
                "output": relative_output, "reference_images": references,
                "model": task_config["model"], "size": task_config["size"],
                "quality": task_config["quality"],
                "metadata": {"task_id": task_config["task_id"], "variant_id": variant["id"]},
            },
            rationale="Produce an independently reviewable keyframe candidate with product-geometry reference.",
        ))
    actions.append(AgentAction.finish({"expected_outputs": [str(path) for path in outputs], "human_review": "pending"}))
    return actions, outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_config", type=Path)
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()
    task_config = load_json(_resolve(str(args.task_config)))
    model_config = load_json(PROJECT_ROOT / "configs/models/gpt_image_2.json")
    env = model_config["environment"]
    registry = ToolRegistry()
    registry.register(GPTImageTool(
        OpenAIImageModel(
            model_env=env["model"], base_url_env=env["base_url"], api_key_env=env["api_key"],
            expected_model=model_config["expected_model"],
        ),
        output_root=PROJECT_ROOT / "outputs/artifacts",
    ))
    actions, outputs = build_actions(task_config)
    quality_config = load_json(_resolve(task_config["quality_config"])) if task_config.get("quality_config") else {}
    technical = quality_config.get("technical", {})
    richness = quality_config.get("scene_richness", {})
    task = Task(
        task_id=task_config["task_id"], objective=task_config["objective"],
        inputs={"prompt_set": task_config["prompt_set"], "reference_images": task_config["reference_images"]},
        constraints=task_config["constraints"], metadata={"model": task_config["model"]},
    )
    evaluator = CompositeEvaluator({
        "execution": RuleEvaluator({
            "all_tools_succeeded": lambda state: bool(state.steps) and all(step["observation"]["ok"] for step in state.steps),
            "all_outputs_exist": lambda state: all(path.is_file() for path in outputs),
        }),
        "image_quality": ImageArtifactEvaluator(
            outputs, expected_model=task_config["model"],
            aspect_tolerance=float(technical.get("aspect_tolerance", 0.02)),
            min_mean_luma=float(technical.get("min_mean_luma", 92.0)),
            max_dark_pixel_ratio=float(technical.get("max_dark_pixel_ratio", 0.34)),
            min_pass_count=1,
        ),
        "scene_richness": SceneRichnessEvaluator(
            outputs, min_entropy=float(richness.get("min_entropy", 5.2)),
            min_edge_density=float(richness.get("min_edge_density", 0.08)),
            min_active_tiles=int(richness.get("min_active_tiles_3x3", 6)),
            min_luma_spread=float(richness.get("min_luma_stddev_spread", 34.0)),
            min_pass_count=1,
        ),
    })
    result = HarnessRunner(
        registry, recorder=TrajectoryRecorder(PROJECT_ROOT / "outputs/trajectories"),
    ).run(task=task, agent=ScriptedAgent(actions), evaluator=evaluator, max_steps=args.max_steps)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    if result.status != "completed":
        return 2
    if result.evaluation and result.evaluation.get("passed"):
        return 0
    # Generation completed, but deterministic or human-facing quality gates rejected the artifacts.
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
