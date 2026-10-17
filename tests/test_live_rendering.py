import json
from pathlib import Path
from unittest.mock import patch

from harness.live import LiveProductionTimeline
from harness.renderers import render_live_overlay, render_vfx_overlay
from harness.evaluators.live import probe_video


def short_timeline() -> LiveProductionTimeline:
    return LiveProductionTimeline.from_dict({
        "schema": "visualagent.live-production-timeline.v1", "duration": 0.2,
        "disclosure": "AI DEMO", "scene": {"description": "test"},
        "tracks": {
            "camera": [{"id": "camera", "start": 0.0, "end": 0.2, "action": "test"}],
            "speech": [],
            "comments": [{"id": "comment", "time": 0.0, "duration": 0.2, "username": "u", "text": "hello", "model_owned": False}],
            "ui": [{"id": "state", "time": 0.0, "state": {"viewer_count": 2}, "model_owned": False}],
            "vfx": [{"id": "heart", "type": "heart_burst", "start": 0.0, "end": 0.2, "model_owned": False}],
            "ar": [], "subtitles": [],
        },
    })


def test_ui_and_vfx_render_to_independent_alpha_tracks(tmp_path: Path):
    timeline = short_timeline()
    ui = render_live_overlay(timeline, tmp_path / "ui.mov", width=180, height=320, fps=5)
    vfx = render_vfx_overlay(timeline, tmp_path / "vfx.mov", width=180, height=320, fps=5)
    assert ui.is_file() and vfx.is_file()
    assert ui.read_bytes() != vfx.read_bytes()
    ui_manifest = json.loads(ui.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    vfx_manifest = json.loads(vfx.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert ui_manifest["comment_event_ids"] == ["comment"]
    assert vfx_manifest["events"][0]["id"] == "heart"


def test_probe_uses_bundled_ffmpeg_when_matching_ffprobe_is_unavailable(tmp_path: Path):
    video = tmp_path / "camera.mp4"
    video.touch()
    stderr = (
        "Duration: 00:00:15.00, start: 0.000000, bitrate: 8000 kb/s\n"
        "Stream #0:0: Video: h264, yuv420p, 1080x1920, 30 fps\n"
    )
    with patch("harness.evaluators.live.ffmpeg_executable", return_value="/opt/bundled/ffmpeg"), \
         patch("harness.evaluators.live.Path.is_file", side_effect=[True, False]), \
         patch("harness.evaluators.live.subprocess.run") as run:
        run.return_value = type("Process", (), {"stderr": stderr})()
        probe = probe_video(video)
    assert probe["probe_backend"] == "ffmpeg_stderr"
    assert probe["duration"] == 15.0
    assert (probe["width"], probe["height"], probe["fps"]) == (1080, 1920, "30")
    assert run.call_args.args[0][0] == "/opt/bundled/ffmpeg"
