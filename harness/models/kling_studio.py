"""Local Kling-backed upstream for the port-forwarded studio.

Each POST is one explicit paid submission. There is no retry and no model
substitution. Provider payloads and temporary URLs stay in process memory only.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import math
import time
import os
import secrets
import subprocess
import tempfile
from harness.models.kling_video import _first, _task_status
import urllib.request
from pathlib import Path
from PIL import Image

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

CLI = os.getenv("KLING_CLI", "kling")
REFERENCE = Path(os.getenv("KLING_REFERENCE_IMAGE", ""))
OUTPUT_DIR = Path(os.getenv("KLING_OUTPUT_DIR", "/tmp/visualstation-kling"))
MODEL = os.getenv("KLING_MODEL", "kling-video-v3_0")
JOBS: dict[str, dict[str, object]] = {}
ACTIVE = False
POLLING: set[str] = set()
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
            if job.get("status") == "processing" and not job.get("generation_id"):
                job.update(status="uncertain", error="提交结果待核对，未自动重试")
            JOBS[job_id] = job
        except (OSError, ValueError):
            continue


load_states()
ACTIVE = any(j.get("status") in {"processing","uncertain"} for j in JOBS.values())


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "kling", "active": ACTIVE}


def generation_args(body: dict) -> list[str] | dict:
    task=body.get('task');model=body.get('model') or MODEL
    if task not in {'t2va','fl2va','ref2va'}:raise HTTPException(422,'Unsupported Kling studio task')
    prompt=body.get('prompt')
    if not isinstance(prompt,str) or not prompt.strip():raise HTTPException(422,'prompt is required')
    if body.get('seed') is not None:raise HTTPException(422,'Kling studio does not support seed')
    conditions=body.get('conditions',[]);paths=[]
    if not isinstance(conditions,list):raise HTTPException(422,'Invalid image conditions')
    if task=='t2va' and conditions:raise HTTPException(422,'Text-to-video cannot include reference conditions')
    if task=='ref2va' and (model not in {'kling-video-v3_0_omni','kling-video-v4_0','kling-video-o1'} or not 1<=len(conditions)<=7):
        raise HTTPException(422,'Multi-image reference requires Kling O3 and one to seven images')
    if task=='fl2va' and (not 1<=len(conditions)<=2 or len(conditions)==2 and model not in {'kling-video-v3_0','kling-video-v2_5','kling-video-v2_6'}):
        raise HTTPException(422,'First/tail frames require Kling 3.0; legacy single images remain supported')
    total=0
    for i,c in enumerate(conditions):
        if not isinstance(c,dict) or c.get('type')!='image':raise HTTPException(422,'Invalid image condition')
        if task=='ref2va':
            valid=set(c)=={'type','role','index','uri'} and c.get('role')=='reference' and type(c.get('index')) is int and c['index']==i+1
        else:
            valid=set(c)=={'type','role','frame_index','uri'} and c.get('role')=='keyframe' and type(c.get('frame_index')) is int and c['frame_index']==(0 if i==0 else -1)
        if not valid:raise HTTPException(422,'Unsupported image condition or order')
        uri=c['uri']
        if not isinstance(uri,str) or not uri.startswith('data:image/jpeg;base64,') or len(uri)>700000:
            raise HTTPException(422,'Only bounded inline JPEG references are accepted')
        total+=len(uri)
        if total>950000:raise HTTPException(422,'Combined reference payload is too large')
        try:
            data=base64.b64decode(uri.split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(data)) as image:
                if image.format!='JPEG' or max(image.size)>1280 or min(image.size)<128 or not .5<=image.width/image.height<=2:raise ValueError()
                image.verify()
        except Exception as exc:raise HTTPException(422,'Invalid reference JPEG') from exc
        folder=OUTPUT_DIR/'references';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=folder/(hashlib.sha256(data).hexdigest()+'.jpg')
        if not path.exists():
            with path.open('xb') as output:output.write(data)
            path.chmod(0o600)
        elif path.read_bytes()!=data:raise HTTPException(503,'Stored reference integrity check failed')
        paths.append(path)
    target = body.get("target", {})
    if not isinstance(target, dict):
        raise HTTPException(422, "target must be an object")
    if set(target) - {"duration_seconds", "short_edge", "aspect_ratio"}:
        raise HTTPException(422, "Unsupported Kling target parameter")
    duration = target.get("duration_seconds", 5)
    edge = target.get("short_edge", 720)
    aspect = target.get("aspect_ratio", "16:9")
    if type(duration) is not int or not 3 <= duration <= 30:
        raise HTTPException(422, "duration_seconds must be an integer from 3 to 30")
    if type(edge) is not int or edge not in {720, 1080}:
        raise HTTPException(422, "short_edge must be 720 or 1080 for Kling")
    if not isinstance(aspect, str) or aspect not in {"16:9", "9:16", "1:1"}:
        raise HTTPException(422, "Unsupported aspect_ratio")
    model = body.get("model") or MODEL
    if model not in {"kling-video-v2_5", "kling-video-v3_0", "kling-video-v3_0_omni", "kling-video-v4_0", "kling-video-v2_6", "kling-video-o1", "kling-video-v3_0_turbo"}:
        raise HTTPException(422, "Requested Kling model is not enabled")
    if model == "kling-video-v2_5" and duration not in {5,10}:
        raise HTTPException(422, "Kling 2.5 supports 5 or 10 seconds")
    audio = body.get('enable_audio', False)
    multi = body.get('prefer_multi_shots', False)
    if type(audio) is not bool or type(multi) is not bool:
        raise HTTPException(422, 'Audio and multi-shot flags must be booleans')
    from harness.models.video_catalog import MANUAL_DURATIONS
    if duration not in MANUAL_DURATIONS[model]:raise HTTPException(422,'Duration is not supported by the selected model')
    if model in {'kling-video-v2_6','kling-video-o1','kling-video-v3_0_turbo'}:
        if multi:raise HTTPException(422,'Selected model does not support multi-shot generation')
        if audio and model in {'kling-video-o1','kling-video-v3_0_turbo'}:raise HTTPException(422,'Selected model does not support audio')
        if task=='fl2va' and model=='kling-video-o1':raise HTTPException(422,'O1 uses reference images')
        return {'task':'manual_family','model':model,'prompt':prompt.strip(),'paths':paths,'duration':duration,'resolution':f'{edge}p','aspect':aspect,'audio':audio}
    if model=='kling-video-v4_0':
        if task=='fl2va' or not multi:
            raise HTTPException(422, 'Kling 4.0 Omni requires multi-shot mode; use text or image references')
        return {'task':'omni_v4','model':model,'prompt':prompt.strip(),'paths':paths,
                'duration':duration,'resolution':f'{edge}p','aspect':aspect,'audio':audio}
    if multi and model=='kling-video-v2_5':
        raise HTTPException(422, 'Selected model does not support multi-shot generation')
    if paths:
        flags=[v for i,path in enumerate(paths) for v in [('--tailImage' if task=='fl2va' and i==1 else '--image'),str(path)]]
        return [CLI,'image_to_video',*flags,'--model',model,
                '--duration',str(duration),'--resolution',f'{edge}p','--imageCount','1',
                *(['--aspect_ratio',aspect] if model=='kling-video-v3_0_omni' else []),
                *(['--prefer_multi_shots',str(multi).lower()] if model!='kling-video-v2_5' else []),
                '--enable_audio',str(audio).lower(),'--skill-name','visualstation-local','--skill-version','0.3.0',
                '--poll','0',prompt.strip(),'--quiet']
    return [CLI, "text_to_video", "--model", model,
            "--duration", str(duration), "--resolution", f"{edge}p",
            "--aspect_ratio", aspect, "--imageCount", "1",
            *(["--prefer_multi_shots", str(multi).lower()] if model != "kling-video-v2_5" else []),
            "--enable_audio", str(audio).lower(),
            "--skill-name", "visualstation-local", "--skill-version", "0.1.0",
            "--poll", "0", "--quiet", prompt.strip()]


def cli_result(args: list[str]) -> dict:
    process = subprocess.run(args, check=False, capture_output=True, text=True,
                             timeout=int(os.getenv("KLING_PROCESS_TIMEOUT", "360")))
    if process.returncode:
        raise RuntimeError("Kling 请求未取得确定结果；未重新提交")
    for line in reversed(process.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("ok") is True:
            return candidate
    raise RuntimeError("Kling 未返回可确认的结果；未重新提交")


def refresh_active() -> None:
    global ACTIVE
    ACTIVE = any(j.get('status') in {'processing','uncertain'} for j in JOBS.values())


def poll_generation(job_id: str) -> None:
    output = OUTPUT_DIR / f"{job_id}.mp4"
    temporary = output.with_suffix('.part')
    try:
        generation_id = JOBS[job_id]['generation_id']
        from harness.models.kling_session import session_lock
        with session_lock():
            result = cli_result([CLI, 'query_tasks', '--poll', '0',
                                 generation_id, '--skill-name','visualstation-local',
                                 '--skill-version','0.2.0','--quiet'])
        state = _task_status(result)
        job = JOBS[job_id]
        # Expose only documented counters and known stages, never provider payloads.
        job['checked_at'] = int(time.time())
        job['stage'] = 'queued' if state in {'QUEUED', 'PENDING', 'WAITING', 'SUBMITTED'} else 'generating'
        progress = _first(result, ('progress',))
        job.pop('progress', None)
        if type(progress) in (int, float) and math.isfinite(progress) and 0 <= progress <= 100:
            job['progress'] = round(progress)
        persist(job_id)
        if JOBS[job_id].pop('error',None) is not None: persist(job_id)
        if state in {'FAILED','ERROR','CANCELLED','CANCELED','REJECTED'}:
            JOBS[job_id].update(status='failed',error='供应商确认生成失败；未重试')
            persist(job_id)
            return
        url = _first(result, ('urlWithoutWatermark','url_without_watermark'))
        if state not in {'COMPLETED','PARTIAL_COMPLETED','SUCCEEDED','SUCCESS','FINISHED'} or not isinstance(url,str):
            return  # A non-terminal poll is not a failed paid generation.
        if not url.startswith(('https://','http://')):
            raise RuntimeError('供应商视频地址无效')
        JOBS[job_id]['stage'] = 'finalizing'
        persist(job_id)
        if not output.exists():
            with urllib.request.urlopen(url,timeout=600) as response:
                with temporary.open('wb') as stream:
                    while chunk := response.read(1024*1024): stream.write(chunk)
            if temporary.stat().st_size<1024: raise RuntimeError('视频下载不完整')
            temporary.replace(output)
        JOBS[job_id].update(status='completed',progress=100,output=str(output))
        JOBS[job_id].pop('error',None)
        persist(job_id)
    except Exception:
        # Keep the provider handle so a later read resumes polling/download.
        JOBS[job_id]['error']='查询或下载暂时中断；任务编号已保留，未重复生成'
        persist(job_id)
    finally:
        temporary.unlink(missing_ok=True)
        POLLING.discard(job_id)
        refresh_active()


def run_generation(job_id: str, args: list[str] | dict) -> None:
    try:
        from harness.models.kling_session import session_lock
        with session_lock():
            if isinstance(args, dict):
                if args.get('task')=='omni_v4':
                    from harness.models.kling_omni import submit
                elif args.get('task')=='manual_family':
                    from harness.models.kling_manual import submit
                else:
                    from harness.models.kling_retake import submit
                submitted = submit(args, cli_result, CLI)
            else:
                submitted=cli_result(args)
        generation_id=_first(submitted,('generation_id','generationId','task_id'))
        if not isinstance(generation_id,str) or not generation_id:
            raise RuntimeError('Missing generation handle')
        JOBS[job_id]['generation_id']=generation_id
        persist(job_id)  # Save before the first potentially long status poll.
    except Exception as exc:
        from harness.models.kling_retake import PreflightError
        if isinstance(exc, PreflightError):
            JOBS[job_id].update(status='failed',error='输入或账户能力检查未通过，未提交生成')
        else:
            JOBS[job_id].update(status='uncertain',error='供应商提交结果待核对；未自动重试或退款')
        persist(job_id)
        POLLING.discard(job_id)
        refresh_active()
        return
    poll_generation(job_id)


@app.post("/v1/videos")
async def create(body: dict):
    global ACTIVE
    if body.get('task') == 'v2v_edit':
        from harness.models.kling_retake import validate_request
        try: validate_request(body)
        except ValueError as exc: raise HTTPException(422, str(exc)) from exc
        args = body
    else:
        args = generation_args(body)
    if ACTIVE:
        raise HTTPException(429, "Kling worker is busy", headers={"Retry-After": "15"})
    if not shutil_which(CLI):
        raise HTTPException(503, "Kling CLI is not available")
    job_id = "kling_" + secrets.token_hex(8)
    JOBS[job_id] = {"id": job_id, "status": "processing", "stage": "preparing"}
    persist(job_id)
    ACTIVE = True
    POLLING.add(job_id)
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
    if job.get('status')=='processing' and job.get('generation_id') and job_id not in POLLING:
        POLLING.add(job_id)
        asyncio.create_task(asyncio.to_thread(poll_generation,job_id))
    return {key: value for key, value in job.items() if key not in {'output','generation_id'}}


@app.get("/v1/videos/{job_id}/content")
async def content(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Video not found")
    if job.get("status") != "completed":
        raise HTTPException(409, "Video is not completed")
    return FileResponse(str(job["output"]), media_type="video/mp4", filename=f"{job_id}.mp4")
