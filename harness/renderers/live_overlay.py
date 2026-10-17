from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from harness.live.timeline import LiveProductionTimeline

from .common import encode_rgba_track


def _font(path: Path | None, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path and path.is_file():
        return ImageFont.truetype(str(path), size)
    fallback = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(fallback, size) if Path(fallback).is_file() else ImageFont.load_default()


def _active(events: list[dict[str, Any]], time: float) -> list[dict[str, Any]]:
    return [event for event in events if float(event.get("start", event.get("time", 0))) <= time < float(event.get("end", event.get("time", 0) + event.get("duration", 3.5)))]


def render_live_overlay(
    timeline: LiveProductionTimeline, output: Path, *, width: int = 1080, height: int = 1920, fps: int = 30,
    font_path: Path | None = None,
) -> Path:
    regular = _font(font_path, 34)
    small = _font(font_path, 27)
    bold = _font(font_path, 38, bold=True)
    title = str(timeline.payload.get("ui_template", {}).get("host_label", "AI LIVE DEMO"))
    disclosure = str(timeline.payload.get("disclosure", "AI-generated demonstration · not a real livestream or endorsement"))

    def frame(time: float) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((28, 28, 670, 126), radius=34, fill=(12, 17, 22, 178))
        draw.ellipse((48, 47, 104, 103), fill=(118, 215, 160, 255))
        draw.text((122, 48), title, font=bold, fill="white")
        draw.rounded_rectangle((520, 49, 645, 101), radius=18, fill=(238, 42, 83, 245))
        draw.text((548, 57), "LIVE", font=small, fill="white")
        draw.rounded_rectangle((28, 140, 850, 202), radius=22, fill=(0, 0, 0, 175))
        draw.text((52, 154), disclosure, font=small, fill=(255, 232, 128, 255))
        state_events = [event for event in timeline.tracks.get("ui", []) if float(event.get("time", event.get("start", 0))) <= time]
        state: dict[str, Any] = {}
        for event in state_events:
            state.update(event.get("state", {}))
        draw.rounded_rectangle((786, 38, 1042, 116), radius=28, fill=(12, 17, 22, 178))
        draw.text((814, 57), f"{int(state.get('viewer_count', 126700)):,} watching", font=small, fill="white")
        for index, symbol in enumerate(("♥", "↗", "▣")):
            cy = 700 + index * 120
            draw.ellipse((938, cy, 1032, cy + 94), fill=(14, 20, 27, 190))
            draw.text((966, cy + 20), symbol, font=bold, fill="white")
        comments = [event for event in timeline.tracks.get("comments", []) if float(event.get("time", event.get("start", 0))) <= time]
        comments = comments[-4:]
        base_y = 1240
        for index, event in enumerate(comments):
            y = base_y + index * 100
            draw.rounded_rectangle((34, y, 748, y + 82), radius=26, fill=(0, 0, 0, 155))
            label = f"{event.get('username', 'viewer')}: {event.get('text', '')}"
            draw.text((58, y + 22), label, font=regular, fill="white")
        product_events = [event for event in _active(timeline.tracks.get("ui", []), time) if event.get("type") == "product_card"]
        if product_events:
            event = product_events[-1]
            draw.rounded_rectangle((500, 1475, 1034, 1742), radius=36, fill=(247, 249, 251, 244), outline=(66, 212, 151, 255), width=4)
            draw.text((538, 1514), str(event.get("title", "Flagship GPU")), font=bold, fill=(16, 23, 31, 255))
            draw.text((538, 1580), str(event.get("subtitle", "AI product demonstration")), font=small, fill=(65, 74, 84, 255))
            draw.rounded_rectangle((760, 1642, 988, 1710), radius=22, fill=(34, 184, 113, 255))
            draw.text((811, 1658), "VIEW", font=small, fill="white")
        draw.rounded_rectangle((32, 1785, 870, 1878), radius=38, fill=(12, 17, 22, 188))
        draw.text((70, 1812), "Add a comment...", font=regular, fill=(215, 220, 225, 255))
        return image

    encode_rgba_track(output, width=width, height=height, fps=fps, duration=timeline.duration, frame_factory=frame)
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps({
        "schema": "visualagent.live-overlay-manifest.v1", "layer": "ui",
        "duration": timeline.duration, "fps": fps, "resolution": [width, height],
        "static_ui_pixel_drift_expected": 0,
        "comment_event_ids": [event["id"] for event in timeline.tracks.get("comments", [])],
        "ui_event_ids": [event["id"] for event in timeline.tracks.get("ui", [])],
        "disclosure_present": bool(disclosure), "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
