"""Account-owned immutable recipe versions and favorites; no public publishing."""
import json
import secrets
import time
from fastapi import HTTPException
from harness.studio import store
from harness.tools.creative_skills import build_revision


def connection():
    c=store.connection()
    c.executescript('''
      CREATE TABLE IF NOT EXISTS creative_skills(id TEXT PRIMARY KEY, owner INTEGER NOT NULL, version INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS creative_skill_versions(id TEXT, version INTEGER, data TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(id,version));
      CREATE TABLE IF NOT EXISTS creative_skill_favorites(owner INTEGER, id TEXT, PRIMARY KEY(owner,id));
    ''')
    return c


def get(sid,owner,version=None):
    with connection() as c:
        row=c.execute('SELECT version FROM creative_skills WHERE id=? AND owner=?',(sid,owner)).fetchone()
        if not row: raise HTTPException(404,'找不到这个 Skill')
        version=version or row[0]
        record=c.execute('SELECT data FROM creative_skill_versions WHERE id=? AND version=?',(sid,version)).fetchone()
    if not record: raise HTTPException(404,'找不到这个 Skill 版本')
    return json.loads(record[0])


def mine(owner):
    with connection() as c:
        rows=c.execute('SELECT v.data FROM creative_skills s JOIN creative_skill_versions v ON s.id=v.id AND s.version=v.version WHERE s.owner=? ORDER BY v.created DESC',(owner,)).fetchall()
        favorites=[r[0] for r in c.execute('SELECT id FROM creative_skill_favorites WHERE owner=?',(owner,))]
    return {'skills':[json.loads(r[0]) for r in rows], 'favorites':favorites}


def history(sid,owner):
    get(sid,owner)
    with connection() as c:
        rows=c.execute('SELECT version,created,data FROM creative_skill_versions WHERE id=? ORDER BY version DESC',(sid,)).fetchall()
    return [{'version':v,'created_at':ts,'title':json.loads(data)['title']} for v,ts,data in rows]


def create(owner,content,parent=None):
    sid='custom-'+secrets.token_hex(12)
    previous=dict(parent or {})
    if parent: previous['parent']={'id':parent['id'],'version':parent['version']}
    recipe=build_revision(content,previous,sid=sid,version=1)
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT COUNT(*) FROM creative_skills WHERE owner=?',(owner,)).fetchone()[0]>=100:
            raise HTTPException(422,'最多保存 100 个个人 Skill')
        c.execute('INSERT INTO creative_skills VALUES(?,?,?)',(sid,owner,1))
        c.execute('INSERT INTO creative_skill_versions VALUES(?,?,?,?)',(sid,1,json.dumps(recipe,ensure_ascii=False),time.time()))
    return recipe


def update(sid,owner,base_version,content):
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT version FROM creative_skills WHERE id=? AND owner=?',(sid,owner)).fetchone()
        if not row: raise HTTPException(404,'找不到这个 Skill')
        if row[0]!=base_version: raise HTTPException(409,'Skill 已有新版本，请重新打开后编辑；当前输入尚未保存')
        if base_version>=100: raise HTTPException(422,'此 Skill 已有 100 个版本，请另存一份')
        previous=json.loads(c.execute('SELECT data FROM creative_skill_versions WHERE id=? AND version=?',(sid,base_version)).fetchone()[0])
        recipe=build_revision(content,previous,sid=sid,version=base_version+1)
        c.execute('INSERT INTO creative_skill_versions VALUES(?,?,?,?)',(sid,recipe['version'],json.dumps(recipe,ensure_ascii=False),time.time()))
        c.execute('UPDATE creative_skills SET version=? WHERE id=?',(recipe['version'],sid))
    return recipe


def favorite(sid,owner,enabled):
    with connection() as c:
        if enabled: c.execute('INSERT OR IGNORE INTO creative_skill_favorites VALUES(?,?)',(owner,sid))
        else: c.execute('DELETE FROM creative_skill_favorites WHERE owner=? AND id=?',(owner,sid))
    return {'id':sid,'favorite':enabled}
