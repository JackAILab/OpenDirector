"""Sanitize optional full-motion review results before persistence.

This receipt records bounded observations about the whole moving image.  It
never stores frames, media paths, provider payloads, or a quality label that
could make a reference or user work trainable by itself.
"""
import hashlib
import json
import re
from harness.learning.review_coverage import coverage

HEX = re.compile(r'^[a-f0-9]{64}$')
LEVELS = {'clear', 'unclear', 'not_present'}


def _text(value, limit):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value or '')).strip()[:limit]


def build_motion_review(*, item, media_sha256, analysis_version, result):
    if not isinstance(item, str) or not item or not HEX.fullmatch(str(media_sha256 or '')):
        raise ValueError('Motion review must bind an anonymous item and media hash')
    if type(analysis_version) is not int or analysis_version < 1:
        raise ValueError('Analysis version is required')
    if not isinstance(result, dict):
        raise ValueError('Motion review result is malformed')
    clean = {
        'schema': 'visualagent.ad-motion-review.v1',
        'item': item,
        'media_sha256': media_sha256,
        'analysis_version': analysis_version,
        'shot_boundaries': result.get('shot_boundaries') if result.get('shot_boundaries') in LEVELS else 'unclear',
        'product_continuity': result.get('product_continuity') if result.get('product_continuity') in LEVELS else 'unclear',
        'causal_motion': result.get('causal_motion') if result.get('causal_motion') in LEVELS else 'unclear',
        'camera_and_occlusion': result.get('camera_and_occlusion') if result.get('camera_and_occlusion') in LEVELS else 'unclear',
        'brand_transition': result.get('brand_transition') if result.get('brand_transition') in LEVELS else 'unclear',
        'evidence_windows': [_text(v, 180) for v in result.get('evidence_windows', [])[:12] if isinstance(v, str)],
        'reviewer_model': _text(result.get('reviewer_model'), 80) if result.get('reviewer_model') else 'unreported',
        'evidence_scope': 'full_motion_semantic_review',
        'training_eligible': False,
        'coverage': coverage(result, 'motion'),
    }
    clean['review_sha256'] = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return clean
