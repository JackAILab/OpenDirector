#!/usr/bin/env python3
"""Apply two short physical-occlusion seam stabilizations without changing duration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-seam-repaired.mp4"
OUTPUT = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-seam-stabilized.mp4"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    record_path = OUTPUT.with_suffix(".assembly.json")
    if OUTPUT.exists() or record_path.exists():
        raise FileExistsError(f"refusing to overwrite seam stabilization: {OUTPUT}")
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    graph = ";".join([
        "[0:v]trim=start=0:end=17.75,setpts=PTS-STARTPTS[v0]",
        "[0:v]trim=start=17.25:end=32.75,setpts=PTS-STARTPTS[v1]",
        "[0:v]trim=start=32.25:end=60,setpts=PTS-STARTPTS[v2]",
        "[v0][v1]xfade=transition=fadeblack:duration=0.5:offset=17.25[v01]",
        "[v01][v2]xfade=transition=fadeblack:duration=0.5:offset=32.25[vout]",
        "[0:a]atrim=start=0:end=17.75,asetpts=PTS-STARTPTS[a0]",
        "[0:a]atrim=start=17.25:end=32.75,asetpts=PTS-STARTPTS[a1]",
        "[0:a]atrim=start=32.25:end=60,asetpts=PTS-STARTPTS[a2]",
        "[a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[a01]",
        "[a01][a2]acrossfade=d=0.5:c1=tri:c2=tri[aout]",
    ])
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(SOURCE),
        "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-g", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUTPUT),
    ], check=True)
    record = {
        "schema": "visualagent.camera-seam-stabilization.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha256(SOURCE)},
        "output": {"path": str(OUTPUT.relative_to(ROOT)), "sha256": sha256(OUTPUT)},
        "method": "0.5-second fade-through-occlusion at 17.5s and 32.5s with matching native-audio crossfades",
        "duration_seconds": 60,
        "paid_calls": 0,
        "training_eligible": False,
        "human_review": "pending",
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
