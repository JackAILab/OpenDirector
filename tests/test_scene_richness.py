from pathlib import Path

from PIL import Image, ImageDraw

from harness.evaluators import SceneRichnessEvaluator


def test_scene_richness_rejects_empty_flat_frame(tmp_path: Path):
    path = tmp_path / "empty.png"
    Image.new("RGB", (360, 640), "#777777").save(path)
    report = SceneRichnessEvaluator([path]).evaluate(None)
    assert not report["passed"]
    assert "low_visual_entropy" in report["candidates"][0]["failures"]


def test_scene_richness_accepts_layered_detail(tmp_path: Path):
    path = tmp_path / "layered.png"
    image = Image.new("RGB", (360, 640), "#111827")
    draw = ImageDraw.Draw(image)
    for y in range(0, 640, 24):
        for x in range(0, 360, 24):
            value = (x * 7 + y * 11) % 255
            draw.rectangle((x, y, x + 16, y + 16), fill=(value, 255 - value, (value * 3) % 255))
    draw.ellipse((80, 80, 280, 360), fill="#d1a17a", outline="white", width=4)
    draw.rectangle((35, 390, 325, 560), fill="#253346", outline="#67e8f9", width=5)
    image.save(path)
    report = SceneRichnessEvaluator(
        [path], min_entropy=3.0, min_edge_density=0.06, min_active_tiles=0, min_luma_spread=0,
    ).evaluate(None)
    assert report["passed"], report
