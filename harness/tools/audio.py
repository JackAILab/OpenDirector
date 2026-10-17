from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.audio import render_speech_track
from harness.core.types import Observation

from .live_render import _OutputBoundTool


class RenderAudioTool(_OutputBoundTool):
    name = "render_audio"
    layer = "audio"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        output = self.output_path(str(arguments["output"]))
        render_speech_track(
            self.timeline(str(arguments["timeline"])), output,
            voice=str(arguments.get("voice", "zh-CN-YunxiNeural")),
            rate=str(arguments.get("rate", "+12%")),
        )
        return Observation(ok=True, content={"layer": self.layer, "artifact": str(output), "manifest": str(output.with_suffix('.manifest.json')), "voice_clone": False})
