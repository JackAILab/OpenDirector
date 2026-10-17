#!/usr/bin/env python3
"""Print the recorded evaluation for a harness trajectory."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness.evaluators import CompositeEvaluator, ImageArtifactEvaluator, SceneRichnessEvaluator
from harness.core.state import RunState
from harness.utils.config import load_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectory", type=Path, nargs="?")
    parser.add_argument("--task-config", type=Path)
    args = parser.parse_args()
    if args.task_config:
        config_path = args.task_config if args.task_config.is_absolute() else PROJECT_ROOT / args.task_config
        config = load_json(config_path)
        prompt_set = load_json(PROJECT_ROOT / config["prompt_set"])
        quality = load_json(PROJECT_ROOT / config["quality_config"]) if config.get("quality_config") else {}
        technical = quality.get("technical", {})
        richness = quality.get("scene_richness", {})
        outputs = [
            PROJECT_ROOT / "outputs/artifacts" / config["output_dir"] / f"{item['id']}.png"
            for item in prompt_set["variants"]
        ]
        state = RunState(
            run_id="evaluation-only", task_id=config["task_id"], objective=config["objective"],
            inputs={}, constraints=config["constraints"],
        )
        evaluation = CompositeEvaluator({
            "image_quality": ImageArtifactEvaluator(
                outputs, expected_model=config["model"],
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
        }).evaluate(state)
        target = PROJECT_ROOT / "outputs/results" / f"{config['task_id']}.evaluation.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"evaluation": evaluation, "report": str(target)}, ensure_ascii=False, indent=2))
        return 0 if evaluation.get("passed") else 3
    if not args.trajectory:
        parser.error("trajectory or --task-config is required")
    payload = json.loads(args.trajectory.read_text(encoding="utf-8"))
    print(json.dumps(payload.get("evaluation"), ensure_ascii=False, indent=2))
    return 0 if payload.get("evaluation", {}).get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
