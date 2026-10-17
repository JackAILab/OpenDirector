from __future__ import annotations

import subprocess
from pathlib import Path

from harness.renderers.common import ffmpeg_executable


def compose_live_video(
    *, camera_video: Path, ui_overlay: Path, vfx_overlay: Path | None, output: Path,
    audio: Path | None = None, width: int = 1080, height: int = 1920, fps: int = 30,
) -> Path:
    for path in (camera_video, ui_overlay, vfx_overlay, audio):
        if path is not None and not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite composed video: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["-i", str(camera_video), "-i", str(ui_overlay)]
    filters = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}[camera]", "[camera][1:v]overlay=0:0:format=auto[layer1]"]
    current = "layer1"
    input_count = 2
    if vfx_overlay:
        inputs += ["-i", str(vfx_overlay)]
        filters.append(f"[{current}][{input_count}:v]overlay=0:0:format=auto[layer2]")
        current = "layer2"
        input_count += 1
    if audio:
        inputs += ["-i", str(audio)]
        audio_map = ["-map", f"{input_count}:a:0", "-c:a", "aac", "-b:a", "192k"]
    else:
        audio_map = ["-an"]
    command = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", ";".join(filters), "-map", f"[{current}]", *audio_map,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-shortest", str(output),
    ]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg composition failed: {process.stderr[-1600:]}")
    return output
