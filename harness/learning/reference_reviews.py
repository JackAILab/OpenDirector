"""Apply bounded audio/motion receipts to an exact reference analysis.

The operation is deliberately explicit and hash-bound.  It never changes the
analysis model, source media, or training eligibility and refuses stale
receipts after a media replacement or newer analysis version.
"""
import json
import hashlib
import re
import sqlite3
from harness.library import learning
from harness.learning.review_coverage import require_full_coverage


def apply_receipts(*, item, media_sha256, analysis_version, audio=None, motion=None):
    if not isinstance(item, str) or not item:
        raise ValueError('Reference item is required')
    if type(analysis_version) is not int or analysis_version < 1:
        raise ValueError('Analysis version is required')
    if not isinstance(media_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', media_sha256):
        raise ValueError('Media hash is required')
    if audio is None and motion is None:
        raise ValueError('At least one review receipt is required')
    for receipt, schema in ((audio, 'visualagent.ad-audio-semantic-review.v1'),
                            (motion, 'visualagent.ad-motion-review.v1')):
        if receipt is None:
            continue
        if not isinstance(receipt, dict) or receipt.get('schema') != schema:
            raise ValueError('Invalid review receipt')
        if (receipt.get('item'), receipt.get('media_sha256'), receipt.get('analysis_version')) != (item, media_sha256, analysis_version):
            raise ValueError('Review receipt binding mismatch')
        payload = {k: v for k, v in receipt.items() if k != 'review_sha256'}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if receipt.get('review_sha256') != digest or receipt.get('training_eligible') is not False:
            raise ValueError('Review receipt integrity failed')
    with sqlite3.connect(f'file:{learning.store.ROOT / "library.sqlite3"}?mode=ro', uri=True, timeout=2) as library:
        asset = library.execute('SELECT sha256,duration FROM assets WHERE item=?', (item,)).fetchone()
    if not asset or asset[0] != media_sha256:
        raise ValueError('Current media binding mismatch')
    for receipt, modality in ((audio, 'audio'), (motion, 'motion')):
        if receipt is not None:
            require_full_coverage(receipt, modality, asset[1])
    with learning.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        latest = connection.execute('SELECT MAX(version) FROM analyses WHERE item=? AND media_sha256=?',
                                    (item, media_sha256)).fetchone()[0]
        if latest != analysis_version:
            raise ValueError('Analysis version is stale or missing')
        row = connection.execute(
            'SELECT data FROM analyses WHERE item=? AND media_sha256=? AND version=?',
            (item, media_sha256, analysis_version),
        ).fetchone()
        if not row:
            raise ValueError('Analysis version is stale or missing')
        data = json.loads(row['data'])
        if audio is not None:
            if not isinstance(audio, dict) or audio.get('schema') != 'visualagent.ad-audio-semantic-review.v1':
                raise ValueError('Invalid audio review receipt')
            data['audio_review'] = {k: audio[k] for k in (
                'language', 'speech', 'music', 'sound_effects', 'sync_cues', 'brand_sound',
                'evidence_scope', 'coverage', 'reviewer_model', 'review_sha256') if k in audio}
            data['audio_semantics_reviewed'] = True
        if motion is not None:
            if not isinstance(motion, dict) or motion.get('schema') != 'visualagent.ad-motion-review.v1':
                raise ValueError('Invalid motion review receipt')
            data['motion_review'] = {k: motion[k] for k in (
                'shot_boundaries', 'product_continuity', 'causal_motion', 'camera_and_occlusion',
                'brand_transition', 'evidence_windows', 'evidence_scope', 'coverage', 'reviewer_model', 'review_sha256') if k in motion}
            data['full_motion_reviewed'] = True
        # These flags never promote training.  Human review and release gates
        # remain independent of reference evidence completion.
        data['training_eligible'] = False
        connection.execute(
            'UPDATE analyses SET data=? WHERE item=? AND media_sha256=? AND version=?',
            (json.dumps(data, ensure_ascii=False), item, media_sha256, analysis_version),
        )
    return {'item': item, 'media_sha256': media_sha256, 'analysis_version': analysis_version,
            'audio_semantics_reviewed': data.get('audio_semantics_reviewed') is True,
            'full_motion_reviewed': data.get('full_motion_reviewed') is True,
            'training_eligible': False}
