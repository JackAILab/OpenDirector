from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from harness.live.timeline import LiveProductionTimeline

LayerMode = Literal["ui", "vfx", "review"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _static_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def _render_environment() -> dict[str, str]:
    env = os.environ.copy()
    ffmpeg = env.get("HYPERFRAMES_FFMPEG_PATH") or _static_ffmpeg()
    if ffmpeg:
        env["HYPERFRAMES_FFMPEG_PATH"] = ffmpeg
        # A static ffmpeg binary also supports ffprobe syntax. This avoids a
        # broken host ffprobe from blocking compositions without source video.
        env.setdefault("HYPERFRAMES_FFPROBE_PATH", ffmpeg)
    return env


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> str:
    process = subprocess.run(
        command, cwd=cwd, env=env, check=False, capture_output=True, text=True,
        timeout=timeout,
    )
    if process.returncode:
        message = (process.stderr or process.stdout).strip()
        raise RuntimeError(f"HyperFrames command failed ({process.returncode}): {message[-2400:]}")
    return (process.stdout or process.stderr).strip()


def render_hyperframes_layer(
    timeline: LiveProductionTimeline,
    output: Path,
    *,
    project: Path,
    layer_mode: LayerMode,
    fps: int = 30,
    quality: str = "high",
    workers: int = 4,
    timeout_seconds: int = 1800,
) -> Path:
    """Render a seek-safe professional live layer through HyperFrames.

    UI and VFX modes produce transparent WebM artifacts. Review mode is an
    explicitly non-deliverable MP4 with the layout reference underneath.
    """
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite HyperFrames artifact: {output}")
    if layer_mode not in {"ui", "vfx", "review"}:
        raise ValueError(f"unsupported layer mode: {layer_mode}")
    project = project.resolve()
    design = project / "DESIGN.md"
    source = project / "index.html"
    if not design.is_file() or not source.is_file():
        raise FileNotFoundError("HyperFrames project requires DESIGN.md and index.html")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    env = _render_environment()
    _run(["npx", "hyperframes", "check"], cwd=project, env=env, timeout=300)
    variables = json.dumps({"layerMode": layer_mode}, separators=(",", ":"))
    command = [
        "npx", "hyperframes", "render", "--output", str(output),
        "--fps", str(fps), "--quality", quality, "--workers", str(workers),
        "--variables", variables, "--strict-all",
    ]
    if layer_mode in {"ui", "vfx"}:
        command.extend(["--format", "webm"])
    _run(command, cwd=project, env=env, timeout=timeout_seconds)
    if not output.is_file() or output.stat().st_size < 1024:
        raise RuntimeError("HyperFrames completed without a valid artifact")
    manifest = {
        "schema": "visualagent.hyperframes-layer-manifest.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layer": layer_mode,
        "renderer": "HyperFrames HTML/CSS/SVG/GSAP",
        "duration": timeline.duration,
        "fps": fps,
        "resolution": [1080, 1920],
        "source_sha256": _sha256(source),
        "design_sha256": _sha256(design),
        "artifact_sha256": _sha256(output),
        "artifact_bytes": output.stat().st_size,
        "comment_event_ids": [event["id"] for event in timeline.tracks.get("comments", [])] if layer_mode in {"ui", "review"} else [],
        "ui_event_ids": [event["id"] for event in timeline.tracks.get("ui", [])] if layer_mode in {"ui", "review"} else [],
        "vfx_event_ids": [event["id"] for event in timeline.tracks.get("vfx", [])] if layer_mode in {"vfx", "review"} else [],
        "disclosure_present": bool(timeline.payload.get("disclosure")) if layer_mode in {"ui", "review"} else False,
        "static_ui_pixel_drift_expected": 0 if layer_mode in {"ui", "review"} else None,
        "review_only": layer_mode == "review",
        "dynamic_camera_feed_present": False if layer_mode == "review" else None,
        "training_eligible": False,
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return output
