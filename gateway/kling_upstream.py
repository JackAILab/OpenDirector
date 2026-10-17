"""Local Kling-backed upstream for the port-forwarded studio.

Each POST is one explicit paid submission. There is no retry and no model
substitution. Provider payloads and temporary URLs stay in process memory only.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

CLI = os.getenv("KLING_CLI", "kling")
REFERENCE = Path(os.getenv("KLING_REFERENCE_IMAGE", ""))
OUTPUT_DIR = Path(os.getenv("KLING_OUTPUT_DIR", "/tmp/visualstation-kling"))
MODEL = os.getenv("KLING_MODEL", "kling-video-v3_0")
JOBS: dict[str, dict[str, object]] = {}
ACTIVE = False
app = FastAPI(title="Local Kling upstream")


def state_path(job_id: str) -> Path:
    return OUTPUT_DIR / f"{job_id}.state.json"


def persist(job_id: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    destination = state_path(job_id)
    # A crash must leave either the old complete record or the new one.
    fd, temporary = tempfile.mkstemp(prefix=destination.name + ".", dir=OUTPUT_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(JOBS[job_id], stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_states() -> None:
    for path in OUTPUT_DIR.glob("kling_*.state.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            job_id = job.get("id")
            if not isinstance(job_id, str):
                continue
            if job.get("status") == "processing":
                job.update(status="failed", error="Kling worker restarted before completion; no retry issued")
                path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            JOBS[job_id] = job
        except (OSError, ValueError):
            continue


if not os.getenv("CREATIVE_STUDIO_ROOT"):
    load_states()


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "kling", "active": ACTIVE}


def generation_args(body: dict) -> list[str]:
    if body.get("task") != "t2va":
        raise HTTPException(422, "Kling studio currently supports text-to-video only")
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(422, "prompt is required")
    if body.get("conditions") or body.get("seed") is not None:
        raise HTTPException(422, "Kling text-to-video does not support conditions or seed")
    target = body.get("target", {})
    if not isinstance(target, dict):
        raise HTTPException(422, "target must be an object")
    if set(target) - {"duration_seconds", "short_edge", "aspect_ratio"}:
        raise HTTPException(422, "Unsupported Kling target parameter")
    duration = target.get("duration_seconds", 5)
    edge = target.get("short_edge", 720)
    aspect = target.get("aspect_ratio", "16:9")
    if type(duration) is not int or not 3 <= duration <= 15:
        raise HTTPException(422, "duration_seconds must be an integer from 3 to 15")
    if type(edge) is not int or edge not in {720, 1080}:
        raise HTTPException(422, "short_edge must be 720 or 1080 for Kling")
    if not isinstance(aspect, str) or aspect not in {"16:9", "9:16", "1:1"}:
        raise HTTPException(422, "Unsupported aspect_ratio")
    model = body.get("model") or MODEL
    if model not in {"kling-video-v2_5", "kling-video-v3_0", "kling-video-v3_0_omni"}:
        raise HTTPException(422, "Requested Kling model is not enabled")
    if model == "kling-video-v2_5" and duration not in {5,10}:
        raise HTTPException(422, "Kling 2.5 supports 5 or 10 seconds")
    return [CLI, "text_to_video", "--model", model,
            "--duration", str(duration), "--resolution", f"{edge}p",
            "--aspect_ratio", aspect, "--imageCount", "1",
            *(["--prefer_multi_shots", "false"] if model != "kling-video-v2_5" else []),
            "--enable_audio", "false",
            "--skill-name", "visualstation-local", "--skill-version", "0.1.0",
            "--poll", os.getenv("KLING_POLL_SECONDS", "240"), "--quiet", prompt.strip()]


def run_generation(job_id: str, args: list[str]) -> None:
    global ACTIVE
    output = OUTPUT_DIR / f"{job_id}.mp4"
    try:
        process = subprocess.run(args, check=False, capture_output=True, text=True,
                                 timeout=int(os.getenv("KLING_PROCESS_TIMEOUT", "360")))
        if process.returncode:
            raise RuntimeError("Kling submission failed")
        payload = None
        for line in reversed(process.stdout.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("ok") is True:
                payload = candidate
                break
        if not payload:
            raise RuntimeError("Kling returned no structured result")
        body = payload.get("body", {})
        work = body.get("generations", [{}])[0].get("result", {}).get("works", [{}])[0]
        url = work.get("urlWithoutWatermark") or work.get("url_without_watermark")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise RuntimeError("Kling completed without a video URL")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=600) as response:
            output.write_bytes(response.read())
        if output.stat().st_size < 1024:
            raise RuntimeError("Kling result is unexpectedly small")
        JOBS[job_id].update(status="completed", output=str(output))
        persist(job_id)
    except Exception as exc:
        output.unlink(missing_ok=True)
        JOBS[job_id].update(status="failed", error=str(exc))
        persist(job_id)
    finally:
        ACTIVE = False


@app.post("/v1/videos")
async def create(body: dict):
    global ACTIVE
    args = generation_args(body)
    if ACTIVE:
        raise HTTPException(429, "Kling worker is busy", headers={"Retry-After": "15"})
    if not shutil_which(CLI):
        raise HTTPException(503, "Kling CLI is not available")
    job_id = "kling_" + secrets.token_hex(8)
    JOBS[job_id] = {"id": job_id, "status": "processing"}
    persist(job_id)
    ACTIVE = True
    asyncio.create_task(asyncio.to_thread(run_generation, job_id, args))
    return {"id": job_id, "status": "processing", "provider": "kling"}


def shutil_which(command: str) -> str | None:
    import shutil
    return shutil.which(command)


@app.get("/v1/videos/{job_id}")
async def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Video not found")
    return {key: value for key, value in job.items() if key != "output"}


@app.get("/v1/videos/{job_id}/content")
async def content(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Video not found")
    if job.get("status") != "completed":
        raise HTTPException(409, "Video is not completed")
    return FileResponse(str(job["output"]), media_type="video/mp4", filename=f"{job_id}.mp4")


# AdvertiseAgent owns the durable provider adapter when the creative service is enabled.
if os.getenv("CREATIVE_STUDIO_ROOT"):
    import sys
    sys.path.insert(0, os.environ["CREATIVE_STUDIO_ROOT"])
    from harness.models.kling_studio import app
