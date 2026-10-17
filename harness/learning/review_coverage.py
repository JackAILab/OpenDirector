"""Explicit review coverage declarations, never inferred from stream presence."""
import math


def coverage(result, modality):
    value = result.get('coverage')
    if not isinstance(value, dict):
        return {'modality': modality, 'complete': False}
    clean = {'modality': modality, 'complete': value.get('complete') is True}
    for key in ('start_seconds', 'end_seconds'):
        number = value.get(key)
        if type(number) in (int, float) and math.isfinite(number) and number >= 0:
            clean[key] = number
    return clean


def require_full_coverage(receipt, modality, duration):
    value = receipt.get('coverage') or {}
    start, end = value.get('start_seconds'), value.get('end_seconds')
    if (type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0
            or value.get('modality') != modality or value.get('complete') is not True
            or type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end)
            or start != 0 or abs(end - duration) > 0.1
            or receipt.get('reviewer_model') in (None, '', 'unreported')):
        raise ValueError('Full media review coverage is required')
