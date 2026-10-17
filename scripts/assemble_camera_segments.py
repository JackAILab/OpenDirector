#!/usr/bin/env python3
"""Deterministically trim paid sources and assemble a configured camera feed."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.compositor import concatenate_camera_segments, trim_camera_segment


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_existing_trim(
    source: Path, output: Path, *, duration: float, fps: int, preserve_audio: bool,
) -> bool:
    record_path = output.with_suffix(".assembly.json")
    if not output.exists() and not record_path.exists():
        return False
    if not output.is_file() or not record_path.is_file():
        raise FileExistsError(f"incomplete existing trim record: {output}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    expected = (
        record.get("source", {}).get("sha256") == _sha256(source)
        and record.get("output", {}).get("sha256") == _sha256(output)
        and float(record.get("trim_out", -1)) == duration
        and int(record.get("fps", -1)) == fps
        and bool(record.get("audio_preserved")) == preserve_audio
    )
    if not expected:
        raise FileExistsError(f"existing trim does not match current source or parameters: {output}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks/jensen_rubin_live_30s_v2.segments.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    root = ROOT / "outputs/artifacts" / config["case_id"] / "camera_segments"
    parameters = config.get("parameters", {})
    source_duration = float(config.get("source_duration_seconds", parameters.get("duration_seconds_per_segment", 8)))
    trim_duration = float(config.get("assembled_duration_seconds", source_duration))
    preserve_audio = bool(config.get("enable_audio", parameters.get("enable_audio", False)))
    trimmed: list[Path] = []
    reused: list[Path] = []
    for segment in config["segments"]:
        declared_source = segment.get("source", segment.get("output"))
        source = ROOT / declared_source if declared_source else root / f"{segment['id']}.source-{source_duration:g}s.mp4"
        output_name = source.name.replace(f".source-{source_duration:g}s.mp4", f".trim-{trim_duration:g}s.mp4")
        if output_name == source.name:
            output_name = f"{segment['id']}.trim-{trim_duration:g}s.mp4"
        output = source.parent / output_name
        if _verified_existing_trim(source, output, duration=trim_duration, fps=30, preserve_audio=preserve_audio):
            reused.append(output)
        else:
            trim_camera_segment(
                source, output, duration=trim_duration, fps=30,
                preserve_audio=preserve_audio,
            )
        trimmed.append(output)
    camera = ROOT / config.get(
        "assembly_output",
        f"outputs/artifacts/{config['case_id']}/camera/camera_feed_30s.mp4",
    )
    concatenate_camera_segments(trimmed, camera, fps=30, include_audio=preserve_audio)
    print(json.dumps({
        "segments": [str(path) for path in trimmed],
        "reused_verified_segments": [str(path) for path in reused],
        "camera": str(camera),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
