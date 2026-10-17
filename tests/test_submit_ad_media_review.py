import json
import sqlite3
import subprocess
import sys


def test_review_input_is_allowlisted_and_non_training(tmp_path):
    review = {'reviewer_model': 'reviewer', 'coverage': {'complete': True, 'start_seconds': 0, 'end_seconds': 4}}
    path = tmp_path / 'motion.json'
    path.write_text(json.dumps(review), encoding='utf-8')
    from harness.learning.motion_review import build_motion_review
    receipt = build_motion_review(item='item', media_sha256='a' * 64, analysis_version=1, result=review)
    assert receipt['training_eligible'] is False
    assert receipt['coverage']['complete'] is True
    assert 'reviewer_model' in receipt
