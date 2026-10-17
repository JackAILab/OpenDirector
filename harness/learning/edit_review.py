"""Independent quality receipts for immutable edit exports.

Edit exports are private production artifacts and are not the same thing as a
native project film.  Keep their review records in a separate table and bind
every receipt to the export id, revision and bytes on disk.  A receipt never
opens training eligibility by itself.
"""
import json
import time

from harness.learning import governance, review
from harness.learning.episodes import _hash
from harness.studio import store
from harness.tools.creative_edit_media import digest


def connection():
    c = governance.connection()
    c.execute("""CREATE TABLE IF NOT EXISTS edit_quality_reviews(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT, owner INTEGER, reviewer INTEGER, export_id TEXT,
        revision INTEGER, artifact TEXT, data TEXT, created REAL)""")
    return c


def export_record(project, export_id):
    return next((j for j in project.get('edit_versions', []) if j.get('id') == export_id), None)


def export_path(project, export):
    if not export or export.get('state') != 'completed':
        raise ValueError('只有已完成的剪辑导出才能独立审阅')
    path = (store.DATA / 'edits' / project['id'] / export['id'] / 'final.mp4').resolve()
    if not path.is_file() or not path.is_relative_to((store.DATA / 'edits').resolve()):
        raise ValueError('剪辑导出文件不可读取')
    actual = digest(path)
    if export.get('artifact_sha256') != actual:
        raise ValueError('剪辑导出文件已变化，请重新导出')
    return path, actual


def record(project, owner, reviewer, export, artifact, decision, ratings, checks):
    if reviewer == owner:
        raise ValueError('独立审阅者不能是作品创建者')
    path, actual = export_path(project, export)
    if actual != artifact:
        raise ValueError('剪辑导出版本已变化，请重新审阅')
    if decision not in ('passed', 'needs_changes', 'rejected'):
        raise ValueError('审阅结论无效')
    if set(ratings) != set(review.RUBRIC):
        raise ValueError('请逐项填写质量评价')
    clean = {}
    for key in review.RUBRIC:
        item = ratings[key]
        score = item.get('score')
        evidence = item.get('evidence', '').strip()
        if type(score) is not int or not 0 <= score <= 5 or not 5 <= len(evidence) <= 500:
            raise ValueError('每项需要0–5分和具体审阅依据')
        clean[key] = {'score': score, 'evidence': evidence}
    expected_checks = ('full_video_watched', 'audio_listened', 'product_facts_checked')
    if set(checks) != set(expected_checks) or any(type(v) is not bool for v in checks.values()):
        raise ValueError('请明确填写审阅范围')
    if decision == 'passed' and (not all(checks.values()) or any(i['score'] < 3 for i in clean.values())):
        raise ValueError('通过需要完整观看、听音及核实商品事实，且各项至少3分')
    payload = {
        'schema': 'visualagent.edit-independent-quality-review.v1',
        'rubric_version': 'ad-quality-v1',
        'target': 'edit_export',
        'export_id': export['id'],
        'decision': decision,
        'ratings': clean,
        'checks': checks,
        'revision': export.get('revision'),
        'artifact_sha256': artifact,
        'training_eligible': False,
    }
    payload['receipt_sha256'] = _hash({
        'project': project['id'], 'owner': owner, 'reviewer': reviewer,
        'export_id': export['id'], 'revision': export.get('revision'), 'data': payload,
    })
    c = connection()
    try:
        with c:
            seq = c.execute(
                'INSERT INTO edit_quality_reviews(project,owner,reviewer,export_id,revision,artifact,data,created) VALUES(?,?,?,?,?,?,?,?)',
                (project['id'], owner, reviewer, export['id'], export.get('revision'), artifact,
                 json.dumps(payload, ensure_ascii=False, sort_keys=True), time.time())).lastrowid
    finally:
        c.close()
    return dict(payload, receipt_id=seq, independent=True)


def latest(project, owner, export_id, artifact):
    c = connection()
    try:
        row = c.execute(
            'SELECT seq,reviewer,revision,data FROM edit_quality_reviews WHERE project=? AND owner=? AND export_id=? AND artifact=? ORDER BY seq DESC LIMIT 1',
            (project['id'], owner, export_id, artifact)).fetchone()
        if not row:
            return None
        data = json.loads(row[3])
        checked = {k: v for k, v in data.items() if k != 'receipt_sha256'}
        expected = _hash({
            'project': project['id'], 'owner': owner, 'reviewer': row[1],
            'export_id': export_id, 'revision': row[2], 'data': checked,
        })
        if data.get('receipt_sha256') != expected or row[1] == owner:
            raise ValueError('剪辑独立审阅记录未通过完整性核对')
        return dict(data, receipt_id=row[0], independent=True)
    finally:
        c.close()
