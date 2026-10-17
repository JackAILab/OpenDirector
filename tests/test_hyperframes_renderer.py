import json
from pathlib import Path
from unittest.mock import patch

from harness.live import LiveProductionTimeline
from harness.renderers.hyperframes import render_hyperframes_layer


def minimal_timeline() -> LiveProductionTimeline:
    return LiveProductionTimeline.from_dict({
        "schema": "visualagent.live-production-timeline.v1", "duration": 1.0,
        "disclosure": "AI DEMO", "scene": {"description": "test"},
        "tracks": {
            "camera": [{"id": "camera", "start": 0.0, "end": 1.0, "action": "test"}],
            "speech": [], "comments": [{"id": "c", "time": 0.1, "duration": 0.5, "model_owned": False}],
            "ui": [{"id": "u", "time": 0.0, "model_owned": False}],
            "vfx": [{"id": "v", "start": 0.2, "end": 0.8, "model_owned": False}],
            "ar": [], "subtitles": [],
        },
    })


def test_hyperframes_ui_layer_is_non_overwriting_and_records_evidence(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "DESIGN.md").write_text("design", encoding="utf-8")
    (project / "index.html").write_text("<html></html>", encoding="utf-8")
    output = tmp_path / "ui.webm"

    def fake_run(command, **kwargs):
        if "render" in command:
            output.write_bytes(b"0" * 2048)
        return "ok"

    with patch("harness.renderers.hyperframes.subprocess.run") as run:
        run.side_effect = lambda command, **kwargs: type("P", (), {"returncode": 0, "stdout": fake_run(command), "stderr": ""})()
        render_hyperframes_layer(minimal_timeline(), output, project=project, layer_mode="ui", fps=30)

    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["renderer"] == "HyperFrames HTML/CSS/SVG/GSAP"
    assert manifest["comment_event_ids"] == ["c"]
    assert manifest["vfx_event_ids"] == []
    assert manifest["training_eligible"] is False
    render_command = next(call.args[0] for call in run.call_args_list if "render" in call.args[0])
    assert "webm" in render_command
    assert '{"layerMode":"ui"}' in render_command
