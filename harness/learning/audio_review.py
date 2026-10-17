"""Sanitize optional audio-semantic review results before persistence."""
import hashlib
import json
import re
from harness.learning.review_coverage import coverage

HEX = re.compile(r'^[a-f0-9]{64}$')
ALLOWED_LANGUAGES = {'zh', 'en', 'ja', 'ko', 'mixed', 'unknown'}
ALLOWED_LEVELS = {'present', 'absent', 'unclear'}


def _text(value, limit):
    text = re.sub(r'[\x00-\x1f\x7f]', '', str(value or '')).strip()
    return text[:limit]


def build_audio_review(*, item, media_sha256, analysis_version, result):
    """Return a privacy-safe, non-training audio review receipt.

    Raw transcript, audio URLs, provider IDs and model payloads are deliberately
    excluded.  The caller may keep a local transcript in volatile memory only.
    """
    if not isinstance(item, str) or not item or not HEX.fullmatch(str(media_sha256 or '')):
        raise ValueError('Audio review must bind an anonymous item and media hash')
    if type(analysis_version) is not int or analysis_version < 1:
        raise ValueError('Analysis version is required')
    if not isinstance(result, dict):
        raise ValueError('Audio review result is malformed')
    language = result.get('language', 'unknown')
    if language not in ALLOWED_LANGUAGES:
        language = 'unknown'
    clean = {
        'schema': 'visualagent.ad-audio-semantic-review.v1',
        'item': item,
        'media_sha256': media_sha256,
        'analysis_version': analysis_version,
        'language': language,
        'speech': result.get('speech') if result.get('speech') in ALLOWED_LEVELS else 'unclear',
        'music': result.get('music') if result.get('music') in ALLOWED_LEVELS else 'unclear',
        'sound_effects': result.get('sound_effects') if result.get('sound_effects') in ALLOWED_LEVELS else 'unclear',
        'sync_cues': [_text(v, 160) for v in result.get('sync_cues', [])[:8] if isinstance(v, str)],
        'brand_sound': _text(result.get('brand_sound'), 160) if result.get('brand_sound') else None,
        'evidence_scope': 'audio_stream_semantic_review',
        'reviewer_model': _text(result.get('reviewer_model'), 80) if result.get('reviewer_model') else 'unreported',
        'training_eligible': False,
        'coverage': coverage(result, 'audio'),
    }
    clean['review_sha256'] = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return clean
