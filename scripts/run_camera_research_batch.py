#!/usr/bin/env python3
"""Run at most three explicitly named Kling segments in one R&D authorization window."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("segments", nargs="+")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks/jensen_rubin_live_30s_v2.segments.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if len(args.segments) > 3:
        parser.error("R&D authorization covers at most three case/segment calls")
    if len(set(args.segments)) != len(args.segments):
        parser.error("duplicate segment ids are not allowed")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    known = {segment["id"] for segment in config["segments"]}
    unknown = [segment for segment in args.segments if segment not in known]
    if unknown:
        parser.error("unknown segment ids: " + ", ".join(unknown))
    receipts = []
    for index, segment in enumerate(args.segments):
        command = [
            sys.executable, str(ROOT / "scripts/run_camera_segment.py"), segment,
            "--config", str(args.config), "--research-budget-limit", "3",
            "--research-budget-used", str(index),
        ]
        if args.dry_run:
            receipts.append({"segment_id": segment, "call_index": index + 1, "command": command})
            continue
        process = subprocess.run(command, cwd=ROOT, check=False)
        receipts.append({"segment_id": segment, "call_index": index + 1, "returncode": process.returncode})
        if process.returncode:
            # No implicit retries and no attempt to switch provider/model.
            break
    print(json.dumps({
        "schema": "visualagent.research-paid-batch.v1",
        "limit": 3, "automatic_retry": False, "model_substitution": False,
        "calls": receipts,
    }, ensure_ascii=False, indent=2))
    return 0 if args.dry_run or all(item.get("returncode") == 0 for item in receipts) else 3


if __name__ == "__main__":
    raise SystemExit(main())
