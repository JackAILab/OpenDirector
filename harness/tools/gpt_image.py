from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.core.types import Observation
from harness.models.base import ImageModel, ImageRequest

from .base import Tool


class GPTImageTool(Tool):
    name = "generate_image"
    layer = "camera_reference"
    paid = True

    def __init__(self, model: ImageModel, *, output_root: Path) -> None:
        self.model = model
        self.output_root = output_root.resolve()

    def _output_path(self, value: str) -> Path:
        path = (self.output_root / value).resolve()
        if path != self.output_root and self.output_root not in path.parents:
            raise ValueError("output must remain under the configured artifact root")
        return path

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("prompt is required")
        output = self._output_path(str(arguments["output"]))
        references = tuple(Path(path).resolve() for path in arguments.get("reference_images", []))
        result = self.model.create(ImageRequest(
            prompt=prompt, output=output, reference_images=references, operation=arguments.get("operation"),
            model=arguments.get("model"),
            size=str(arguments.get("size", "1024x1824")), quality=str(arguments.get("quality", "high")),
            metadata=dict(arguments.get("metadata", {})),
        ))
        return Observation(ok=True, content={
            "output": str(result.output), "provenance": str(result.provenance), "sha256": result.sha256,
            "dimensions": list(result.dimensions), "model": result.model, "operation": result.operation,
            "generation_id": result.generation_id, "credits_consumed": result.credits_consumed,
        })
