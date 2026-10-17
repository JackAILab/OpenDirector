#!/usr/bin/env python3
"""Collect trajectory summaries without changing source trajectories."""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectory_dir", type=Path, nargs="?", default=Path("outputs/trajectories"))
    args = parser.parse_args()
    rows = []
    for path in sorted(args.trajectory_dir.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "run_id": item.get("run_id"), "task_id": item.get("task_id"),
            "passed": item.get("evaluation", {}).get("passed"),
            "training_eligible": item.get("training_eligible", False), "path": str(path),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
