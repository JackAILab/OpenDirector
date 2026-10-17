#!/usr/bin/env python3
"""Read-only audit of the AdvertiseAgent paper evidence gates."""
from __future__ import annotations
import argparse, json
from pathlib import Path

PACKETS = {
    "source_relation": ("paper-source-relations-review-20261009-v2", "visualagent.source-relation-packet.v1"),
    "reference_plan": ("paper-cross-reference-review-20261009-v2", "visualagent.reference-plan-review-packet.v1"),
}
REVIEW_SCHEMAS = {
    "visualagent.source-relation-review.v1",
    "visualagent.reference-plan-review.v1",
    "visualagent.human-plan-review-draft.v1",
}

def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

def audit(learning_root: Path, repo_root: Path):
    packets = {}
    for name, (directory, expected_schema) in PACKETS.items():
        packet = learning_root / directory / "packet.json"
        data = load_json(packet) if packet.exists() else None
        packets[name] = {
            "packet_present": packet.exists(),
            "schema": data.get("schema") if isinstance(data, dict) else None,
            "expected_schema": expected_schema,
            "schema_valid": isinstance(data, dict) and data.get("schema") == expected_schema,
            "reviewer_package_present": (packet.parent / "reviewer-package.zip").exists(),
        }

    review_files = []
    review_counts = {schema: 0 for schema in sorted(REVIEW_SCHEMAS)}
    for path in learning_root.rglob("*.json"):
        data = load_json(path)
        schema = data.get("schema") if isinstance(data, dict) else None
        if schema in REVIEW_SCHEMAS:
            review_files.append(path)
            review_counts[schema] += 1

    analysis_plan = repo_root / "docs/research/advertising_agent/analysis_plan_v1.md"
    manuscript = repo_root / "docs/research/advertising_agent/paper_draft_v0.md"
    return {
        "schema": "visualagent.research-readiness-audit.v1",
        "scope": "known_learning_root_only",
        "analysis_plan_present": analysis_plan.exists(),
        "manuscript_present": manuscript.exists(),
        "packets": packets,
        "review_exports": {"count": len(review_files), "by_schema": review_counts},
        "independent_review_gate": "passed" if review_files else "pending",
        "video_evaluation_gate": "pending",
        "license_gate": "pending",
        "training_eligible": False,
        "limitations": [
            "No external inbox, user computer, or unlisted directory was scanned.",
            "A packet is not a review response; independent identity and semantic agreement require dedicated intake validation.",
        ],
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--learning-root", type=Path, default=Path("/var/lib/visualstation-local/creative/learning"))
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    payload = audit(args.learning_root, args.repo_root)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text, end="")

if __name__ == "__main__":
    main()
