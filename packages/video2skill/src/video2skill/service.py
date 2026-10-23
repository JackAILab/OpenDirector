import fcntl
import hmac
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from .harness.models.vision import configured
from .runner import Store, run
from .schema import Source

ARTIFACTS = {'SKILL.md', 'skill.json', 'evidence.json', 'review.json', 'manifest.json'}


def create_app(root=None, token=None):
    root = Path(root or os.getenv('V2S_DATA_DIR', './video2skill-data'))
    secret = token or os.getenv('V2S_SERVICE_TOKEN', '')
    if len(secret) < 24: raise ValueError('Set V2S_SERVICE_TOKEN to at least 24 random characters')

    @asynccontextmanager
    async def lifespan(app):
        root.mkdir(parents=True, exist_ok=True)
        with (root / 'service.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            app.state.store = Store(root)
            app.state.store.recover()
            with ThreadPoolExecutor(max_workers=1) as pool:
                app.state.pool = pool
                yield

    app = FastAPI(title='Video2Skill', version='0.1.0', lifespan=lifespan)

    def auth(authorization: str = Header(default='')):
        if not hmac.compare_digest(authorization.encode(), ('Bearer ' + secret).encode()):
            raise HTTPException(401, 'Bearer token required')

    def task(identity):
        if not re.fullmatch('[a-f0-9]{32}', identity): raise HTTPException(404, 'Job not found')
        result = app.state.store.get(identity)
        if not result: raise HTTPException(404, 'Job not found')
        return result

    @app.get('/health')
    def health(): return {'status': 'ok', 'version': '0.1.0'}

    @app.post('/v1/jobs', status_code=202, dependencies=[Depends(auth)])
    async def submit(video: UploadFile = File(...), source: str = Form(...),
                     allow_model_call: bool = Form(False), target_duration: int = Form(15, ge=5, le=180),
                     language: str = Form('zh', pattern='^(zh|en)$')):
        if not allow_model_call: raise HTTPException(422, 'Explicit allow_model_call=true is required')
        if not configured(): raise HTTPException(503, 'Vision provider is not configured')
        try: metadata = Source.model_validate_json(source)
        except (ValidationError, ValueError): raise HTTPException(422, 'Invalid source metadata') from None
        store = app.state.store
        try: identity = store.create()
        except ValueError: raise HTTPException(429, 'Queue is full') from None
        path = root / identity / 'input.bin'
        try:
            size = 0
            with path.open('xb') as handle:
                while chunk := await video.read(1024**2):
                    size += len(chunk)
                    if size > 200 * 1024**2: raise HTTPException(413, 'Video exceeds 200 MiB')
                    handle.write(chunk)
            if not size: raise HTTPException(422, 'Empty video')
            store.update(identity, 'queued')
            app.state.pool.submit(run, store, identity, metadata, target_duration, language)
        except BaseException:
            path.unlink(missing_ok=True)
            store.update(identity, 'failed', 'upload_failed')
            raise
        finally:
            await video.close()
        return {'id': identity, 'status_url': f'/v1/jobs/{identity}'}

    @app.get('/v1/jobs/{identity}', dependencies=[Depends(auth)])
    def status(identity: str): return task(identity)

    @app.get('/v1/jobs/{identity}/artifacts/{name}', dependencies=[Depends(auth)])
    def artifact(identity: str, name: str):
        state = task(identity)
        if name not in ARTIFACTS or state['state'] != 'completed': raise HTTPException(404, 'Artifact not available')
        return FileResponse(root / identity / 'bundle' / name, filename=name)

    return app
