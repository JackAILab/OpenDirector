from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.compositor import compose_live_video
from harness.core.types import Observation
from harness.live import LiveProductionTimeline
from harness.renderers import render_hyperframes_layer, render_live_overlay, render_vfx_overlay

from .base import Tool


class _OutputBoundTool(Tool):
    def __init__(self, *, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def output_path(self, value: str) -> Path:
        path = (self.output_root / value).resolve()
        if path != self.output_root and self.output_root not in path.parents:
            raise ValueError("output must remain under configured artifact root")
        return path

    @staticmethod
    def timeline(path: str) -> LiveProductionTimeline:
        return LiveProductionTimeline.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


class RenderLiveOverlayTool(_OutputBoundTool):
    name = "render_live_overlay"
    layer = "ui"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        output = self.output_path(str(arguments["output"]))
        render_live_overlay(
            self.timeline(str(arguments["timeline"])), output,
            width=int(arguments.get("width", 1080)), height=int(arguments.get("height", 1920)),
            fps=int(arguments.get("fps", 30)),
            font_path=Path(arguments["font_path"]) if arguments.get("font_path") else None,
        )
        return Observation(ok=True, content={"layer": self.layer, "artifact": str(output), "manifest": str(output.with_suffix('.manifest.json'))})


class RenderVFXTool(_OutputBoundTool):
    name = "render_vfx"
    layer = "vfx"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        output = self.output_path(str(arguments["output"]))
        render_vfx_overlay(
            self.timeline(str(arguments["timeline"])), output,
            width=int(arguments.get("width", 1080)), height=int(arguments.get("height", 1920)),
            fps=int(arguments.get("fps", 30)),
        )
        return Observation(ok=True, content={"layer": self.layer, "artifact": str(output), "manifest": str(output.with_suffix('.manifest.json'))})


class RenderHyperFramesLayerTool(_OutputBoundTool):
    name = "render_hyperframes_layer"
    layer = "ui_vfx"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        output = self.output_path(str(arguments["output"]))
        layer_mode = str(arguments.get("layer_mode", "review"))
        render_hyperframes_layer(
            self.timeline(str(arguments["timeline"])), output,
            project=Path(arguments["project"]), layer_mode=layer_mode,  # type: ignore[arg-type]
            fps=int(arguments.get("fps", 30)), quality=str(arguments.get("quality", "high")),
            workers=int(arguments.get("workers", 4)),
        )
        return Observation(ok=True, content={
            "layer": layer_mode, "artifact": str(output),
            "manifest": str(output.with_suffix('.manifest.json')),
            "review_only": layer_mode == "review",
        })


class ComposeVideoTool(_OutputBoundTool):
    name = "compose_video"
    layer = "composite"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        output = self.output_path(str(arguments["output"]))
        compose_live_video(
            camera_video=Path(arguments["camera_video"]), ui_overlay=Path(arguments["ui_overlay"]),
            vfx_overlay=Path(arguments["vfx_overlay"]) if arguments.get("vfx_overlay") else None,
            audio=Path(arguments["audio"]) if arguments.get("audio") else None, output=output,
            width=int(arguments.get("width", 1080)), height=int(arguments.get("height", 1920)),
            fps=int(arguments.get("fps", 30)),
        )
        return Observation(ok=True, content={"layer": self.layer, "artifact": str(output)})
