#!/usr/bin/env python3
"""Submit exactly one non-overwriting paid Kling camera-segment job."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner
from harness.evaluators import CameraVideoEvaluator
from harness.models import KlingVideoModel
from harness.tasks import Task
from harness.tools import CameraVideoTool, ToolRegistry
from harness.trajectory import TrajectoryRecorder


def uuid7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    value = (timestamp_ms << 80) | (0x7 << 76) | (secrets.randbits(12) << 64) | (0b10 << 62) | secrets.randbits(62)
    return str(UUID(int=value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("segment_id")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks/jensen_rubin_live_30s_v2.segments.json")
    parser.add_argument("--authorize-paid-generation", action="store_true", help="legacy single-call authorization")
    parser.add_argument("--research-budget-limit", type=int, default=0)
    parser.add_argument("--research-budget-used", type=int, default=0)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    matches = [item for item in config["segments"] if item["id"] == args.segment_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate segment id: {args.segment_id}")
    segment = matches[0]
    output_root = ROOT / "outputs/artifacts"
    parameters = config.get("parameters", {})
    source_duration = int(config.get("source_duration_seconds", parameters.get("duration_seconds_per_segment", 15)))
    assembled_duration = int(config.get("assembled_duration_seconds", source_duration))
    aspect_ratio = config.get("aspect_ratio", parameters.get("aspect_ratio", "9:16"))
    resolution = config.get("resolution", parameters.get("resolution", "1080p"))
    enable_audio = bool(config.get("enable_audio", parameters.get("enable_audio", False)))
    prefer_multi_shots = bool(config.get("prefer_multi_shots", parameters.get("prefer_multi_shots", False)))
    first = segment.get("first", segment.get("first_frame"))
    tail = segment.get("tail", segment.get("last_frame"))
    if not first:
        raise ValueError(f"segment {args.segment_id} has no first frame")
    if segment.get("output"):
        declared_output = Path(segment["output"])
        prefix = Path("outputs/artifacts")
        try:
            relative_output = declared_output.relative_to(prefix)
        except ValueError as exc:
            raise ValueError("segment output must live below outputs/artifacts") from exc
    else:
        relative_output = Path(config["case_id"]) / "camera_segments" / f"{args.segment_id}.source-{source_duration}s.mp4"
    output = output_root / relative_output
    reference_images = [str(ROOT / first)]
    if tail:
        reference_images.append(str(ROOT / tail))
    input_mode = config.get("input_mode") or (
        "first_tail_boundary_images"
        if config["model"] == "kling-video-v3_0" and len(reference_images) == 2
        else "first_image_motion_preview"
        if config["model"] == "kling-video-v3_0"
        else "omni_single_reference"
        if len(reference_images) == 1
        else "omni_reference_images"
    )
    timeline_summary = config.get("timeline", config.get("objective", f"{segment['start']}-{segment['end']} camera interval"))
    trace_id = uuid7()
    registry = ToolRegistry()
    registry.register(CameraVideoTool(KlingVideoModel(executable="kling"), output_root=output_root))
    action = AgentAction.tool("generate_camera_video", {
        "prompt": segment["prompt"],
        "output": str(relative_output),
        "reference_images": reference_images,
        "model": config["model"],
        "duration_seconds": source_duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "image_count": 1,
        "prefer_multi_shots": prefer_multi_shots,
        "enable_audio": enable_audio,
        "task_trace_id": trace_id,
        "metadata": {
            "case_id": config["case_id"], "segment_id": segment["id"],
            "timeline_start": segment["start"], "timeline_end": segment["end"],
            "source_duration": source_duration,
            "planned_trim_out": assembled_duration,
            "audio_mode": "native_sync" if enable_audio else "disabled",
            **({"attempt": segment["attempt"]} if "attempt" in segment else {}),
            **({"retry_of_run": segment["retry_of_run"]} if segment.get("retry_of_run") else {}),
            "input_mode": input_mode,
            **({"format_contract": config["format_contract"]} if config.get("format_contract") else {}),
        },
    }, rationale=(
        "Generate one bounded neural camera segment between two approved GPT Image 2 states; "
        "all readable UI and effects remain code-owned."
        if len(reference_images) == 2
        else "Generate one bounded single-first-frame neural motion preview; this is not boundary-continuity proof, "
        "and all readable UI and effects remain code-owned."
    ))
    finish = AgentAction.finish({"segment": segment["id"], "source_video": str(output), "training_eligible": False})
    if args.research_budget_limit < 0 or args.research_budget_limit > 9:
        raise ValueError("R&D budget limit must be between 0 and 9")
    if args.research_budget_used < 0:
        raise ValueError("R&D budget used cannot be negative")
    constraints = {"automatic_retry": False, "model_substitution": False}
    if args.research_budget_limit:
        constraints["paid_generation_budget"] = {
            "scope": "case_or_segment",
            "max_calls_without_confirmation": args.research_budget_limit,
            "used": args.research_budget_used,
        }
    else:
        constraints["paid_generation_authorized"] = args.authorize_paid_generation
    task = Task(
        f"{config['case_id']}:{segment['id']}",
        f"Generate camera segment {segment['id']} between approved boundary states",
        inputs={
            "first": first,
            **({"tail": tail} if tail else {}),
            "timeline": timeline_summary,
        },
        constraints=constraints,
        metadata={
            "task_trace_id": trace_id, "model": config["model"], "segment_id": segment["id"],
            **({"attempt": segment["attempt"]} if "attempt" in segment else {}),
            **({"retry_of_run": segment["retry_of_run"]} if segment.get("retry_of_run") else {}),
            **({"format_contract": config["format_contract"]} if config.get("format_contract") else {}),
        },
    )
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(ROOT / "outputs/trajectories")).run(
        task=task, agent=ScriptedAgent([action, finish]),
        evaluator=CameraVideoEvaluator(
            output, expected_duration=source_duration,
            expected_resolution=(1080, 1920) if aspect_ratio == "9:16" else (1920, 1080),
            expected_audio=enable_audio,
        ),
        max_steps=2,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.status == "completed" and result.evaluation and result.evaluation.get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
