import json
from pathlib import Path

from PIL import Image

from harness.evaluators import ImageArtifactEvaluator


def write_candidate(path: Path, *, size=(90, 160), color=(200, 200, 200), model="gp2/gpt-image-2"):
    Image.new("RGB", size, color).save(path)
    path.with_suffix(".provenance.json").write_text(json.dumps({"model": model}), encoding="utf-8")


def test_image_evaluator_passes_bright_portrait(tmp_path: Path):
    path = tmp_path / "good.png"
    write_candidate(path)
    report = ImageArtifactEvaluator([path], expected_model="gp2/gpt-image-2").evaluate(None)
    assert report["passed"] is True
    assert report["candidates"][0]["failures"] == []


def test_image_evaluator_reports_model_aspect_and_exposure(tmp_path: Path):
    path = tmp_path / "bad.png"
    write_candidate(path, size=(100, 100), color=(0, 0, 0), model="wrong")
    report = ImageArtifactEvaluator([path], expected_model="gp2/gpt-image-2").evaluate(None)
    failures = report["candidates"][0]["failures"]
    assert {"model_mismatch", "aspect_mismatch", "underexposed", "excess_dark_pixels"} <= set(failures)


def test_image_evaluator_rejects_clipped_face_region_without_rejecting_dark_set(tmp_path: Path):
    good = tmp_path / "good-dark-set.png"
    clipped = tmp_path / "clipped-face.png"
    write_candidate(good, color=(80, 80, 80))
    write_candidate(clipped, color=(80, 80, 80))
    image = Image.open(clipped).convert("RGB")
    width, height = image.size
    for x in range(int(width * 0.32), int(width * 0.68)):
        for y in range(int(height * 0.10), int(height * 0.38)):
            image.putpixel((x, y), (255, 255, 255))
    image.save(clipped)

    good_report = ImageArtifactEvaluator(
        [good], expected_model="gp2/gpt-image-2", min_mean_luma=72.0,
        max_face_highlight_ratio=0.08,
    ).evaluate(None)
    clipped_report = ImageArtifactEvaluator(
        [clipped], expected_model="gp2/gpt-image-2", min_mean_luma=72.0,
        max_face_highlight_ratio=0.08,
    ).evaluate(None)
    assert good_report["passed"] is True
    assert "face_highlights_clipped" in clipped_report["candidates"][0]["failures"]
