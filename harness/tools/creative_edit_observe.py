"""Bounded observations of owned video ranges. Image bytes stay in memory only."""
import base64
import os
import subprocess
import time as clock
from harness.tools.creative_edit_media import source_path, FFMPEG
from harness.tools.creative_edit_timing import schedule

MAX_SOURCES = 6
FRAMES_PER_SOURCE = 4
MAX_BOUNDARIES = 8
OBSERVATION_FIELDS = ('id', 'source', 'time', 'boundary', 'side', 'clip_index', 'timeline_time', 'transition')


def observation_metadata(item):
    return {key: item[key] for key in OBSERVATION_FIELDS if key in item}


def sample_plan(spec):
    """At most 24 overview + 16 paired boundary frames, all inside saved trims."""
    clips = spec['clips']
    sources = list(dict.fromkeys(c['source'] for c in clips))
    if len(sources) > MAX_SOURCES:
        raise ValueError('一次建议最多分析 6 个视频来源，请先缩小剪辑范围')
    plan = []
    for sid in sources:
        windows = [c for c in clips if c['source'] == sid]
        candidates = sorted(set(round(c['start']+(c['end']-c['start'])*fraction, 3)
                                for c in windows for fraction in (.1, .35, .65, .9)))
        times = [candidates[round(i*(len(candidates)-1)/(FRAMES_PER_SOURCE-1))] for i in range(FRAMES_PER_SOURCE)] if len(candidates)>FRAMES_PER_SOURCE else candidates
        plan.extend({'source': sid, 'time': time} for time in times)
    count = len(clips)-1
    boundaries = list(range(count)) if count <= MAX_BOUNDARIES else [round(i*(count-1)/(MAX_BOUNDARIES-1)) for i in range(MAX_BOUNDARIES)]
    timings = schedule(clips)
    for index in boundaries:
        for side, ci in (('outgoing', index), ('incoming', index+1)):
            clip = clips[ci]
            inset = min(.125, (clip['end']-clip['start'])/4)
            time = round(clip['end']-inset if side == 'outgoing' else clip['start']+inset, 3)
            plan.append(dict(source=clip['source'], time=time, boundary=index+1, side=side,
                             clip_index=ci, timeline_time=round(timings[ci]['at']+time-clip['start'], 3),
                             transition=clips[index].get('transition', {'kind':'cut', 'duration':0})))
    return plan


def observe_edit(project, spec):
    plan = sample_plan(spec)
    observations = []; deadline = clock.monotonic()+180
    for sample in plan:
        sid, time = sample['source'], sample['time']
        remaining = deadline-clock.monotonic()
        if remaining<=0: raise ValueError('视频采样超时')
        result = subprocess.run([os.getenv('CREATIVE_FFMPEG', FFMPEG), '-v', 'error', '-nostdin',
            '-protocol_whitelist', 'file,pipe', '-ss', str(time), '-i', str(source_path(project, sid)),
            '-frames:v', '1', '-vf', 'scale=512:512:force_original_aspect_ratio=decrease',
            '-threads', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
            capture_output=True, check=True, timeout=min(20,remaining))
        if not result.stdout or len(result.stdout)>500_000: raise ValueError('无法读取视频采样画面')
        observations.append({'id': 'frame_'+str(len(observations)+1), **sample,
                             'image': 'data:image/jpeg;base64,'+base64.b64encode(result.stdout).decode()})
    return observations
