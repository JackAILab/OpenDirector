from pathlib import Path

import pytest
from PIL import Image

from harness.models.base import ImageModel, ImageRequest, ImageResult
from harness.tools import GPTImageTool


class FakeImageModel(ImageModel):
    def create(self, request: ImageRequest) -> ImageResult:
        request.output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 96), "white").save(request.output)
        provenance = request.output.with_suffix(".provenance.json")
        provenance.write_text("{}\n", encoding="utf-8")
        return ImageResult(request.output, provenance, "fake", (64, 96), request.model or "fake", "generate")


def test_gpt_image_tool_keeps_outputs_under_artifact_root(tmp_path: Path):
    observation = GPTImageTool(FakeImageModel(), output_root=tmp_path).invoke({
        "prompt": "test", "output": "case/a.png", "model": "fake",
    })
    assert observation.ok
    assert (tmp_path / "case/a.png").is_file()


def test_gpt_image_tool_rejects_path_escape(tmp_path: Path):
    tool = GPTImageTool(FakeImageModel(), output_root=tmp_path)
    with pytest.raises(ValueError, match="artifact root"):
        tool.invoke({"prompt": "test", "output": "../escape.png"})


def test_provenance_contract_uses_artifact_names_not_host_paths(tmp_path: Path):
    observation = GPTImageTool(FakeImageModel(), output_root=tmp_path).invoke({
        "prompt": "test", "output": "case/a.png", "model": "fake",
    })
    assert observation.ok
    # The fake model is deliberately minimal; the production adapter contract is checked by source-level safety here.
    source = Path("harness/models/openai_image.py").read_text(encoding="utf-8")
    assert '"name": path.name' in source
    assert '"path": str(path)' not in source
