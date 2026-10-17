"""Private series membership and explicit version-bound permission receipts."""
import hashlib
import json
import secrets
import time
from harness.learning.episodes import _journal_connection
from harness.studio import store

POLICY='creation-learning-consent-v1'
POLICY_TEXT='可选择允许当前版本的创作输入、方案、工具过程与成片，经独立质量、隐私与使用权审查后用于改进广告导演模型；公开数据另行选择。只处理本作品当前版本，不授权其他作品或未来版本。不改变正常创作。撤回将阻止后续导出；已经发布的数据或训练结果无法自动收回。'


def connection():
    c=_journal_connection()
    c.execute('CREATE TABLE IF NOT EXISTS series(id TEXT PRIMARY KEY,owner INTEGER,label TEXT,created REAL)')
    c.execute('''CREATE TABLE IF NOT EXISTS learning_controls(seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT,owner INTEGER,revision INTEGER,kind TEXT,data TEXT,created REAL)''')
    return c


def list_series(owner):
    c=connection()
    try:return [dict(id=r[0],label=r[1]) for r in c.execute('SELECT id,label FROM series WHERE owner=? ORDER BY created',(owner,))]
    finally:c.close()


def create_series(owner,label):
    label=label.strip()
    if not 1<=len(label)<=80:raise ValueError('系列名称应为1–80字')
    identity=secrets.token_hex(12);c=connection()
    try:
        with c:c.execute('INSERT INTO series VALUES(?,?,?,?)',(identity,owner,label,time.time()))
    finally:c.close()
    return {'id':identity,'label':label}


def _append(c,p,owner,kind,data):
    c.execute('INSERT INTO learning_controls(project,owner,revision,kind,data,created) VALUES(?,?,?,?,?,?)',
        (p['id'],owner,p['revision'],kind,json.dumps(data,sort_keys=True),time.time()))


def set_family(p,owner,identity):
    c=connection()
    try:
        with c:
            if identity and not c.execute('SELECT 1 FROM series WHERE id=? AND owner=?',(identity,owner)).fetchone():
                raise KeyError('系列不存在')
            _append(c,p,owner,'family',{'family_id':identity or 'project:'+p['id']})
    finally:c.close()


def current_artifact(p):
    if p.get('state')!='completed' or not p.get('artifact'):return None
    path=(store.DATA/p['artifact']).resolve()
    if not path.is_relative_to(store.DATA.resolve()) or not path.is_file():raise ValueError('成片文件不可读取')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def set_consent(p,owner,artifact,training,public,policy,policy_sha256):
    if policy!=POLICY or policy_sha256!=hashlib.sha256(POLICY_TEXT.encode()).hexdigest():raise ValueError('授权说明已更新，请重新查看')
    if not artifact or artifact!=current_artifact(p):raise ValueError('成片版本已变化，请重新查看')
    if public and not training:raise ValueError('公开训练数据需要先允许训练使用')
    if type(training) is not bool or type(public) is not bool:raise ValueError('必须明确选择授权范围')
    c=connection()
    try:
        with c:_append(c,p,owner,'consent',{'policy':policy,'policy_sha256':hashlib.sha256(POLICY_TEXT.encode()).hexdigest(),'artifact_sha256':artifact,
            'training':training,'public_dataset':public,'training_eligible':False})
    finally:c.close()


def status(p,owner,artifact=None):
    c=connection()
    try:
        family=c.execute("SELECT data FROM learning_controls WHERE project=? AND owner=? AND kind='family' ORDER BY seq DESC LIMIT 1",(p['id'],owner)).fetchone()
        row=c.execute("SELECT data FROM learning_controls WHERE project=? AND owner=? AND revision=? AND kind='consent' ORDER BY seq DESC LIMIT 1",(p['id'],owner,p['revision'])).fetchone()
        consent=json.loads(row[0]) if row else {}
        if not artifact or consent.get('artifact_sha256')!=artifact or consent.get('policy')!=POLICY or consent.get('policy_sha256')!=hashlib.sha256(POLICY_TEXT.encode()).hexdigest():consent={}
        from harness.learning import review
        try:quality=review.latest(p,owner,artifact) if artifact else None
        except ValueError:quality={'decision':'integrity_failed'}
        quality_summary={k:quality.get(k) for k in ('decision','receipt_id','receipt_sha256','rubric_version','independent')} if quality else None
        if quality_summary is not None and isinstance(quality.get('ratings'), dict):
            scores=[item.get('score') for item in quality['ratings'].values()
                    if isinstance(item, dict) and type(item.get('score')) is int]
            if scores:
                quality_summary['mean_score']=round(sum(scores)/len(scores), 2)
                quality_summary['min_score']=min(scores)
        review_status='独立质量审阅已通过；仍需隐私与使用权审查，尚不可训练' if quality and quality.get('decision')=='passed' else '尚需独立质量、隐私与使用权审查；授权不等于可训练'
        return {'revision':p['revision'],'artifact_sha256':artifact,'family_id':json.loads(family[0])['family_id'] if family else 'project:'+p['id'],
            'policy':POLICY,'policy_sha256':hashlib.sha256(POLICY_TEXT.encode()).hexdigest(),'policy_text':POLICY_TEXT,'training':consent.get('training') is True,
            'public_dataset':consent.get('public_dataset') is True,'training_eligible':False,
            'independent_quality':quality_summary,'review_status':review_status}
    finally:c.close()
