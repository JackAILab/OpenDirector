import json
from pathlib import Path

import pytest

from harness.compositor.segments import concatenate_camera_segments, trim_camera_segment
from harness.evaluators.live import CameraVideoEvaluator


ROOT = Path(__file__).resolve().parents[1]


def test_trim_rejects_missing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        trim_camera_segment(tmp_path / "missing.mp4", tmp_path / "out.mp4")


def test_trim_refuses_to_overwrite(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "out.mp4"
    source.touch()
    output.touch()
    with pytest.raises(FileExistsError):
        trim_camera_segment(source, output)


def test_concatenate_requires_multiple_segments(tmp_path: Path):
    source = tmp_path / "one.mp4"
    source.touch()
    with pytest.raises(ValueError, match="at least two"):
        concatenate_camera_segments([source], tmp_path / "out.mp4")


def test_segment_assembly_api_requires_audio_to_be_explicit():
    import inspect

    trim_signature = inspect.signature(trim_camera_segment)
    concat_signature = inspect.signature(concatenate_camera_segments)
    assert trim_signature.parameters["preserve_audio"].default is False
    assert concat_signature.parameters["include_audio"].default is False


def test_concatenation_sets_the_output_frame_rate_explicitly():
    import inspect

    source = inspect.getsource(concatenate_camera_segments)
    assert '"-r", str(fps)' in source


def test_camera_evaluator_can_require_a_real_audio_stream(tmp_path: Path):
    evaluator = CameraVideoEvaluator(
        tmp_path / "missing.mp4", expected_duration=8,
        expected_resolution=(1080, 1920), expected_audio=True,
    )
    result = evaluator.evaluate(None)  # type: ignore[arg-type]
    assert result["checks"]["audio_stream"] is False


def test_30s_omni_segment_plan_enables_native_audio_without_named_likeness():
    config = json.loads((ROOT / "configs/tasks/jensen_rubin_live_30s_v2.segments.json").read_text(encoding="utf-8"))
    assert config["model"] == "kling-video-v3_0_omni"
    assert config["enable_audio"] is True
    assert config["prefer_multi_shots"] is False
    assert config["format_contract"] == {
        "orientation": "portrait",
        "aspect_ratio": "9:16",
        "expected_width": 1080,
        "expected_height": 1920,
        "preview_fit": "contain",
    }
    prompts = "\n".join(segment["prompt"] for segment in config["segments"])
    assert "黄仁勋" not in prompts
    assert prompts.count("不模仿任何真实人物") == len(config["segments"])


def test_vertical_lock_retry_is_explicit_and_uses_one_portrait_reference():
    config = json.loads((ROOT / "configs/tasks/jensen_rubin_live_30s_v2.omni-vertical-lock-03.json").read_text(encoding="utf-8"))
    segment = config["segments"][0]
    assert config["model"] == "kling-video-v3_0_omni"
    assert config["aspect_ratio"] == "9:16"
    assert config["format_contract"]["expected_width"] == 1080
    assert config["format_contract"]["expected_height"] == 1920
    assert config["enable_audio"] is True
    assert segment["attempt"] == 3
    assert segment["retry_of_run"] == "9b1e7aec03ac46268c2b14b7a158a739"
    assert "tail" not in segment
    assert "显卡长边始终与画面竖轴平行" in segment["prompt"]
    assert "禁止旋转成横向" in segment["prompt"]


def test_60s_plan_is_portrait_audio_enabled_and_avoids_named_likeness():
    config = json.loads((ROOT / "configs/tasks/jensen_rubin_live_60s_v1.segments.json").read_text(encoding="utf-8"))
    assert config["aspect_ratio"] == "9:16"
    assert config["enable_audio"] is True
    assert config["format_contract"]["expected_width"] == 1080
    assert config["format_contract"]["expected_height"] == 1920
    generated = [segment for segment in config["segments"] if "prompt" in segment]
    assert len(generated) == 4
    prompts = "\n".join(segment["prompt"] for segment in generated)
    assert "黄仁勋" not in prompts
    assert prompts.count("不模仿任何真实人物") == len(generated)
