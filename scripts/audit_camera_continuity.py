#!/usr/bin/env python3
"""Create a non-overwriting, deterministic continuity audit for an assembled camera feed."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from harness.evaluators.continuity import BoundaryContinuityPolicy, compare_frame_pair
from harness.renderers.common import ffmpeg_executable


def extract_frame(video: Path, timestamp: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run([
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.6f}",
        "-i", str(video), "-frames:v", "1", "-y", str(output),
    ], check=False, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(process.stderr[-1200:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--boundaries", default="7.5,15,22.5,30,37.5,45,52.5")
    parser.add_argument("--inspect-start", type=float, default=30.0)
    parser.add_argument("--inspect-end", type=float, default=34.0)
    parser.add_argument("--inspect-step", type=float, default=0.1)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite continuity audit: {args.output}")
    args.output.mkdir(parents=True)

    policy = BoundaryContinuityPolicy()
    boundary_results = []
    frame_interval = 1 / args.fps
    for boundary in [float(value) for value in args.boundaries.split(",") if value.strip()]:
        slug = f"{round(boundary * 10):04d}"
        before = args.output / f"boundary-{slug}-before.png"
        after = args.output / f"boundary-{slug}-after.png"
        extract_frame(args.video, boundary - frame_interval, before)
        extract_frame(args.video, boundary + frame_interval, after)
        metrics = compare_frame_pair(before, after)
        boundary_results.append({
            "time": boundary,
            "before": before.name,
            "after": after.name,
            "metrics": metrics,
            "status": policy.classify(metrics),
        })

    scan_results = []
    timestamp = args.inspect_start
    previous_time = timestamp
    previous = args.output / f"scan-{round(timestamp * 100):05d}.png"
    extract_frame(args.video, timestamp, previous)
    timestamp += args.inspect_step
    while timestamp <= args.inspect_end + 1e-9:
        current = args.output / f"scan-{round(timestamp * 100):05d}.png"
        extract_frame(args.video, timestamp, current)
        metrics = compare_frame_pair(previous, current)
        scan_results.append({
            "from": round(previous_time, 3), "to": round(timestamp, 3),
            "before": previous.name, "after": current.name,
            "metrics": metrics, "status": policy.classify(metrics),
        })
        previous, previous_time = current, timestamp
        timestamp += args.inspect_step

    ranked = sorted(scan_results, key=lambda item: item["metrics"]["full_ssim"])
    payload = {
        "schema": "visualagent.camera-continuity-audit.v2",
        "source": str(args.video),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "adjacent-frame global SSIM proxy plus normalized mean absolute difference; semantic review remains mandatory",
        "policy": {
            "pass_ssim": policy.pass_ssim, "review_ssim": policy.review_ssim, "fail_mad": policy.fail_mad,
        },
        "boundaries": boundary_results,
        "intrasegment_scan": {
            "start": args.inspect_start, "end": args.inspect_end, "step": args.inspect_step,
            "worst_candidates": ranked[:8],
        },
        "passed": all(item["status"] == "pass" for item in boundary_results),
        "training_eligible": False,
        "human_review": "pending",
    }
    (args.output / "audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
