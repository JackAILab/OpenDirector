from __future__ import annotations

from pathlib import Path

from PIL import Image

from harness.evaluators.continuity import BoundaryContinuityPolicy, compare_frame_pair, global_ssim


def test_global_ssim_is_one_for_identical_images() -> None:
    image = Image.new("RGB", (40, 40), "#52665b")
    assert global_ssim(image, image, size=(40, 40)) == 1.0


def test_boundary_policy_rejects_large_semantic_change(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (80, 120), "#050505").save(first)
    Image.new("RGB", (80, 120), "#f7f7f7").save(second)
    metrics = compare_frame_pair(first, second)
    assert BoundaryContinuityPolicy().classify(metrics) == "fail"


def test_boundary_policy_passes_identical_frames(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (80, 120), "#6f735e").save(first)
    Image.new("RGB", (80, 120), "#6f735e").save(second)
    metrics = compare_frame_pair(first, second)
    assert BoundaryContinuityPolicy().classify(metrics) == "pass"
