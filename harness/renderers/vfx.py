from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from harness.live.timeline import LiveProductionTimeline

from .common import encode_rgba_track


def render_vfx_overlay(
    timeline: LiveProductionTimeline, output: Path, *, width: int = 1080, height: int = 1920, fps: int = 30,
) -> Path:
    def frame(time: float) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        for event in timeline.tracks.get("vfx", []):
            start = float(event.get("start", event.get("time", 0)))
            end = float(event.get("end", start + event.get("duration", 1.5)))
            if not start <= time < end:
                continue
            progress = (time - start) / max(end - start, 0.001)
            if event.get("type") == "heart_burst":
                for index in range(10):
                    phase = (progress + index * 0.073) % 1.0
                    x = 870 + int(95 * math.sin(index * 2.1 + progress * 4))
                    y = 1540 - int(720 * phase)
                    alpha = int(255 * (1 - phase))
                    draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(255, 45, 102, alpha))
            elif event.get("type") == "rocket":
                x = int(width * (0.15 + 0.70 * progress))
                y = int(height * (0.82 - 0.58 * progress))
                draw.polygon([(x, y - 70), (x - 38, y + 30), (x + 38, y + 30)], fill=(235, 240, 250, 245))
                draw.ellipse((x - 22, y - 28, x + 22, y + 16), fill=(61, 194, 255, 255))
                draw.polygon([(x - 22, y + 28), (x, y + 100), (x + 22, y + 28)], fill=(255, 107, 36, 220))
        return image

    encode_rgba_track(output, width=width, height=height, fps=fps, duration=timeline.duration, frame_factory=frame)
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps({
        "schema": "visualagent.vfx-overlay-manifest.v1", "layer": "vfx",
        "duration": timeline.duration, "fps": fps, "resolution": [width, height],
        "events": [{"id": event["id"], "type": event.get("type"), "start": event.get("start", event.get("time")), "end": event.get("end")} for event in timeline.tracks.get("vfx", [])],
        "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
