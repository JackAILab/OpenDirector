"""Bounded observations of owned video ranges. Image bytes stay in memory only."""
import base64
import os
import subprocess
import time as clock
from harness.tools.creative_edit_media import source_path, FFMPEG

MAX_SOURCES = 6
FRAMES_PER_SOURCE = 4


def observe_edit(project, spec):
    sources = list(dict.fromkeys(c['source'] for c in spec['clips']))
    if len(sources) > MAX_SOURCES: raise ValueError('一次建议最多分析 6 个视频来源，请先缩小剪辑范围')
    observations = []; deadline = clock.monotonic()+180
    for sid in sources:
        windows = [c for c in spec['clips'] if c['source'] == sid]
        candidates = sorted(set(round(c['start']+(c['end']-c['start'])*fraction, 3)
                                for c in windows for fraction in (.1, .35, .65, .9)))
        times = [candidates[round(i*(len(candidates)-1)/(FRAMES_PER_SOURCE-1))] for i in range(FRAMES_PER_SOURCE)] if len(candidates)>FRAMES_PER_SOURCE else candidates
        for time in times:
            remaining = deadline-clock.monotonic()
            if remaining<=0: raise ValueError('视频采样超时')
            result = subprocess.run([os.getenv('CREATIVE_FFMPEG', FFMPEG), '-v', 'error', '-nostdin',
                '-protocol_whitelist', 'file,pipe', '-ss', str(time), '-i', str(source_path(project, sid)),
                '-frames:v', '1', '-vf', 'scale=512:512:force_original_aspect_ratio=decrease',
                '-threads', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
                capture_output=True, check=True, timeout=min(20,remaining))
            if not result.stdout or len(result.stdout)>500_000: raise ValueError('无法读取视频采样画面')
            observations.append({'id': 'frame_'+str(len(observations)+1), 'source': sid, 'time': time,
                                 'image': 'data:image/jpeg;base64,'+base64.b64encode(result.stdout).decode()})
    return observations
