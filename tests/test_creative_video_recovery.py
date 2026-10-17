import asyncio
import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from harness.tools.creative_video import CreativeVideoTool


def test_transient_download_recovers_without_another_submission(tmp_path, monkeypatch):
    app = FastAPI()
    calls = {'get': 0, 'post': 0}
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr('harness.tools.creative_video.asyncio.sleep', sleep)

    @app.get('/v1/videos/existing/content')
    def content():
        calls['get'] += 1
        return Response(b'video' if calls['get'] == 3 else b'', status_code=200 if calls['get'] == 3 else 503)

    @app.post('/v1/videos')
    def submit():
        calls['post'] += 1
        return Response(status_code=503)

    tool = CreativeVideoTool(app, 'Bearer test')
    destination = tmp_path / 'shot.mp4'
    asyncio.run(tool.download('existing', destination))
    assert destination.read_bytes() == b'video'
    assert calls == {'get': 3, 'post': 0}
    assert delays == [1, 3]
    with pytest.raises(RuntimeError, match='503'):
        asyncio.run(tool.request('POST', '/v1/videos', json={}))
    assert calls['post'] == 1
    assert delays == [1, 3]


def test_persistent_read_error_stops_at_three_attempts(monkeypatch):
    app = FastAPI()
    calls = []

    async def sleep(_):
        pass

    monkeypatch.setattr('harness.tools.creative_video.asyncio.sleep', sleep)

    @app.get('/v1/videos/existing')
    def status():
        calls.append(1)
        return Response(status_code=503)

    with pytest.raises(RuntimeError, match='503'):
        asyncio.run(CreativeVideoTool(app, 'Bearer test').status('existing'))
    assert len(calls) == 3
