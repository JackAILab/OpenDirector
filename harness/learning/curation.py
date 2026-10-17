"""Independent privacy, rights and sanitization curation receipts."""
import hashlib
import json
import time
from harness.learning import governance
from harness.learning.episodes import _hash

GATES=('privacy_review','rights_review','sanitized_context_review')


def connection():
    c=governance.connection()
    c.execute('''CREATE TABLE IF NOT EXISTS curation_reviews(seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT,owner INTEGER,reviewer INTEGER,revision INTEGER,artifact TEXT,data TEXT,created REAL)''')
    return c


def record(p,owner,reviewer,artifact,decisions,note):
    if reviewer==owner:raise ValueError('独立策展人不能是作品创建者')
    actual=governance.current_artifact(p)
    if not actual or actual!=artifact:raise ValueError('成片已变化，请重新核对')
    controls=governance.status(p,owner,actual)
    if controls['training'] is not True:raise ValueError('当前版本未授权训练策展')
    if set(decisions)!=set(GATES) or any(type(v) is not bool for v in decisions.values()):raise ValueError('必须逐项明确三个门禁')
    note=note.strip()
    if not 10<=len(note)<=1000:raise ValueError('请填写10–1000字的核对依据')
    payload={'schema':'visualagent.learning-curation.v1','version':'curation-v1','decisions':dict(decisions),
        'note':note,'artifact_sha256':artifact,'training_eligible':False}
    payload['receipt_sha256']=_hash({'project':p['id'],'owner':owner,'reviewer':reviewer,'revision':p['revision'],'data':payload})
    c=connection()
    try:
        with c:
            seq=c.execute('INSERT INTO curation_reviews(project,owner,reviewer,revision,artifact,data,created) VALUES(?,?,?,?,?,?,?)',
                (p['id'],owner,reviewer,p['revision'],artifact,json.dumps(payload,ensure_ascii=False,sort_keys=True),time.time())).lastrowid
    finally:c.close()
    return dict(payload,receipt_id=seq)


def latest(p,owner,artifact):
    c=connection()
    try:
        row=c.execute('SELECT seq,reviewer,data FROM curation_reviews WHERE project=? AND owner=? AND revision=? AND artifact=? ORDER BY seq DESC LIMIT 1',
            (p['id'],owner,p['revision'],artifact)).fetchone()
        if not row:return None
        data=json.loads(row[2]);expected=_hash({'project':p['id'],'owner':owner,'reviewer':row[1],'revision':p['revision'],'data':{k:v for k,v in data.items() if k!='receipt_sha256'}})
        if row[1]==owner or data.get('receipt_sha256')!=expected:raise ValueError('策展记录完整性核对失败')
        return dict(data,receipt_id=row[0],independent=True)
    finally:c.close()
