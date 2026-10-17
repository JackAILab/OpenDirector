"""Owned scene UI with a fixed director and no provider generation."""
import sqlite3,sys,tempfile,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi import FastAPI,HTTPException
from harness.studio import api,store
import uvicorn
root=Path(tempfile.mkdtemp(prefix='scene-shots-'));store.DATA=root;api.DATA=root
app=FastAPI()
def db():return sqlite3.connect(root/'users.sqlite3')
with db() as c:c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)');c.execute('INSERT INTO users VALUES(1,1,0,20)')
def auth(value):
 if value not in ('Bearer fixture','Bearer other'):raise HTTPException(401)
 return {'id':1 if value=='Bearer fixture' else 2,'used':0,'quota':20}
async def director(p,mode):
 return dict(reply='固定方案',brief={'product':'皮夹克验收'},questions=[],assumptions=[],decisions=[],shots=[dict(id='s'+str(i),title='展示',prompt='Visible product detail',audio_prompt='Original restrained music',caption='外观细节',rationale='结构展示',start=i*5,duration=5,state='planned') for i in range(3)])
async def no_production(*args):raise RuntimeError('No paid generation allowed')
api.direct=director;api.production=no_production
api.install(types.SimpleNamespace(app=app,db=db,require_session=auth,require_site_access=lambda _:None))
@app.get('/acceptance/identity')
def identity():
 with db() as c:used=c.execute('SELECT used FROM users').fetchone()[0]
 return dict(fixture='scene-shots-fixed-director',used=used,paid_calls=0)
uvicorn.run(app,host='127.0.0.1',port=30134,log_level='warning')
