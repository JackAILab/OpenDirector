from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.live import LiveProductionTimeline
from harness.renderers.common import ffmpeg_executable


def render_speech_track(
    timeline: LiveProductionTimeline, output: Path, *, voice: str = "zh-CN-YunxiNeural",
    rate: str = "+12%", edge_tts_executable: str = "edge-tts",
) -> Path:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite speech track: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    turns_dir = output.parent / f"{output.stem}.turns"
    turns_dir.mkdir(parents=True, exist_ok=True)
    turns: list[tuple[dict, Path]] = []
    for event in timeline.tracks.get("speech", []):
        turn = turns_dir / f"{event['id']}.mp3"
        if turn.exists():
            raise FileExistsError(f"refusing to overwrite speech turn: {turn}")
        process = subprocess.run([
            edge_tts_executable, "--voice", voice, "--rate", rate,
            "--text", str(event["text"]), "--write-media", str(turn),
        ], check=False, capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError(f"edge-tts failed: {process.stderr[-1200:]}")
        turns.append((event, turn))
    if not turns:
        raise ValueError("speech track has no events")
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for index, (event, turn) in enumerate(turns):
        inputs.extend(["-i", str(turn)])
        delay = round(float(event["start"]) * 1000)
        label = f"a{index}"
        filters.append(f"[{index}:a]adelay={delay}|{delay}[{label}]")
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,apad=pad_dur={timeline.duration}[mix]")
    process = subprocess.run([
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[mix]", "-t", str(timeline.duration),
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ], check=False, capture_output=True, text=True)
    if process.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"speech composition failed: {process.stderr[-1200:]}")
    output.with_suffix(".manifest.json").write_text(json.dumps({
        "schema": "visualagent.speech-track-manifest.v1", "layer": "audio",
        "duration": timeline.duration, "voice": voice, "voice_clone": False,
        "events": [{"id": event["id"], "start": event["start"], "end": event["end"], "responds_to": event.get("responds_to")} for event, _ in turns],
        "training_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
