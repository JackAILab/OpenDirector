"""Small local H3-shaped upstream for exercising the studio without GPUs.

This is intentionally separate from the gateway and is never used by a
production deployment. It returns an existing local MP4 after a short queue
delay while preserving the MiniMax-H3 request and response shape.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

VIDEO = Path(os.getenv("H3_DEV_VIDEO_PATH", ""))
JOBS: dict[str, dict[str, object]] = {}
app = FastAPI(title="Local H3 demo upstream")


@app.get("/health")
async def health():
    return {"status": "ok", "model": "MiniMax-H3-local-demo"}


async def complete(job_id: str) -> None:
    await asyncio.sleep(1)
    if job_id in JOBS:
        JOBS[job_id]["status"] = "completed"


@app.post("/v1/videos")
async def create(body: dict):
    if body.get("task") not in {"t2va", "fl2va", "ref2va"}:
        raise HTTPException(422, "task must be t2va, fl2va, or ref2va")
    if not body.get("prompt"):
        raise HTTPException(422, "prompt is required")
    if not VIDEO.is_file():
        raise HTTPException(503, "H3_DEV_VIDEO_PATH is not configured")
    job_id = "local_" + secrets.token_hex(8)
    JOBS[job_id] = {"id": job_id, "status": "processing", "created_at": int(time.time())}
    asyncio.create_task(complete(job_id))
    return {"id": job_id, "status": "processing"}


@app.get("/v1/videos/{job_id}")
async def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Video not found")
    return job


@app.get("/v1/videos/{job_id}/content")
async def content(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Video not found")
    if job["status"] != "completed":
        raise HTTPException(409, "Video is not completed")
    return FileResponse(VIDEO, media_type="video/mp4", filename=f"{job_id}.mp4")
