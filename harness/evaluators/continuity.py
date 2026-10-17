from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


def _luma_pixels(image: Image.Image, size: tuple[int, int]) -> list[int]:
    resized = image.convert("L").resize(size, Image.Resampling.BILINEAR)
    return list(resized.getdata())


def global_ssim(first: Image.Image, second: Image.Image, *, size: tuple[int, int] = (270, 480)) -> float:
    """Return a deterministic global structural-similarity proxy in [-1, 1]."""
    a = _luma_pixels(first, size)
    b = _luma_pixels(second, size)
    count = len(a)
    mean_a = sum(a) / count
    mean_b = sum(b) / count
    var_a = sum((value - mean_a) ** 2 for value in a) / count
    var_b = sum((value - mean_b) ** 2 for value in b) / count
    covariance = sum((left - mean_a) * (right - mean_b) for left, right in zip(a, b)) / count
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    numerator = (2 * mean_a * mean_b + c1) * (2 * covariance + c2)
    denominator = (mean_a**2 + mean_b**2 + c1) * (var_a + var_b + c2)
    return numerator / denominator if denominator else 1.0


def normalized_mean_absolute_difference(
    first: Image.Image, second: Image.Image, *, size: tuple[int, int] = (270, 480),
) -> float:
    a = first.convert("RGB").resize(size, Image.Resampling.BILINEAR)
    b = second.convert("RGB").resize(size, Image.Resampling.BILINEAR)
    channel_means = ImageStat.Stat(ImageChops.difference(a, b)).mean
    return sum(channel_means) / (len(channel_means) * 255)


def compare_frame_pair(first_path: Path, second_path: Path) -> dict[str, float]:
    with Image.open(first_path) as first, Image.open(second_path) as second:
        width, height = first.size
        regions = {
            "full": (0, 0, width, height),
            "upper": (0, 0, width, height // 2),
            "lower": (0, height // 2, width, height),
            "center": (width // 5, height // 6, width * 4 // 5, height * 5 // 6),
        }
        result: dict[str, float] = {}
        for name, box in regions.items():
            left = first.crop(box)
            right = second.crop(box)
            result[f"{name}_ssim"] = round(global_ssim(left, right), 6)
            result[f"{name}_mad"] = round(normalized_mean_absolute_difference(left, right), 6)
        return result


@dataclass(frozen=True)
class BoundaryContinuityPolicy:
    pass_ssim: float = 0.72
    review_ssim: float = 0.48
    fail_mad: float = 0.22

    def classify(self, metrics: dict[str, float]) -> str:
        similarity = metrics["full_ssim"]
        difference = metrics["full_mad"]
        if similarity >= self.pass_ssim and difference < self.fail_mad:
            return "pass"
        if similarity < self.review_ssim or difference >= self.fail_mad:
            return "fail"
        return "needs_review"

    def audit(self, pairs: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for pair in pairs:
            metrics = compare_frame_pair(Path(pair["before"]), Path(pair["after"]))
            results.append({**pair, "metrics": metrics, "status": self.classify(metrics)})
        return {
            "passed": all(result["status"] == "pass" for result in results),
            "policy": {
                "pass_ssim": self.pass_ssim,
                "review_ssim": self.review_ssim,
                "fail_mad": self.fail_mad,
            },
            "boundaries": results,
            "human_review_required": [
                "host identity and pose continuity",
                "product geometry and hand contact",
                "physical-set object persistence",
                "absence of within-segment object pops",
            ],
        }
