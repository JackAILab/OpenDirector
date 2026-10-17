#!/usr/bin/env python3
"""Replace only the final 12.5 seconds with the reviewed Omni departure repair."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-seam-repaired.mp4"
REPAIR = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera_repairs/departure-47_5-60-omni-v1.source-15s.mp4"
OUTPUT = ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-departure-repaired.mp4"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    record_path = OUTPUT.with_suffix(".assembly.json")
    if OUTPUT.exists() or record_path.exists():
        raise FileExistsError(f"refusing to overwrite departure repair: {OUTPUT}")
    if not BASE.is_file() or not REPAIR.is_file():
        raise FileNotFoundError("base camera or departure repair is missing")
    graph = ";".join([
        "[0:v]trim=start=0:end=47.5,setpts=PTS-STARTPTS,fps=30,format=yuv420p[v0]",
        "[1:v]trim=start=0:duration=12.5,setpts=PTS-STARTPTS,fps=30,format=yuv420p[v1]",
        "[0:a]atrim=start=0:end=47.5,asetpts=PTS-STARTPTS,aresample=48000[a0]",
        "[1:a]atrim=start=0:duration=12.5,asetpts=PTS-STARTPTS,aresample=48000[a1]",
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
    ])
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(BASE), "-i", str(REPAIR),
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-g", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUTPUT),
    ], check=True)
    record = {
        "schema": "visualagent.camera-departure-repair-assembly.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {"path": str(BASE.relative_to(ROOT)), "sha256": sha256(BASE), "range": [0, 47.5]},
            {"path": str(REPAIR.relative_to(ROOT)), "sha256": sha256(REPAIR), "range": [0, 12.5]},
        ],
        "output": {"path": str(OUTPUT.relative_to(ROOT)), "sha256": sha256(OUTPUT), "duration_seconds": 60},
        "native_audio_preserved": True,
        "paid_calls": 0,
        "training_eligible": False,
        "human_review": "pending",
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
