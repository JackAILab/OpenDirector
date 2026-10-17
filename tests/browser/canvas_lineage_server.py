"""Local browser fixture: temporary database, fixed pixels, no model provider calls."""
import sys, tempfile, sqlite3, types, io, asyncio, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi import FastAPI,HTTPException
from PIL import Image
from harness.studio import store,api,image_api
from harness.tools import creative_image
from harness.models import studio_image
import uvicorn
for name in ('ffmpeg','ffprobe'):
 binary=Path('/opt/visualstation/creative-runtime/bin')/name
 if binary.is_file():os.environ.setdefault('CREATIVE_'+name.upper(),str(binary))
root=Path(tempfile.mkdtemp(prefix='canvas-lineage-acceptance-'));store.DATA=root;api.DATA=root
app=FastAPI()
@app.get('/acceptance/identity')
def identity():return {'fixture':'canvas-lineage-fixed-pixels','paid_calls':False}
def db():return sqlite3.connect(root/'users.sqlite3')
with db() as c:
 c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)');c.execute('INSERT INTO users VALUES(1,1,0,20)')
def auth(value):
 if value not in ('Bearer fixture','Bearer other'):raise HTTPException(401)
 return {'id':1 if value=='Bearer fixture' else 2,'quota':20,'used':0}
# No provider call: exercise the real Tool/Runner/asset receipt with fixed pixels.
def generated(model,prompt,aspect,directory,reference):
 if isinstance(reference,list):reference=reference[0]
 if reference and '像素观察' in prompt:
  b=io.BytesIO();Image.new('RGB',(640,360),'#d18b52').save(b,'PNG');return b.getvalue()
 if reference:return reference.read_bytes()
 b=io.BytesIO();Image.new('RGB',(640,360),'#315369').save(b,'PNG');return b.getvalue()
creative_image.generate=generated
specs=[{'id':'hunyuan-image-v2.0-general-edit','label':'测试参考编辑（固定图片）','available':True,'mode':'edit','credits':1,'region_composite':True,'region_brush':True,'max_references':3}, {'id':'hunyuan-image-v3.0','label':'测试生成（固定图片）','available':True,'mode':'text','credits':1}]
image_api.image_models=lambda:specs;studio_image.image_models=lambda:specs
async def no_direct(*args):raise RuntimeError('No director calls allowed in fixture')
api.direct=no_direct
api.install(types.SimpleNamespace(app=app,db=db,require_session=auth,require_site_access=lambda _:None))
uvicorn.run(app,host='127.0.0.1',port=30129,log_level='warning')
