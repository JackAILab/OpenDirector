#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.renderers.common import ffmpeg_executable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_mix(source: Path, output: Path, *, duration: float = 60.0) -> Path:
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite audio artifact: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = (
        f"[0:a]aresample=48000,highpass=f=55,volume=0.92[voice];"
        f"anoisesrc=d={duration}:c=pink:r=48000:a=0.028,highpass=f=85,lowpass=f=1450,volume=0.55[room];"
        "sine=f=620:d=1.08:r=48000,afade=t=in:d=0.03,afade=t=out:st=0.22:d=0.86,volume=0.16,adelay=24680|24680[card1];"
        "sine=f=760:d=0.96:r=48000,afade=t=in:d=0.03,afade=t=out:st=0.20:d=0.76,volume=0.15,adelay=32680|32680[card2];"
        "anoisesrc=d=0.72:c=white:r=48000:a=0.02,highpass=f=700,lowpass=f=5200,afade=t=in:d=0.04,afade=t=out:st=0.22:d=0.50,adelay=21400|21400[car1];"
        "anoisesrc=d=0.72:c=white:r=48000:a=0.02,highpass=f=700,lowpass=f=5200,afade=t=in:d=0.04,afade=t=out:st=0.22:d=0.50,adelay=48600|48600[car2];"
        "[voice][room][card1][card2][car1][car2]amix=inputs=6:duration=first:normalize=0,alimiter=limit=0.891:attack=5:release=80[out]"
    )
    command = [
        ffmpeg_executable(), "-hide_banner", "-y", "-i", str(source),
        "-filter_complex", filters, "-map", "[out]", "-t", str(duration),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(output),
    ]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(process.stderr[-2400:])
    manifest = {
        "schema": "visualagent.live-audio-mix.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": source.name, "sha256": sha256(source)},
        "output": {"name": output.name, "sha256": sha256(output)},
        "strategy": "native voice + continuous low-level room tone + event-linked SFX bridges",
        "dialogue_timing_changed": False,
        "dead_air_bridges": [[24.7, 25.8, "commerce confirmation"], [32.7, 33.6, "connection-card confirmation"]],
        "gift_sfx": [[21.4, "car pass"], [48.6, "car pass"]],
        "training_eligible": False,
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()
    print(build_mix(args.source.resolve(), args.output.resolve(), duration=args.duration))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
