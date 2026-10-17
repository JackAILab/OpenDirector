from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from harness.renderers.common import ffmpeg_executable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trim_camera_segment(
    source: Path, output: Path, *, duration: float = 7.5, fps: int = 30,
    preserve_audio: bool = False,
) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists() or output.with_suffix(".assembly.json").exists():
        raise FileExistsError(f"refusing to overwrite trimmed segment: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_args = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if preserve_audio else ["-an"]
    command = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-t", str(duration), "-map", "0:v:0", *audio_args, "-vf", f"fps={fps}", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(output),
    ]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"segment trim failed: {process.stderr[-1200:]}")
    output.with_suffix(".assembly.json").write_text(json.dumps({
        "schema": "visualagent.camera-segment-assembly.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": source.name, "sha256": _sha256(source)},
        "trim_in": 0.0, "trim_out": duration, "assembled_duration": duration,
        "fps": fps, "audio_preserved": preserve_audio,
        "output": {"name": output.name, "sha256": _sha256(output)},
        "semantic_content_changed": False, "paid_call": False, "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def concatenate_camera_segments(
    sources: list[Path], output: Path, *, fps: int = 30, include_audio: bool = False,
) -> Path:
    if len(sources) < 2:
        raise ValueError("at least two camera segments are required")
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    if output.exists() or output.with_suffix(".assembly.json").exists():
        raise FileExistsError(f"refusing to overwrite camera assembly: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    for index, source in enumerate(sources):
        inputs.extend(["-i", str(source)])
        filters.append(f"[{index}:v]fps={fps},setpts=PTS-STARTPTS[v{index}]")
        if include_audio:
            filters.append(f"[{index}:a]aresample=48000,asetpts=PTS-STARTPTS[a{index}]")
    if include_audio:
        joined = "".join(f"[v{index}][a{index}]" for index in range(len(sources)))
        filters.append(f"{joined}concat=n={len(sources)}:v=1:a=1[outv][outa]")
        audio_map = ["-map", "[outa]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        joined = "".join(f"[v{index}]" for index in range(len(sources)))
        filters.append(f"{joined}concat=n={len(sources)}:v=1:a=0[outv]")
        audio_map = ["-an"]
    command = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[outv]", *audio_map,
        "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", str(output),
    ]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"segment assembly failed: {process.stderr[-1200:]}")
    output.with_suffix(".assembly.json").write_text(json.dumps({
        "schema": "visualagent.camera-feed-assembly.v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "fps": fps, "audio_included": include_audio,
        "segments": [{"order": index, "name": path.name, "sha256": _sha256(path)} for index, path in enumerate(sources)],
        "output": {"name": output.name, "sha256": _sha256(output)},
        "paid_call": False, "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
