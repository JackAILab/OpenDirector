#!/usr/bin/env python3
"""Build differentiated timelines and reference-image plans for the authorized batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harness.live import LiveProductionTimeline

ROOT = Path(__file__).resolve().parents[1]


def write_new(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite batch artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def timeline_for(case: dict, disclosure: str) -> dict:
    comments = case["comments"]
    return {
        "schema": "visualagent.live-production-timeline.v1",
        "duration": 15.0,
        "disclosure": disclosure,
        "scene": {
            "description": case["scene"],
            "subject": "Jensen Huang synthetic dramatization",
            "product": "RTX 5090 Founders Edition",
            "topic": case["topic"],
        },
        "ui_template": {"host_label": "Jensen AI Demo", "template": "vertical_live_v1"},
        "layout": {"safe_areas": [
            {"id": "comments", "instruction": "keep face and GPU details away from the lower-left comment zone"},
            {"id": "actions", "instruction": "keep essential subject details away from the right action rail"},
            {"id": "product", "instruction": "keep the lower-right product-card region calm but not empty"},
        ]},
        "tracks": {
            "camera": [
                {"id": "cam_intro", "start": 0.0, "end": 4.0, "action": "The synthetic host looks into camera, speaks naturally, and holds one RTX 5090 vertically at chest height with stable dual-fan geometry.", "model_owned": True},
                {"id": "cam_response", "start": 4.0, "end": 9.5, "action": case["response_cue"] + " while keeping the same GPU stable and visible.", "responds_to": "comment_question", "model_owned": True},
                {"id": "cam_close", "start": 9.5, "end": 15.0, "action": "The host returns attention to camera, presents the same GPU without changing its geometry, and gives one calm closing nod.", "model_owned": True},
            ],
            "speech": [
                {"id": "speech_intro", "start": 0.4, "end": 3.8, "text": case["speech"][0]},
                {"id": "speech_response", "start": 4.6, "end": 9.0, "text": case["speech"][1], "responds_to": "comment_question"},
                {"id": "speech_close", "start": 9.8, "end": 14.5, "text": case["speech"][2]},
            ],
            "comments": [
                {"id": "comment_hype", "time": 1.2, "duration": 4.0, "username": "frame_chaser", "avatar_id": 3, "text": comments[0], "model_owned": False},
                {"id": "comment_question", "time": 3.4, "duration": 5.0, "username": "pc_master88", "avatar_id": 12, "text": comments[1], "model_owned": False},
                {"id": "comment_followup", "time": 7.3, "duration": 5.0, "username": "thermal_lab", "avatar_id": 18, "text": comments[2], "model_owned": False},
                {"id": "comment_close", "time": 11.0, "duration": 4.0, "username": "small_case", "avatar_id": 21, "text": comments[3], "model_owned": False},
            ],
            "ui": [
                {"id": "ui_state_0", "time": 0.0, "state": {"viewer_count": 126700, "likes": 284900}, "model_owned": False},
                {"id": "ui_state_1", "time": 6.0, "state": {"viewer_count": 127300, "likes": 286400}, "model_owned": False},
                {"id": "ui_product", "type": "product_card", "start": 8.8, "end": 14.2, "title": "RTX 5090 展示", "subtitle": case["topic"] + " · 请核对官方信息", "model_owned": False},
            ],
            "vfx": [
                {"id": "vfx_hearts", "type": case["vfx"][0], "start": 5.5, "end": 8.2, "caused_by": "speech_response", "model_owned": False},
                {"id": "vfx_rocket", "type": case["vfx"][1], "start": 10.6, "end": 12.5, "caused_by": "cam_close", "model_owned": False},
            ],
            "ar": [], "subtitles": [],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=ROOT / "configs/batches/jensen_rtx5090_live_batch10.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/artifacts/jensen_rtx5090_live_batch10_20260820")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    cases = spec["cases"]
    if len(cases) != spec["submission_cap"] or len(cases) != 10:
        raise ValueError("authorized batch must contain exactly ten cases")
    seen = set()
    plan_cases = []
    for index, case in enumerate(cases, start=1):
        if case["id"] in seen:
            raise ValueError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
        case_root = args.output_root / case["id"]
        timeline = timeline_for(case, spec["disclosure"])
        LiveProductionTimeline.from_dict(timeline)
        timeline_path = case_root / "timeline.json"
        write_new(timeline_path, timeline)
        plan_cases.append({
            "attempt_number": index, "id": case["id"], "topic": case["topic"],
            "timeline": str(timeline_path),
            "timeline_sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest(),
            "first_reference": str(case_root / "camera_references/first.png"),
            "tail_reference": str(case_root / "camera_references/tail.png"),
            "camera_output": str(case_root / "camera/camera_feed.mp4"),
            "audio_output": str(case_root / "audio/speech.wav"),
            "ui_output": str(case_root / "overlays/live_ui.webm"),
            "vfx_output": str(case_root / "overlays/vfx.webm"),
            "final_output": str(case_root / "final/final_livestream.mp4"),
        })
    write_new(args.output_root / "batch_plan.json", {
        "schema": "visualagent.live-batch-plan.v1", "batch_id": spec["batch_id"],
        "submission_cap": 10, "max_credits_per_submission": 120,
        "max_total_credits": 1200, "training_eligible": False,
        "human_review": "pending", "cases": plan_cases,
    })
    write_new(args.output_root / "kling_submission_ledger.json", {
        "schema": "visualagent.kling-batch-ledger.v1", "batch_id": spec["batch_id"],
        "submission_cap": 10, "attempt_count": 0, "attempts": [],
        "raw_provider_payload_stored": False, "temporary_urls_stored": False,
        "training_eligible": False,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
