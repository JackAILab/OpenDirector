"""Admin access to the private, sanitized candidate review queue."""
import hashlib
import hmac
import json
import os
import stat
import threading
from pathlib import Path

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field, StrictBool

from harness.learning.candidate_review import make_receipt, queue_digest


class CandidateReview(BaseModel):
    privacy_review: StrictBool
    rights_review: StrictBool
    sanitized_context_review: StrictBool
    note: str = Field(min_length=10, max_length=1000)


def install(gateway):
    app = gateway.app
    write_lock = threading.Lock()

    def admin(auth):
        if not hasattr(gateway, 'require_admin'):
            raise HTTPException(403, '需要管理员审阅权限')
        return gateway.require_admin(auth)['id']

    def paths():
        queue = Path(os.getenv(
            'AD_TRAINING_CANDIDATE_QUEUE',
            '/var/lib/visualstation-local/creative/learning/training-candidates-current.json'))
        reviews = Path(os.getenv('AD_TRAINING_REVIEW_DIR', str(queue.parent / 'candidate-reviews')))
        return queue, reviews

    def load_queue():
        queue, _ = paths()
        if queue.is_symlink() or not queue.is_file():
            return None
        if stat.S_IMODE(queue.stat().st_mode) & 0o077:
            raise HTTPException(500, '候选队列权限不安全')
        try:
            data = json.loads(queue.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise HTTPException(500, '候选队列不可读取')
        if data.get('schema') != 'visualagent.training-candidate-queue.v1' or not isinstance(data.get('records'), list):
            raise HTTPException(500, '候选队列格式不受支持')
        return data

    def safe_record(record, detail=False):
        result = {k: v for k, v in record.items() if k != 'creator_token'}
        if not detail:
            plan = result.get('plan') or {}
            trajectory_events = len((result.get('trajectory') or {}).get('events', []))
            result = {k: result.get(k) for k in ('sample_id', 'partition', 'review_status', 'training_eligible')}
            result.update({'brief': plan.get('brief', {}),
                           'strategy_count': len(plan.get('strategy_candidates', [])),
                           'trajectory_events': trajectory_events})
        return result

    @app.get('/creative/api/admin/learning/candidates')
    def candidates(authorization: str | None = Header(None)):
        admin(authorization)
        queue = load_queue()
        if queue is None:
            return {'state': 'missing', 'record_count': 0, 'training_eligible': False, 'items': []}
        return {'state': 'present', 'record_count': len(queue['records']),
                'training_eligible': queue.get('training_eligible') is True,
                'queue_sha256': queue_digest(queue),
                'items': [safe_record(r) for r in queue['records']]}

    @app.get('/creative/api/admin/learning/candidates/{sample_id}')
    def candidate(sample_id: str, authorization: str | None = Header(None)):
        admin(authorization)
        queue = load_queue()
        if queue is None:
            raise HTTPException(404, '候选队列不存在')
        record = next((r for r in queue['records'] if r.get('sample_id') == sample_id), None)
        if not record:
            raise HTTPException(404, '候选不存在')
        return {'queue_sha256': queue_digest(queue), 'candidate': safe_record(record, detail=True)}

    @app.post('/creative/api/admin/learning/candidates/{sample_id}/review')
    def review(sample_id: str, body: CandidateReview, authorization: str | None = Header(None)):
        actor = admin(authorization)
        queue = load_queue()
        if queue is None:
            raise HTTPException(404, '候选队列不存在')
        record = next((r for r in queue['records'] if r.get('sample_id') == sample_id), None)
        if not record:
            raise HTTPException(404, '候选不存在')
        decisions = {key: getattr(body, key) for key in
                     ('privacy_review', 'rights_review', 'sanitized_context_review')}
        key_setting = os.getenv('AD_LEARNING_SALT_FILE')
        if not key_setting:
            raise HTTPException(503, '未配置独立审阅身份校验')
        key_path = Path(key_setting)
        if key_path.is_symlink() or not key_path.is_file() or stat.S_IMODE(key_path.stat().st_mode) & 0o077:
            raise HTTPException(503, '独立审阅身份校验配置不可用')
        salt = key_path.read_bytes()
        if len(salt) < 32 or queue.get('salt_sha256') != hashlib.sha256(salt).hexdigest():
            raise HTTPException(409, '候选队列身份校验版本不匹配，请重新准备队列')
        if not record.get('creator_token'):
            raise HTTPException(409, '候选缺少创建者绑定，不能独立审阅')
        reviewer_token = hmac.new(salt, f"creator:{actor}".encode(), hashlib.sha256).hexdigest()
        try:
            receipt = make_receipt(queue, sample_id, str(actor), decisions, body.note,
                                   reviewer_token=reviewer_token)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        _, directory = paths()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise HTTPException(500, '审核回执目录权限不安全')
        target = directory / (receipt['candidate_sha256'] + '.json')
        with write_lock:
            if target.exists() or target.is_symlink():
                raise HTTPException(409, '该候选已有审核回执，请保留历史并通过离线流程复核')
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(receipt, out, ensure_ascii=False, indent=2)
                out.write('\n')
        return {'candidate': sample_id, 'receipt_sha256': receipt['receipt_sha256'],
                'training_eligible': False}
