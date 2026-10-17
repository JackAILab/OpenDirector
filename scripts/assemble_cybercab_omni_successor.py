#!/usr/bin/env python3
"""Assemble the 60-second Cybercab Omni successor with three seam clips.

All seven inputs remain immutable. The output is a new deterministic composite
that keeps native audio and records its exact source ranges.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-seam-repaired.mp4"

PARTS = [
    ("camera_segments/seg-00-15-omni-native-av-v2.source-15s.mp4", 0.0, 12.5, "base-00"),
    ("camera_transitions/seam-15-omni-v1.source-5s.mp4", 0.0, 5.0, "seam-15"),
    ("camera_segments/seg-15-30-omni-native-av-v2.source-15s.mp4", 2.5, 12.5, "base-15"),
    ("camera_transitions/seam-30-omni-v1.source-5s.mp4", 0.0, 5.0, "seam-30"),
    ("camera_segments/seg-30-45-omni-native-av-v2.source-15s.mp4", 2.5, 12.5, "base-30"),
    ("camera_transitions/seam-45-omni-v1.source-5s.mp4", 0.0, 5.0, "seam-45"),
    ("camera_segments/seg-45-60-omni-native-av-v2.source-15s.mp4", 2.5, 15.0, "base-45"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if OUTPUT.exists() or OUTPUT.with_suffix(".assembly.json").exists():
        raise FileExistsError(f"refusing to overwrite successor assembly: {OUTPUT}")
    base = ROOT / "outputs/artifacts/cybercab_live_60s_v2"
    resolved = [(base / relative, start, end, role) for relative, start, end, role in PARTS]
    missing = [str(path) for path, _, _, _ in resolved if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing successor inputs: {missing}")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for path, _, _, _ in resolved:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (_, start, end, _) in enumerate(resolved):
        duration = end - start
        filters.append(
            f"[{index}:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,format=yuv420p"
            f"[v{index}]"
        )
        filters.append(
            f"[{index}:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS,"
            "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            f"[a{index}]"
        )
        concat_inputs.extend([f"[v{index}]", f"[a{index}]"])
    filters.append("".join(concat_inputs) + f"concat=n={len(resolved)}:v=1:a=1[v][a]")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-g", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUTPUT),
    ])
    subprocess.run(command, check=True)
    record = {
        "schema": "visualagent.camera-seam-repaired-assembly.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "seven-part deterministic trim/concat with native audio preserved",
        "sources": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "trim_start": start,
                "trim_end": end,
                "duration": end - start,
                "role": role,
            }
            for path, start, end, role in resolved
        ],
        "output": {
            "path": str(OUTPUT.relative_to(ROOT)),
            "sha256": sha256(OUTPUT),
            "duration_seconds": 60,
            "audio_preserved": True,
        },
        "training_eligible": False,
        "human_review": "pending",
    }
    OUTPUT.with_suffix(".assembly.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
