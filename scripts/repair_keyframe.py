#!/usr/bin/env python3
"""Apply an explicit, non-neural technical keyframe repair with provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageEnhance


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--brightness", type=float, default=1.75)
    parser.add_argument("--contrast", type=float, default=1.12)
    parser.add_argument("--gamma", type=float, default=1.0, help="Gamma below 1 lifts shadows while preserving highlights.")
    args = parser.parse_args()
    provenance = args.output.with_suffix(".provenance.json")
    if args.output.exists() or provenance.exists():
        raise FileExistsError(f"refusing to overwrite repair artifact: {args.output}")
    with Image.open(args.source) as source:
        image = source.convert("RGB")
    width, height = image.size
    crop_width = round(height * 9 / 16)
    if crop_width > width:
        raise ValueError("source is narrower than 9:16")
    left = (width - crop_width) // 2
    image = image.crop((left, 0, left + crop_width, height)).resize((1080, 1920), Image.Resampling.LANCZOS)
    image = ImageEnhance.Brightness(image).enhance(args.brightness)
    image = ImageEnhance.Contrast(image).enhance(args.contrast)
    if args.gamma <= 0:
        raise ValueError("gamma must be positive")
    if args.gamma != 1.0:
        table = [round(255 * ((value / 255) ** args.gamma)) for value in range(256)]
        image = image.point(table * 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    source_provenance = args.source.with_suffix(".provenance.json")
    source_record = json.loads(source_provenance.read_text(encoding="utf-8")) if source_provenance.is_file() else {}
    provenance.write_text(json.dumps({
        "schema": "visualagent.keyframe-technical-repair.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": source_record.get("model"),
        "source": {"name": args.source.name, "sha256": sha256(args.source), "provenance": source_provenance.name},
        "operation": "deterministic_center_crop_exposure_contrast_gamma",
        "parameters": {"target_dimensions": [1080, 1920], "brightness": args.brightness, "contrast": args.contrast, "gamma": args.gamma},
        "output": {"name": args.output.name, "sha256": sha256(args.output), "dimensions": [1080, 1920]},
        "paid_call": False, "semantic_content_changed": False,
        "training_eligible": False, "human_review": "pending"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
