#!/usr/bin/env python3
"""Run one layered live-production task through bounded harness tools."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from uuid import UUID
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner
from harness.evaluators import CameraVideoEvaluator, CompositeEvaluator, OverlayEvaluator, TimelineNarrativeEvaluator
from harness.live import LiveProductionTimeline, compile_camera_prompt
from harness.models import KlingVideoModel, OpenAIImageModel
from harness.tasks import Task
from harness.tools import (
    CameraVideoTool, ComposeVideoTool, GPTImageTool, InspectKeyframesTool, RenderAudioTool,
    RenderHyperFramesLayerTool, RenderLiveOverlayTool, RenderVFXTool, ToolRegistry,
)
from harness.trajectory import TrajectoryRecorder
from harness.utils.config import load_json


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def uuid7() -> str:
    """Return an RFC 9562 UUIDv7 for provider task trace correlation."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (secrets.randbits(12) << 64)
        | (0b10 << 62)
        | secrets.randbits(62)
    )
    return str(UUID(int=value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_config", type=Path)
    parser.add_argument("--resume-from-first", type=Path)
    parser.add_argument("--resume-from-tail", type=Path)
    parser.add_argument("--supersedes-trajectory", type=Path)
    parser.add_argument(
        "--authorize-paid-generation",
        action="store_true",
        help="Explicitly authorize this invocation to submit paid generation calls.",
    )
    args = parser.parse_args()
    config = load_json(resolve(str(args.task_config)))
    timeline_path = resolve(config["timeline"])
    timeline = LiveProductionTimeline.from_dict(load_json(timeline_path))
    font_path = resolve(config["font_path"]) if config.get("font_path") else None
    if font_path and not font_path.is_file():
        raise FileNotFoundError(f"configured UI font is missing: {font_path}")
    output_root = PROJECT_ROOT / "outputs/artifacts"
    relative = Path(config["output_dir"])
    run_root = output_root / relative
    if run_root.exists() and not args.resume_from_first:
        raise FileExistsError(f"refusing to overwrite live-production run: {run_root}")
    first = args.resume_from_first.resolve() if args.resume_from_first else run_root / "camera_references/first.png"
    tail = args.resume_from_tail.resolve() if args.resume_from_tail else run_root / "camera_references/tail.png"
    camera = run_root / "camera/camera_feed.mp4"
    audio = run_root / "audio/speech.wav"
    ui = run_root / "overlays/live_ui.webm"
    vfx = run_root / "overlays/vfx.webm"
    final = run_root / "final/final_livestream.mp4"
    image_config = load_json(PROJECT_ROOT / "configs/models/gpt_image_2.json")
    env = image_config["environment"]
    registry = ToolRegistry()
    registry.register(GPTImageTool(OpenAIImageModel(
        model_env=env["model"], base_url_env=env["base_url"], api_key_env=env["api_key"],
        expected_model=config["image_model"],
    ), output_root=output_root))
    registry.register(InspectKeyframesTool())
    registry.register(CameraVideoTool(KlingVideoModel(), output_root=output_root))
    registry.register(RenderAudioTool(output_root=output_root))
    registry.register(RenderLiveOverlayTool(output_root=output_root))
    registry.register(RenderVFXTool(output_root=output_root))
    registry.register(RenderHyperFramesLayerTool(output_root=output_root))
    registry.register(ComposeVideoTool(output_root=output_root))
    trace_id = uuid7()
    common_scene = (
        "Photorealistic high-density vertical PC-hardware livestream camera reference. A clearly synthetic "
        "dramatization of Jensen Huang in a black leather jacket, natural five-finger hands, presenting one "
        "RTX 5090 Founders Edition with stable dual-fan geometry. Rich commercial studio: active open PC, "
        "light-oak desk, tools, product packaging silhouette, layered GPU shelving, acoustic panels, emerald "
        "and cyan practical lights, distinct foreground/midground/background, at least five coherent non-text "
        "visual anchors across at least six grid regions. Keep only compact calm overlay zones. No text, letters, "
        "numbers, UI, comments, price, product card, caption, logo, watermark, extra fingers, duplicate GPU, "
        "third fan, sparse background, dark underexposure, or endorsement implication."
    )
    first_prompt = common_scene + " Medium shot, direct eye contact, GPU held vertically at chest height, stable tripod framing."
    tail_prompt = common_scene + " Preserve the exact identity, clothing, studio and GPU from image 1. Closing pose: GPU slightly angled to show dual-fan structure, confident nod, same tripod framing."
    camera_prompt = compile_camera_prompt(timeline)
    keyframe_gate = {
        "expected_model": config["image_model"],
        **dict(config.get("keyframe_quality_gate", {})),
    }
    if config["video_model"] == "kling-video-v3_0_omni":
        camera_prompt = (
            "图片1是第0秒人物、商品、布景和构图状态参考；图片2是第15秒同一人物、同一商品、"
            "同一布景的收尾状态参考。请生成两种状态之间连续自然的单镜头过程。\n"
            + camera_prompt
        )
    full_actions = [
        AgentAction.tool("render_audio", {"timeline": str(timeline_path), "output": str(relative / "audio/speech.wav"), "voice": "zh-CN-YunxiNeural", "rate": "+12%"}, rationale="Build non-cloned audio-first speech track."),
        AgentAction.tool("generate_image", {"prompt": first_prompt, "output": str(relative / "camera_references/first.png"), "operation": "generate", "model": config["image_model"], "size": config["image_size"], "quality": config["image_quality"], "metadata": {"role": "camera_reference_first", "synthetic_public_figure": True}}, rationale="Generate first clean camera reference; paid and non-overwriting."),
        AgentAction.tool("inspect_keyframes", {"paths": [str(first)], **keyframe_gate}, rationale="Stop before further paid calls if first reference fails deterministic gates."),
        AgentAction.tool("generate_image", {"prompt": tail_prompt, "output": str(relative / "camera_references/tail.png"), "operation": "edit", "reference_images": [str(first)], "model": config["image_model"], "size": config["image_size"], "quality": config["image_quality"], "metadata": {"role": "camera_reference_tail", "synthetic_public_figure": True}}, rationale="Generate continuity-preserving tail reference after first gate."),
        AgentAction.tool("inspect_keyframes", {"paths": [str(first), str(tail)], **keyframe_gate}, rationale="Require both references to pass before video spend."),
        AgentAction.tool("generate_camera_video", {"prompt": camera_prompt, "output": str(relative / "camera/camera_feed.mp4"), "reference_images": [str(first), str(tail)], "model": config["video_model"], "duration_seconds": config["duration_seconds"], "aspect_ratio": config["aspect_ratio"], "resolution": config["resolution"], "image_count": 1, "prefer_multi_shots": False, "enable_audio": False, "task_trace_id": trace_id, "metadata": {"input_mode": "explicit_first_tail" if config["video_model"] == "kling-video-v3_0" else "omni_two_image_reference", "strict_first_tail_api": config["video_model"] == "kling-video-v3_0", "expected_credits": config["expected_kling_credits"]}}, rationale="Generate only the neural camera feed; comments and VFX remain outside the model."),
        AgentAction.tool("render_hyperframes_layer", {"timeline": str(timeline_path), "project": str(PROJECT_ROOT / "productions/jensen_rtx5090_live_v1"), "layer_mode": "ui", "output": str(relative / "overlays/live_ui.webm"), "fps": config["fps"], "quality": "high", "workers": 4}, rationale="Render professional static UI, stateful counters and causally timed comments as a transparent deterministic layer."),
        AgentAction.tool("render_hyperframes_layer", {"timeline": str(timeline_path), "project": str(PROJECT_ROOT / "productions/jensen_rtx5090_live_v1"), "layer_mode": "vfx", "output": str(relative / "overlays/vfx.webm"), "fps": config["fps"], "quality": "high", "workers": 4}, rationale="Render authored SVG hearts and rocket on an independent transparent effect layer."),
        AgentAction.tool("compose_video", {"camera_video": str(camera), "ui_overlay": str(ui), "vfx_overlay": str(vfx), "audio": str(audio), "output": str(relative / "final/final_livestream.mp4"), "width": 1080, "height": 1920, "fps": config["fps"]}, rationale="Composite independent camera, audio, UI and VFX artifacts."),
        AgentAction.finish({"final_video": str(final), "human_review": "pending", "training_eligible": False}),
    ]
    if args.resume_from_first and args.resume_from_tail:
        actions = [full_actions[4], *full_actions[5:]]
    elif args.resume_from_first:
        actions = [full_actions[2], *full_actions[3:]]
    else:
        actions = full_actions
    constraints = dict(config["constraints"])
    constraints["paid_generation_authorized"] = args.authorize_paid_generation
    task = Task(config["task_id"], config["objective"], inputs={
        "timeline": config["timeline"], "resume_from_first": str(first) if args.resume_from_first else None,
        "resume_from_tail": str(tail) if args.resume_from_tail else None,
    }, constraints=constraints, metadata={
        "task_trace_id": trace_id, "models": {"image": config["image_model"], "video": config["video_model"]},
        "supersedes_trajectory": str(args.supersedes_trajectory.resolve()) if args.supersedes_trajectory else None,
        "repair_scope": "technical_keyframe_then_resume" if args.resume_from_first else None,
    })
    evaluator = CompositeEvaluator({
        "camera": CameraVideoEvaluator(camera, expected_duration=timeline.duration, expected_resolution=(1080, 1920)),
        "ui": OverlayEvaluator(ui.with_suffix(".manifest.json"), expected_comments=len(timeline.tracks["comments"])),
        "vfx": OverlayEvaluator(vfx.with_suffix(".manifest.json"), expected_comments=0, expected_vfx=len(timeline.tracks["vfx"])),
        "narrative": TimelineNarrativeEvaluator(timeline),
    })
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(PROJECT_ROOT / "outputs/trajectories")).run(task=task, agent=ScriptedAgent(actions), evaluator=evaluator, max_steps=len(actions))
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.status == "completed" and result.evaluation and result.evaluation.get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
