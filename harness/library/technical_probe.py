"""Bounded technical probes for private ad review packets.

The probe records container/stream facts only.  It never infers speech meaning,
editing quality, motion readability, or training eligibility from ffprobe.
"""
import json
import hashlib
import math
import os
import subprocess
from pathlib import Path

FFPROBE = os.getenv('AD_FFPROBE', '/opt/visualstation/creative-runtime/bin/ffprobe')


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _rate(value):
    if not isinstance(value, str) or '/' not in value:
        return None
    left, right = value.split('/', 1)
    try:
        denominator = float(right)
        return round(float(left) / denominator, 6) if denominator else None
    except (TypeError, ValueError):
        return None


def summarize_probe(payload):
    """Reduce ffprobe JSON to safe, stable stream facts without a path."""
    if not isinstance(payload, dict):
        raise ValueError('Invalid ffprobe payload')
    streams = payload.get('streams')
    if not isinstance(streams, list):
        raise ValueError('ffprobe streams are missing')
    video = next((s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'audio'), None)
    format_data = payload.get('format') if isinstance(payload.get('format'), dict) else {}
    return {
        'status': 'ok',
        'duration_seconds': _number(format_data.get('duration')),
        'video': {
            'present': bool(video),
            'codec': video.get('codec_name') if video else None,
            'width': video.get('width') if video else None,
            'height': video.get('height') if video else None,
            'frame_rate': _rate(video.get('avg_frame_rate')) if video else None,
        },
        'audio': {
            'present': bool(audio),
            'codec': audio.get('codec_name') if audio else None,
            'sample_rate': int(audio['sample_rate']) if audio and str(audio.get('sample_rate', '')).isdigit() else None,
            'channels': audio.get('channels') if audio else None,
        },
        'semantic_review': 'pending',
        'motion_review': 'pending',
        'training_eligible': False,
    }


def probe_file(path, expected_sha256=None):
    """Probe one local file and return facts; optionally bind its SHA upstream."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return {'status': 'missing', 'semantic_review': 'pending', 'motion_review': 'pending', 'training_eligible': False}
    before = path.stat()
    if expected_sha256:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            return {'status': 'hash_mismatch', 'semantic_review': 'pending', 'motion_review': 'pending', 'training_eligible': False}
    command = [FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        result = summarize_probe(json.loads(completed.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return {'status': 'probe_failed', 'semantic_review': 'pending', 'motion_review': 'pending', 'training_eligible': False}
    if expected_sha256:
        result['bound_media_sha256'] = expected_sha256
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return {'status': 'media_changed', 'semantic_review': 'pending', 'motion_review': 'pending', 'training_eligible': False}
    return result
