"""Bounded local-media inspection; never opens a remote media URL."""
import hashlib
import json
import subprocess
from pathlib import Path
from fractions import Fraction


def sample(path, destination, count=12):
    path, dest = Path(path).resolve(), Path(destination)
    if not 2 <= count <= 24 or not path.is_file() or path.stat().st_size > 200 * 1024**2:
        raise ValueError('Invalid local media or sample count')
    base = ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm,avi']
    probe = subprocess.run(['ffprobe', *base, '-show_format', '-show_streams', '-of', 'json', str(path)],
                           capture_output=True, timeout=30, check=True)
    info = json.loads(probe.stdout)
    duration = float(info['format']['duration'])
    streams = info['streams']
    if not 0 < duration <= 600 or not any(s['codec_type'] == 'video' for s in streams):
        raise ValueError('Video must be at most 600 seconds')
    dest.mkdir(parents=True, exist_ok=False)
    video = next(s for s in streams if s['codec_type'] == 'video')
    try:
        frame_interval = 1 / float(Fraction(video.get('avg_frame_rate', '0/1')))
    except (ValueError, ZeroDivisionError):
        frame_interval = min(.5, duration / 2)
    # Leave a frame interval at the tail; seeking past the final frame emits no JPEG.
    span = max(0, duration - frame_interval)
    if span <= 0: raise ValueError('Video needs multiple frames')
    times = [round(span * i / (count - 1), 6) for i in range(count)]
    for i, stamp in enumerate(times):
        subprocess.run(['ffmpeg', *base, '-nostdin', '-ss', str(stamp), '-i', str(path),
                        '-frames:v', '1', '-vf', 'scale=768:768:force_original_aspect_ratio=decrease',
                        '-q:v', '4', str(dest / f'{i:02}.jpg')],
                       capture_output=True, timeout=30, check=True)
        if not (dest / f'{i:02}.jpg').is_file(): raise ValueError('Frame extraction incomplete')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024**2), b''): digest.update(block)
    return {'duration': duration, 'frame_times': times, 'media_sha256': digest.hexdigest(),
            'has_audio': any(s['codec_type'] == 'audio' for s in streams)}
