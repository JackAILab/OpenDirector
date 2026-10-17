"""Independent human quality receipts. No training eligibility is inferred."""
import json
import time
from harness.learning import governance
from harness.learning.episodes import _hash

RUBRIC=('product_fidelity','claim_accuracy','narrative','visual_quality','audio_quality')


def connection():
    c=governance.connection()
    c.execute('''CREATE TABLE IF NOT EXISTS quality_reviews(seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT,owner INTEGER,reviewer INTEGER,revision INTEGER,artifact TEXT,data TEXT,created REAL)''')
    return c


def record(p,owner,reviewer,artifact,decision,ratings,checks):
    if reviewer==owner:raise ValueError('独立审阅者不能是作品创建者')
    actual=governance.current_artifact(p)
    if not actual or actual!=artifact:raise ValueError('成片已变化，请重新审阅')
    controls=governance.status(p,owner,actual)
    if not controls['training']:raise ValueError('当前版本未授权训练审阅')
    if decision not in ('passed','needs_changes','rejected'):raise ValueError('审阅结论无效')
    if set(ratings)!=set(RUBRIC):raise ValueError('请逐项填写质量评价')
    clean={}
    for key in RUBRIC:
        item=ratings[key];score=item.get('score');evidence=item.get('evidence','').strip()
        if type(score) is not int or not 0<=score<=5 or not 5<=len(evidence)<=500:raise ValueError('每项需要0–5分和具体审阅依据')
        clean[key]={'score':score,'evidence':evidence}
    if set(checks)!=set(('full_video_watched','audio_listened','product_facts_checked')) or any(type(v) is not bool for v in checks.values()):raise ValueError('请明确填写审阅范围')
    if decision=='passed' and (not all(checks.values()) or any(i['score']<3 for i in clean.values())):
        raise ValueError('通过需要完整观看、听音及核实商品事实，且各项至少3分')
    payload={'schema':'visualagent.independent-quality-review.v1','rubric_version':'ad-quality-v1',
        'decision':decision,'ratings':clean,'checks':checks,'artifact_sha256':artifact,
        'training_eligible':False}
    payload['receipt_sha256']=_hash({'project':p['id'],'owner':owner,'reviewer':reviewer,'revision':p['revision'],'data':payload})
    c=connection()
    try:
        with c:
            seq=c.execute('INSERT INTO quality_reviews(project,owner,reviewer,revision,artifact,data,created) VALUES(?,?,?,?,?,?,?)',
                (p['id'],owner,reviewer,p['revision'],artifact,json.dumps(payload,ensure_ascii=False,sort_keys=True),time.time())).lastrowid
    finally:c.close()
    return dict(payload,receipt_id=seq)


def latest(p,owner,artifact):
    c=connection()
    try:
        row=c.execute('SELECT seq,reviewer,data FROM quality_reviews WHERE project=? AND owner=? AND revision=? AND artifact=? ORDER BY seq DESC LIMIT 1',
            (p['id'],owner,p['revision'],artifact)).fetchone()
        if not row:return None
        data=json.loads(row[2]);checked={k:v for k,v in data.items() if k!='receipt_sha256'}
        if data.get('receipt_sha256')!=_hash({'project':p['id'],'owner':owner,'reviewer':row[1],'revision':p['revision'],'data':checked}) or row[1]==owner:raise ValueError('独立审阅记录未通过完整性核对')
        return dict(data,receipt_id=row[0],independent=True)
    finally:c.close()
