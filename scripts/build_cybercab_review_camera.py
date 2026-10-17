#!/usr/bin/env python3
"""Build a non-overwriting 60s Cybercab review camera feed with an audited deterministic gap bridge."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.compositor import concatenate_camera_segments, trim_camera_segment
from harness.renderers.common import ffmpeg_executable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    case = ROOT / "outputs/artifacts/cybercab_live_60s_v1"
    segments = case / "camera_segments"
    first = case / "reference_states/state-30-000.png"
    last = case / "reference_states/state-45-000.png"
    bridge = segments / "seg-30-45.deterministic-bridge-15s.mp4"
    bridge_record = bridge.with_suffix(".repair.json")
    if bridge.exists() or bridge_record.exists():
        raise FileExistsError("refusing to overwrite deterministic bridge")
    command = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", "15", "-i", str(first),
        "-loop", "1", "-t", "15", "-i", str(last),
        "-f", "lavfi", "-t", "15", "-i", "anullsrc=r=48000:cl=stereo",
        "-filter_complex",
        "[0:v]scale=1080:1920,fps=30,setsar=1[v0];"
        "[1:v]scale=1080:1920,fps=30,setsar=1[v1];"
        "[v0][v1]xfade=transition=fade:duration=15:offset=0,format=yuv420p[outv]",
        "-map", "[outv]", "-map", "2:a:0", "-t", "15", "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", str(bridge),
    ]
    bridge.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode:
        bridge.unlink(missing_ok=True)
        raise RuntimeError(process.stderr[-1600:])
    bridge_record.write_text(json.dumps({
        "schema": "visualagent.deterministic-gap-bridge.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": "paid segment completed but could not be retained after shared filesystem ENOSPC",
        "inputs": [{"name": first.name, "sha256": sha256(first)}, {"name": last.name, "sha256": sha256(last)}],
        "output": {"name": bridge.name, "sha256": sha256(bridge), "duration": 15},
        "method": "full-duration linear crossfade with silent stereo continuity bed",
        "paid_call": False, "provider_generation_replacement": False,
        "semantic_continuity_proven": False, "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sources = [
        segments / "seg-00-15.source-15s.mp4",
        segments / "seg-15-30.source-15s.mp4",
        bridge,
        segments / "seg-45-60.source-15s.mp4",
    ]
    trims = []
    for source in sources:
        target = segments / f"{source.stem}.trim-15s.mp4"
        trim_camera_segment(source, target, duration=15, fps=30, preserve_audio=True)
        trims.append(target)
    output = case / "camera/camera_feed_60s-review-v1.mp4"
    concatenate_camera_segments(trims, output, fps=30, include_audio=True)
    print(json.dumps({"bridge": str(bridge), "camera": str(output), "training_eligible": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
