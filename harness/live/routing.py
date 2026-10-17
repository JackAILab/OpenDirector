from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RepairRoute:
    layer: Literal["camera", "ui", "vfx", "tracking_ar", "video_edit", "audio"]
    tools: tuple[str, ...]
    regenerate_camera: bool
    reason: str


def route_change(*, symbolic: bool, affects_subject: bool = False, trackable: bool = False, audio: bool = False) -> RepairRoute:
    if audio:
        return RepairRoute("audio", ("render_audio", "compose_video"), False, "audio-only repair")
    if symbolic:
        return RepairRoute("ui", ("render_hyperframes_layer", "compose_video"), False, "symbolic content belongs to professional renderer")
    if not affects_subject:
        return RepairRoute("vfx", ("render_hyperframes_layer", "compose_video"), False, "screen-space visual effect")
    if trackable:
        return RepairRoute("tracking_ar", ("track_subject", "render_ar", "compose_video"), False, "rigid subject-anchored effect")
    return RepairRoute("video_edit", ("edit_camera_video",), True, "appearance or geometry change requires neural edit")
