from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.core.types import Observation
from harness.models.base import VideoModel, VideoRequest

from .base import Tool


class CameraVideoTool(Tool):
    name = "generate_camera_video"
    layer = "camera"
    paid = True

    def __init__(self, model: VideoModel, *, output_root: Path) -> None:
        self.model = model
        self.output_root = output_root.resolve()

    def _output(self, value: str) -> Path:
        path = (self.output_root / value).resolve()
        if path != self.output_root and self.output_root not in path.parents:
            raise ValueError("output must remain under configured artifact root")
        return path

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("camera prompt is required")
        result = self.model.create(VideoRequest(
            prompt=prompt, output=self._output(str(arguments["output"])),
            reference_images=tuple(Path(value).resolve() for value in arguments.get("reference_images", [])),
            model=str(arguments["model"]), duration_seconds=int(arguments.get("duration_seconds", 15)),
            aspect_ratio=str(arguments.get("aspect_ratio", "9:16")),
            resolution=str(arguments.get("resolution", "1080p")),
            image_count=int(arguments.get("image_count", 1)),
            prefer_multi_shots=bool(arguments.get("prefer_multi_shots", False)),
            enable_audio=bool(arguments.get("enable_audio", False)),
            task_trace_id=arguments.get("task_trace_id"), metadata=dict(arguments.get("metadata", {})),
        ))
        return Observation(ok=True, content={
            "layer": self.layer, "artifact": str(result.output), "receipt": str(result.receipt),
            "sha256": result.sha256, "model": result.model,
            "generation_id": result.generation_id, "credits_consumed": result.credits_consumed,
        })
