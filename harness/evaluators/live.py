from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from harness.core.state import RunState
from harness.live import LiveProductionTimeline
from harness.renderers.common import ffmpeg_executable

from .base import Evaluator


def parse_silencedetect(output: str) -> list[dict[str, float]]:
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", output)]
    ends = [(float(end), float(duration)) for end, duration in re.findall(
        r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", output,
    )]
    return [
        {"start": start, "end": end, "duration": duration}
        for start, (end, duration) in zip(starts, ends)
    ]


def detect_audio_silence(path: Path, *, threshold_db: float = -42.0, min_duration: float = 0.12) -> list[dict[str, float]]:
    process = subprocess.run([
        ffmpeg_executable(), "-hide_banner", "-i", str(path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_duration}", "-f", "null", "-",
    ], check=False, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError((process.stderr or process.stdout)[-1600:])
    return parse_silencedetect(process.stderr)


def probe_video(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False}
    executable = ffmpeg_executable()
    probe = str(Path(executable).with_name("ffprobe"))
    if not Path(probe).is_file():
        process = subprocess.run([executable, "-hide_banner", "-i", str(path)], check=False, capture_output=True, text=True)
        output = process.stderr
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", output)
        video_match = re.search(r"Video: ([^,]+).*?, (\d+)x(\d+).*?, ([0-9.]+) fps", output)
        audio_match = re.search(r"Audio: ([^,]+), (\d+) Hz, ([^,]+)", output)
        duration = 0.0
        if duration_match:
            duration = int(duration_match[1]) * 3600 + int(duration_match[2]) * 60 + float(duration_match[3])
        return {
            "exists": True, "width": int(video_match[2]) if video_match else None,
            "height": int(video_match[3]) if video_match else None,
            "fps": video_match[4] if video_match else None, "duration": duration,
            "codec": video_match[1].strip() if video_match else None,
            "video_stream_count": 1 if video_match else 0,
            "audio_stream_count": 1 if audio_match else 0,
            "audio_codec": audio_match[1].strip() if audio_match else None,
            "audio_sample_rate": int(audio_match[2]) if audio_match else None,
            "audio_channel_layout": audio_match[3].strip() if audio_match else None,
            "probe_backend": "ffmpeg_stderr",
        }
    process = subprocess.run([
        probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ], check=False, capture_output=True, text=True)
    if process.returncode:
        return {"exists": True, "probe_error": process.stderr[-800:]}
    payload = json.loads(process.stdout)
    streams = payload.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video = video_streams[0] if video_streams else {}
    audio = audio_streams[0] if audio_streams else {}
    return {
        "exists": True, "width": video.get("width"), "height": video.get("height"),
        "fps": video.get("avg_frame_rate"), "duration": float(payload.get("format", {}).get("duration", 0)),
        "codec": video.get("codec_name"),
        "video_stream_count": len(video_streams), "audio_stream_count": len(audio_streams),
        "audio_codec": audio.get("codec_name"), "audio_channels": audio.get("channels"),
        "audio_channel_layout": audio.get("channel_layout"),
        "audio_sample_rate": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
    }


class CameraVideoEvaluator(Evaluator):
    def __init__(
        self, path: Path, *, expected_duration: float,
        expected_resolution: tuple[int, int], expected_audio: bool = False,
    ) -> None:
        self.path = path
        self.expected_duration = expected_duration
        self.expected_resolution = expected_resolution
        self.expected_audio = expected_audio

    def evaluate(self, state: RunState) -> dict[str, Any]:
        probe = probe_video(self.path)
        checks = {
            "decodes": probe.get("exists") and not probe.get("probe_error"),
            "duration": abs(probe.get("duration", 0) - self.expected_duration) <= 0.25,
            "resolution": (probe.get("width"), probe.get("height")) == self.expected_resolution,
            "audio_stream": not self.expected_audio or probe.get("audio_stream_count", 0) > 0,
        }
        return {"passed": all(checks.values()), "checks": checks, "probe": probe, "human_review_required": ["identity", "hands", "product geometry", "motion physics"]}


class AudioContinuityEvaluator(Evaluator):
    def __init__(
        self, path: Path, *, threshold_db: float = -42.0, min_duration: float = 0.12,
        max_dead_air_seconds: float = 0.75,
    ) -> None:
        self.path = path
        self.threshold_db = threshold_db
        self.min_duration = min_duration
        self.max_dead_air_seconds = max_dead_air_seconds

    def evaluate(self, state: RunState) -> dict[str, Any]:
        intervals = detect_audio_silence(
            self.path, threshold_db=self.threshold_db, min_duration=self.min_duration,
        )
        violations = [item for item in intervals if item["duration"] >= self.max_dead_air_seconds]
        return {
            "passed": not violations,
            "threshold_db": self.threshold_db,
            "min_duration": self.min_duration,
            "max_dead_air_seconds": self.max_dead_air_seconds,
            "silence_intervals": intervals,
            "violations": violations,
            "human_review_required": ["speech cadence", "segment-join naturalness", "SFX relevance"],
        }


class OverlayEvaluator(Evaluator):
    def __init__(self, manifest: Path, *, expected_comments: int, expected_vfx: int | None = None) -> None:
        self.manifest = manifest
        self.expected_comments = expected_comments
        self.expected_vfx = expected_vfx

    def evaluate(self, state: RunState) -> dict[str, Any]:
        if not self.manifest.is_file():
            return {"passed": False, "failures": ["missing_manifest"]}
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        checks = {"training_locked": payload.get("training_eligible") is False}
        if self.expected_vfx is None:
            checks.update({
                "comments_complete": len(payload.get("comment_event_ids", [])) == self.expected_comments,
                "disclosure_present": payload.get("disclosure_present") is True,
                "static_ui_drift_zero": payload.get("static_ui_pixel_drift_expected") == 0,
            })
        else:
            event_count = len(payload.get("events", payload.get("vfx_event_ids", [])))
            checks["vfx_complete"] = event_count == self.expected_vfx
        return {"passed": all(checks.values()), "checks": checks}


class TimelineNarrativeEvaluator(Evaluator):
    def __init__(self, timeline: LiveProductionTimeline) -> None:
        self.timeline = timeline

    def evaluate(self, state: RunState) -> dict[str, Any]:
        comments = {event["id"]: event for event in self.timeline.tracks.get("comments", [])}
        responses = [event for track in ("camera", "speech") for event in self.timeline.tracks.get(track, []) if event.get("responds_to")]
        checks = {
            "responses_have_comments": bool(responses) and all(event["responds_to"] in comments for event in responses),
            "responses_are_later": all(float(event["start"]) >= float(comments[event["responds_to"]].get("time", comments[event["responds_to"]].get("start", 0))) for event in responses),
            "symbolic_tracks_not_model_owned": all(not event.get("model_owned", False) for track in ("comments", "ui", "vfx", "subtitles") for event in self.timeline.tracks.get(track, [])),
        }
        return {"passed": all(checks.values()), "checks": checks, "response_links": [{"event": event["id"], "responds_to": event["responds_to"]} for event in responses]}
