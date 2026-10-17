import json
import sqlite3
import pytest

from harness.library import learning
from harness.learning.audio_review import build_audio_review
from harness.learning.motion_review import build_motion_review
from harness.learning.reference_reviews import apply_receipts


def test_apply_receipts_is_hash_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(learning.store, 'ROOT', tmp_path)
    digest = 'a' * 64
    with sqlite3.connect(tmp_path / 'library.sqlite3') as c:
        c.execute('CREATE TABLE assets(item TEXT, sha256 TEXT, duration REAL)')
        c.execute('INSERT INTO assets VALUES(?,?,?)', ('item', digest, 15.0))
    with learning.connection() as c:
        c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                  ('item', digest, 1, 1, 'model', json.dumps({
                      'audio_semantics_reviewed': False,
                      'full_motion_reviewed': False,
                      'training_eligible': False,
                  }), 1.0))
    audio = build_audio_review(item='item', media_sha256=digest, analysis_version=1,
                               result={'speech': 'present', 'sync_cues': ['0-2s'], 'reviewer_model': 'test-reviewer', 'coverage': {'complete': True, 'start_seconds': 0, 'end_seconds': 15}})
    motion = build_motion_review(item='item', media_sha256=digest, analysis_version=1,
                                 result={'product_continuity': 'clear', 'reviewer_model': 'test-reviewer', 'coverage': {'complete': True, 'start_seconds': 0, 'end_seconds': 15}})
    result = apply_receipts(item='item', media_sha256=digest, analysis_version=1,
                            audio=audio, motion=motion)
    assert result['audio_semantics_reviewed'] and result['full_motion_reviewed']
    with learning.connection() as c:
        data = json.loads(c.execute('SELECT data FROM analyses').fetchone()[0])
    assert data['training_eligible'] is False


def test_apply_receipts_rejects_stale_version(tmp_path, monkeypatch):
    monkeypatch.setattr(learning.store, 'ROOT', tmp_path)
    with pytest.raises(ValueError):
        apply_receipts(item='item', media_sha256='a' * 64, analysis_version=1,
                       audio={'schema': 'visualagent.ad-audio-semantic-review.v1'})


@pytest.mark.parametrize('change', ['item', 'hash', 'tamper', 'new_version', 'replaced_media', 'partial', 'missing_coverage', 'wrong_modality'])
def test_review_cannot_promote_wrong_or_stale_evidence(tmp_path, monkeypatch, change):
    monkeypatch.setattr(learning.store, 'ROOT', tmp_path)
    digest = 'a' * 64
    with sqlite3.connect(tmp_path / 'library.sqlite3') as c:
        c.execute('CREATE TABLE assets(item TEXT, sha256 TEXT, duration REAL)')
        c.execute('INSERT INTO assets VALUES(?,?,?)', ('item', 'b' * 64 if change == 'replaced_media' else digest, 15.0))
    with learning.connection() as c:
        c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                  ('item', digest, 1, 1, 'model', '{}', 1))
        if change == 'new_version':
            c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                      ('item', digest, 2, 1, 'model', '{}', 2))
    receipt = build_motion_review(item='other' if change == 'item' else 'item',
                                  media_sha256='b' * 64 if change == 'hash' else digest,
                                  analysis_version=1, result={'reviewer_model': 'test-reviewer', 'coverage': {'complete': change != 'missing_coverage', 'start_seconds': 0, 'end_seconds': 5 if change == 'partial' else 15}})
    if change == 'wrong_modality':
        import hashlib
        receipt['coverage']['modality'] = 'audio'
        receipt['review_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in receipt.items() if k != 'review_sha256'}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if change == 'tamper':
        receipt['causal_motion'] = 'clear'
    with pytest.raises(ValueError):
        apply_receipts(item='item', media_sha256=digest, analysis_version=1, motion=receipt)
    with learning.connection() as c:
        assert all('full_motion_reviewed' not in json.loads(r[0]) for r in c.execute('SELECT data FROM analyses'))
