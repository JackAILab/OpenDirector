"""Bounded pixel observation for generated image transform results.

This is a technical Observation only. It can show that two owned images are
different (or unchanged) after a transform request; it cannot prove that a
model followed an angle, lighting, product, or semantic instruction.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


OBSERVATION_VERSION = 'image-transform-pixel-v1'
SAMPLE_SIZE = (128, 128)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _invalid(status: str) -> dict:
    return {
        'schema': OBSERVATION_VERSION,
        'status': status,
        'human_review_required': True,
        'training_eligible': False,
    }


def observe_transform(source: Path, result: Path) -> dict:
    """Compare two owned images after deterministic 128px normalization.

    Paths are used only inside the evaluator and are never returned. The
    result is deliberately bounded so it is safe to persist in a project
    receipt and project to the canvas.
    """
    try:
        source_raw = source.read_bytes()
        result_raw = result.read_bytes()
        with Image.open(source) as source_image, Image.open(result) as result_image:
            source_rgb = source_image.convert('RGB')
            result_rgb = result_image.convert('RGB')
            source_size = list(source_rgb.size)
            result_size = list(result_rgb.size)
            source_sample = source_rgb.resize(SAMPLE_SIZE, Image.Resampling.BILINEAR)
            result_sample = result_rgb.resize(SAMPLE_SIZE, Image.Resampling.BILINEAR)
            difference = ImageChops.difference(source_sample, result_sample)
            mean = ImageStat.Stat(difference).mean
            flattened = getattr(difference, 'get_flattened_data', difference.getdata)
            pixels = list(flattened())
            changed = sum(1 for pixel in pixels if max(pixel) > 4)
            total = max(len(pixels), 1)
            changed_ratio = changed / total
            mean_absolute_error = sum(mean) / (3 * 255)
    except (OSError, ValueError, SyntaxError):
        return _invalid('decode_failed')

    status = 'changed_observed' if changed_ratio > 0 else 'unchanged'
    return {
        'schema': OBSERVATION_VERSION,
        'status': status,
        'source_sha256': _sha256(source_raw),
        'result_sha256': _sha256(result_raw),
        'source_dimensions': source_size,
        'result_dimensions': result_size,
        'sample_dimensions': list(SAMPLE_SIZE),
        'changed_pixel_ratio': round(changed_ratio, 6),
        'mean_absolute_error': round(mean_absolute_error, 6),
        'human_review_required': True,
        'training_eligible': False,
    }
