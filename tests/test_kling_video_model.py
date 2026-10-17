from pathlib import Path
from unittest.mock import patch

import pytest

from harness.models.base import VideoRequest
from harness.models.kling_video import KlingVideoModel


def request(tmp_path: Path, model: str) -> VideoRequest:
    first = tmp_path / "first.png"
    tail = tmp_path / "tail.png"
    first.touch()
    tail.touch()
    return VideoRequest(
        prompt="clean camera feed", output=tmp_path / "out.mp4",
        reference_images=(first, tail), model=model, duration_seconds=15,
        aspect_ratio="9:16", resolution="1080p", prefer_multi_shots=False, enable_audio=False,
    )


def test_v3_first_tail_command_uses_tail_image_and_omits_aspect_ratio(tmp_path: Path):
    command = KlingVideoModel.build_command(request(tmp_path, "kling-video-v3_0"))
    assert command.count("--image") == 1
    assert "--tailImage" in command
    assert "--aspect_ratio" not in command
    assert command[command.index("--duration") + 1] == "15"
    assert command[command.index("--resolution") + 1] == "1080p"
    assert command[-2:] == ["clean camera feed", "--quiet"]


def test_omni_semantic_reference_command_keeps_two_reference_images_and_aspect_ratio(tmp_path: Path):
    command = KlingVideoModel.build_command(request(tmp_path, "kling-video-v3_0_omni"))
    assert command.count("--image") == 2
    assert "--tailImage" not in command
    assert command[command.index("--aspect_ratio") + 1] == "9:16"
    assert command[command.index("--duration") + 1] == "15"


def test_omni_hard_endpoint_command_uses_tail_image(tmp_path: Path):
    base = request(tmp_path, "kling-video-v3_0_omni")
    hard = VideoRequest(
        prompt=base.prompt, output=base.output, reference_images=base.reference_images,
        model=base.model, duration_seconds=base.duration_seconds,
        aspect_ratio=base.aspect_ratio, resolution=base.resolution,
        metadata={"input_mode": "hard_first_and_last_frames"},
    )
    command = KlingVideoModel.build_command(hard)
    assert command.count("--image") == 1
    assert command.count("--tailImage") == 1
    assert command[command.index("--aspect_ratio") + 1] == "9:16"


def test_v3_single_first_image_omits_tail_image(tmp_path: Path):
    base = request(tmp_path, "kling-video-v3_0")
    single = VideoRequest(
        prompt=base.prompt, output=base.output, reference_images=base.reference_images[:1],
        model=base.model, duration_seconds=base.duration_seconds, resolution=base.resolution,
    )
    command = KlingVideoModel.build_command(single)
    assert command.count("--image") == 1
    assert "--tailImage" not in command


def test_v3_rejects_more_than_one_tail_image(tmp_path: Path):
    base = request(tmp_path, "kling-video-v3_0")
    extra = tmp_path / "extra.png"
    extra.touch()
    malformed = VideoRequest(
        prompt=base.prompt, output=base.output, reference_images=(*base.reference_images, extra),
        model=base.model, duration_seconds=base.duration_seconds, resolution=base.resolution,
    )
    with pytest.raises(ValueError, match="at most one tail image"):
        KlingVideoModel.build_command(malformed)


def test_cli_command_keeps_boolean_quiet_after_prompt(tmp_path: Path):
    command = KlingVideoModel.build_command(request(tmp_path, "kling-video-v3_0"))
    assert command[-1] == "--quiet"
    assert command[-2] == "clean camera feed"


def test_cli_command_forwards_explicit_uuid7_task_trace_id(tmp_path: Path):
    base = request(tmp_path, "kling-video-v3_0")
    traced = VideoRequest(
        prompt=base.prompt, output=base.output, reference_images=base.reference_images,
        model=base.model, duration_seconds=base.duration_seconds, resolution=base.resolution,
        prefer_multi_shots=base.prefer_multi_shots, enable_audio=base.enable_audio,
        task_trace_id="019c7d3f-cc55-7e3e-8fe1-4c234d1f8f5a",
    )
    command = KlingVideoModel.build_command(traced)
    assert command[:3] == [
        "--task-trace-id", "019c7d3f-cc55-7e3e-8fe1-4c234d1f8f5a", "image_to_video",
    ]


def test_cli_failure_keeps_safe_mcp_reason_and_redacts_urls():
    process = type("Process", (), {
        "returncode": 1,
        "stdout": "",
        "stderr": (
            "[kling] Uploaded -> https://signed.example/secret\n"
            "MCP tool call failed (image_to_video): provider rejected request; "
            "url=https://signed.example/video?token=secret"
        ),
    })()
    with patch("harness.models.kling_video.subprocess.run", return_value=process):
        with pytest.raises(RuntimeError) as error:
            KlingVideoModel()._run(["image_to_video"])
    message = str(error.value)
    assert "provider rejected request" in message
    assert "signed.example" not in message
    assert "secret" not in message


def test_cli_failure_redaction_preserves_compact_json_after_url():
    process = type("Process", (), {
        "returncode": 1,
        "stdout": "",
        "stderr": (
            'MCP tool call failed: {"url":"https://signed.example/input?token=secret",'
            '"error":"tail_image is not accepted"}'
        ),
    })()
    with patch("harness.models.kling_video.subprocess.run", return_value=process):
        with pytest.raises(RuntimeError) as error:
            KlingVideoModel()._run(["image_to_video"])
    message = str(error.value)
    assert "tail_image is not accepted" in message
    assert "signed.example" not in message
    assert "secret" not in message


def test_poll_timeout_preserves_submission_and_blocks_second_paid_call(tmp_path: Path):
    import json
    import subprocess
    model = KlingVideoModel()
    req = request(tmp_path, "kling-video-v3_0_omni")
    with patch.object(model, "_run", side_effect=[
        {"generation_id": "test-existing-job"},
        subprocess.TimeoutExpired("query_tasks", 1),
    ]) as run:
        with pytest.raises(subprocess.TimeoutExpired):
            model.create(req)
        record = json.loads(req.output.with_suffix(".submission.json").read_text())
        assert record["generation_id"] == "test-existing-job"
        assert record["training_eligible"] is False
        assert not req.output.exists()
        assert not req.output.with_suffix(".receipt.json").exists()
        with pytest.raises(FileExistsError):
            model.create(req)
        assert run.call_count == 2
