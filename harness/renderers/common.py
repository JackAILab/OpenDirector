from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image


def ffmpeg_executable() -> str:
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        bundled = Path("/opt/visualstation/creative-runtime/bin/ffmpeg")
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return str(bundled)
        discovered = shutil.which("ffmpeg")
        if discovered:
            return discovered
        raise RuntimeError("ffmpeg not found; set FFMPEG_BINARY or install imageio-ffmpeg")


def encode_rgba_track(
    output: Path, *, width: int, height: int, fps: int, duration: float,
    frame_factory: Callable[[float], Image.Image],
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite rendered track: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", f"{width}x{height}",
        "-framerate", str(fps), "-i", "-", "-an", "-c:v", "qtrle",
        "-pix_fmt", "argb", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.stdin is not None
        for index in range(round(duration * fps)):
            frame = frame_factory(index / fps).convert("RGBA")
            if frame.size != (width, height):
                raise ValueError("renderer returned frame with unexpected dimensions")
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        code = process.wait()
        if code:
            raise RuntimeError(f"ffmpeg overlay encoding failed: {error[-1200:]}")
    except Exception:
        process.kill()
        output.unlink(missing_ok=True)
        raise
