import json
from pathlib import Path

import pytest

from harness.live import LiveProductionTimeline, TimelineValidationError, compile_camera_prompt, route_change


TIMELINE = Path("data/tasks/jensen_rtx5090_live_v1.timeline.json")
TIMELINE_60 = Path("data/tasks/jensen_rubin_live_60s_v1.timeline.json")


def load_timeline() -> LiveProductionTimeline:
    return LiveProductionTimeline.from_dict(json.loads(TIMELINE.read_text(encoding="utf-8")))


def test_timeline_validates_cross_track_causality():
    timeline = load_timeline()
    assert timeline.duration == 15.0
    assert timeline.tracks["camera"][1]["responds_to"] == "comment_power"


def test_60s_timeline_has_eight_camera_segments_and_code_owned_symbolic_tracks():
    timeline = LiveProductionTimeline.from_dict(json.loads(TIMELINE_60.read_text(encoding="utf-8")))
    assert timeline.duration == 60.0
    assert len(timeline.tracks["camera"]) == 8
    assert all(event.get("model_owned") is False for name in ("comments", "ui", "vfx") for event in timeline.tracks[name])


def test_camera_prompt_excludes_symbolic_comment_and_ui_text():
    prompt = compile_camera_prompt(load_timeline())
    assert "电源怎么选才稳" not in prompt
    assert "RTX 5090 展示" not in prompt
    assert "No readable text, UI" in prompt
    assert "noticing a power-supply question" in prompt


def test_timeline_rejects_response_before_comment():
    payload = json.loads(TIMELINE.read_text(encoding="utf-8"))
    payload["tracks"]["comments"][1]["time"] = 4.5
    with pytest.raises(TimelineValidationError, match="before its cause"):
        LiveProductionTimeline.from_dict(payload)


def test_symbolic_tracks_cannot_be_model_owned():
    payload = json.loads(TIMELINE.read_text(encoding="utf-8"))
    payload["tracks"]["vfx"][0]["model_owned"] = True
    with pytest.raises(TimelineValidationError, match="cannot be model_owned"):
        LiveProductionTimeline.from_dict(payload)


def test_localized_repair_routing_does_not_regenerate_camera_for_ui_or_vfx():
    ui = route_change(symbolic=True)
    vfx = route_change(symbolic=False, affects_subject=False)
    ar = route_change(symbolic=False, affects_subject=True, trackable=True)
    edit = route_change(symbolic=False, affects_subject=True, trackable=False)
    assert ui.tools == ("render_hyperframes_layer", "compose_video")
    assert vfx.tools == ("render_hyperframes_layer", "compose_video")
    assert not ui.regenerate_camera and not vfx.regenerate_camera and not ar.regenerate_camera
    assert edit.regenerate_camera
