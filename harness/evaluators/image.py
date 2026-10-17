from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from harness.core.state import RunState

from .base import Evaluator


class ImageArtifactEvaluator(Evaluator):
    """Deterministic technical gate; visual semantics still require human review."""

    def __init__(
        self, paths: list[Path], *, expected_model: str, target_aspect: tuple[int, int] = (9, 16),
        aspect_tolerance: float = 0.02, min_mean_luma: float = 92.0, max_dark_pixel_ratio: float = 0.34,
        max_face_highlight_ratio: float | None = None, min_pass_count: int = 1,
    ) -> None:
        self.paths = paths
        self.expected_model = expected_model
        self.target_aspect = target_aspect[0] / target_aspect[1]
        self.aspect_tolerance = aspect_tolerance
        self.min_mean_luma = min_mean_luma
        self.max_dark_pixel_ratio = max_dark_pixel_ratio
        self.max_face_highlight_ratio = max_face_highlight_ratio
        self.min_pass_count = min_pass_count

    def _evaluate_one(self, path: Path) -> dict[str, Any]:
        failures: list[str] = []
        provenance_path = path.with_suffix(".provenance.json")
        if not path.is_file():
            return {"path": str(path), "passed": False, "failures": ["missing_image"]}
        if not provenance_path.is_file():
            failures.append("missing_provenance")
            provenance = {}
        else:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            if provenance.get("model") != self.expected_model:
                failures.append("model_mismatch")
        with Image.open(path) as source:
            image = source.convert("RGB")
            width, height = image.size
            luminance = image.convert("L")
            mean_luma = float(ImageStat.Stat(luminance).mean[0])
            histogram = luminance.histogram()
            dark_pixel_ratio = sum(histogram[:32]) / max(width * height, 1)
            face_region = luminance.crop((
                int(width * 0.32), int(height * 0.10), int(width * 0.68), int(height * 0.38),
            ))
            face_histogram = face_region.histogram()
            face_pixel_count = max(face_region.width * face_region.height, 1)
            face_highlight_ratio = sum(face_histogram[245:]) / face_pixel_count
        aspect = width / height
        if abs(aspect - self.target_aspect) > self.aspect_tolerance:
            failures.append("aspect_mismatch")
        if mean_luma < self.min_mean_luma:
            failures.append("underexposed")
        if dark_pixel_ratio > self.max_dark_pixel_ratio:
            failures.append("excess_dark_pixels")
        if self.max_face_highlight_ratio is not None and face_highlight_ratio > self.max_face_highlight_ratio:
            failures.append("face_highlights_clipped")
        return {
            "path": str(path), "provenance": str(provenance_path), "model": provenance.get("model"),
            "dimensions": [width, height], "aspect": round(aspect, 4),
            "mean_luma": round(mean_luma, 2), "dark_pixel_ratio": round(dark_pixel_ratio, 4),
            "face_highlight_ratio": round(face_highlight_ratio, 4),
            "passed": not failures, "failures": failures,
        }

    def evaluate(self, state: RunState) -> dict[str, Any]:
        candidates = [self._evaluate_one(path) for path in self.paths]
        passed_count = sum(candidate["passed"] for candidate in candidates)
        return {
            "passed": passed_count >= self.min_pass_count, "passed_count": passed_count,
            "required_pass_count": self.min_pass_count,
            "thresholds": {
                "target_aspect": "9:16", "aspect_tolerance": self.aspect_tolerance,
                "min_mean_luma": self.min_mean_luma, "max_dark_pixel_ratio": self.max_dark_pixel_ratio,
                "max_face_highlight_ratio": self.max_face_highlight_ratio,
            },
            "candidates": candidates,
            "human_visual_review_required": True,
        }
