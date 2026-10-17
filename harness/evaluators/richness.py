from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from harness.core.state import RunState

from .base import Evaluator


def _entropy(image: Image.Image) -> float:
    histogram = image.convert("L").histogram()
    total = sum(histogram) or 1
    return -sum((count / total) * math.log2(count / total) for count in histogram if count)


class SceneRichnessEvaluator(Evaluator):
    """Gate against empty keyframes without rewarding model-painted text or UI."""

    def __init__(
        self, paths: list[Path], *, min_entropy: float = 5.2, min_edge_density: float = 0.08,
        min_active_tiles: int = 6, min_luma_spread: float = 34.0, min_pass_count: int = 1,
    ) -> None:
        self.paths = paths
        self.min_entropy = min_entropy
        self.min_edge_density = min_edge_density
        self.min_active_tiles = min_active_tiles
        self.min_luma_spread = min_luma_spread
        self.min_pass_count = min_pass_count

    def _one(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"path": str(path), "passed": False, "failures": ["missing_image"]}
        with Image.open(path) as source:
            image = source.convert("RGB").resize((360, 640), Image.Resampling.LANCZOS)
        luminance = image.convert("L")
        edges = luminance.filter(ImageFilter.FIND_EDGES)
        edge_density = sum(edges.histogram()[32:]) / (image.width * image.height)
        width, height = image.size
        tile_metrics = []
        for row in range(3):
            for column in range(3):
                tile = luminance.crop((column * width // 3, row * height // 3, (column + 1) * width // 3, (row + 1) * height // 3))
                tile_edges = tile.filter(ImageFilter.FIND_EDGES)
                tile_edge_density = sum(tile_edges.histogram()[32:]) / max(tile.width * tile.height, 1)
                tile_metrics.append({
                    "entropy": _entropy(tile), "edge_density": tile_edge_density,
                    "luma_stddev": float(ImageStat.Stat(tile).stddev[0]),
                })
        active_tiles = sum(
            metric["entropy"] >= 4.2 and metric["edge_density"] >= 0.045
            for metric in tile_metrics
        )
        luma_spread = max(metric["luma_stddev"] for metric in tile_metrics) - min(
            metric["luma_stddev"] for metric in tile_metrics
        )
        entropy = _entropy(luminance)
        failures = []
        if entropy < self.min_entropy:
            failures.append("low_visual_entropy")
        if edge_density < self.min_edge_density:
            failures.append("low_edge_density")
        if active_tiles < self.min_active_tiles:
            failures.append("insufficient_active_regions")
        if luma_spread < self.min_luma_spread:
            failures.append("flat_scene_depth")
        return {
            "path": str(path), "entropy": round(entropy, 3),
            "edge_density": round(edge_density, 4), "active_tiles_3x3": active_tiles,
            "tile_luma_stddev_spread": round(luma_spread, 2),
            "passed": not failures, "failures": failures,
        }

    def evaluate(self, state: RunState) -> dict[str, Any]:
        candidates = [self._one(path) for path in self.paths]
        passed_count = sum(item["passed"] for item in candidates)
        return {
            "passed": passed_count >= self.min_pass_count, "passed_count": passed_count,
            "required_pass_count": self.min_pass_count, "candidates": candidates,
            "thresholds": {
                "min_entropy": self.min_entropy, "min_edge_density": self.min_edge_density,
                "min_active_tiles_3x3": self.min_active_tiles, "min_luma_stddev_spread": self.min_luma_spread,
            },
            "semantic_review_required": [
                "foreground/midground/background separation",
                "multiple coherent product and studio anchors",
                "hardware display richness without cluttering overlay-safe zones",
                "no readable model-painted UI, comments, prices, counters or watermarks",
            ],
        }
