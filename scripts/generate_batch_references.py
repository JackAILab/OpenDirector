#!/usr/bin/env python3
"""Generate non-overwriting GPT Image 2 first/tail references for batch cases."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from harness.models import OpenAIImageModel
from harness.models.base import ImageRequest

ROOT = Path(__file__).resolve().parents[1]


def copy_approved(source: Path, output: Path) -> None:
    provenance = output.with_suffix(".provenance.json")
    if output.exists() or provenance.exists():
        raise FileExistsError(f"refusing to overwrite approved reference: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    source_provenance = source.with_suffix(".provenance.json")
    provenance.write_text(json.dumps({
        "schema": "visualagent.approved-reference-reuse.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source), "source_provenance": str(source_provenance),
        "model": "gp2/gpt-image-2", "paid_call": False,
        "human_review": "approved_for_camera_reference",
        "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=ROOT / "configs/batches/jensen_rtx5090_live_batch10.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/artifacts/jensen_rtx5090_live_batch10_20260820")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    source_root = ROOT / "outputs/artifacts/jensen_rtx5090_live_v1_20260819/camera_references"
    copy_approved(source_root / "first-repaired-v3.png", args.output_root / "v01_power/camera_references/first.png")
    copy_approved(source_root / "tail-repaired-v2.png", args.output_root / "v01_power/camera_references/tail.png")

    config = json.loads((ROOT / "configs/models/gpt_image_2.json").read_text(encoding="utf-8"))
    env = config["environment"]
    model = OpenAIImageModel(
        model_env=env["model"], base_url_env=env["base_url"],
        api_key_env=env["api_key"], expected_model=spec["image_model"],
    )
    common = (
        "Photorealistic premium vertical 9:16 synthetic livestream camera plate. A clearly synthetic "
        "dramatization of Jensen Huang in a black leather jacket presents exactly one RTX 5090 Founders "
        "Edition with stable physically coherent dual-fan geometry and natural five-finger hands. Rich, "
        "commercially legible physical set with foreground, midground and background depth. Keep face in "
        "upper-middle and GPU centered, leaving compact lower-left, right-rail and lower-right overlay-safe "
        "zones without making the scene empty. No readable text, letters, numbers, UI, comments, captions, "
        "prices, inventory, claims, buttons, logos, watermarks, extra fingers, duplicate GPU or third fan. "
    )
    for case in spec["cases"][1:]:
        case_root = args.output_root / case["id"] / "camera_references"
        first = case_root / "first.png"
        tail = case_root / "tail.png"
        first_prompt = common + "Physical set: " + case["scene"] + ". Opening pose: direct eye contact, GPU held vertically at chest height, stable tripod medium shot."
        model.create(ImageRequest(
            prompt=first_prompt, output=first, model=spec["image_model"],
            size="1024x1824", quality="high",
            metadata={"batch_id": spec["batch_id"], "case_id": case["id"], "role": "camera_reference_first", "synthetic_public_figure": True},
        ))
        tail_prompt = (
            "Preserve the exact same synthetic host identity, black leather jacket, RTX 5090 dual-fan "
            "geometry, lighting, physical studio and tripod framing. Closing pose: the same GPU is angled "
            "slightly while both fan openings remain visible; the host returns to camera with a calm nod. "
            "Natural five-finger hands. No readable text, UI, price, claims, logo, watermark, duplicate GPU, "
            "third fan or changed background."
        )
        model.create(ImageRequest(
            prompt=tail_prompt, output=tail, reference_images=(first,), operation="edit",
            model=spec["image_model"], size="1024x1824", quality="high",
            metadata={"batch_id": spec["batch_id"], "case_id": case["id"], "role": "camera_reference_tail", "synthetic_public_figure": True},
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
