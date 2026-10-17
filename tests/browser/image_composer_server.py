"""Isolated three-image UI acceptance, real storage and fixed model bytes, no paid calls."""
import hashlib,io,sqlite3,sys,tempfile,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi import FastAPI,HTTPException
from PIL import Image
from harness.studio import api,store,image_api
from harness.models import studio_image
from harness.tools import creative_image
import uvicorn
root=Path(tempfile.mkdtemp(prefix='image-composer-acceptance-'));store.DATA=root;api.DATA=root
fixtures=root/'fixtures';fixtures.mkdir();calls=[]
for color in ('red','blue','green'):
 Image.new('RGB',(360,240),color).save(fixtures/(color+'.png'))
def db():return sqlite3.connect(root/'users.sqlite3')
with db() as c:
 c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)');c.execute('INSERT INTO users VALUES(1,1,0,20)')
def auth(value):
 if value not in ('Bearer fixture','Bearer other'):raise HTTPException(401)
 return {'id':1 if value=='Bearer fixture' else 2,'used':0,'quota':20}
def generate(model,prompt,aspect,directory,reference):
 refs=reference if isinstance(reference,list) else [reference] if reference else []
 calls.append(dict(model=model,prompt=prompt,references=[hashlib.sha256(p.read_bytes()).hexdigest() for p in refs]))
 return refs[0].read_bytes() if refs else (fixtures/'red.png').read_bytes()
creative_image.generate=generate
specs=[dict(m,available=True) for m in studio_image.IMAGE_MODELS]
image_api.image_models=lambda:specs;studio_image.image_models=lambda:specs
async def no_direct(*args):raise RuntimeError('No director calls allowed')
api.direct=no_direct;app=FastAPI()
@app.get('/acceptance/identity')
def identity():
 with db() as c:used=c.execute('SELECT used FROM users').fetchone()[0]
 return dict(fixture='image-composer-fixed-model',fixtures=str(fixtures),calls=calls,used=used,paid_calls=0)
api.install(types.SimpleNamespace(app=app,db=db,require_session=auth,require_site_access=lambda _:None))
uvicorn.run(app,host='127.0.0.1',port=30132,log_level='warning')
