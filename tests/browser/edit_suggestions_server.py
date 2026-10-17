"""Isolated acceptance server: real media/tools, fixed planning-model response, no provider calls."""
import json, os, sqlite3, subprocess, sys, tempfile, types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi import FastAPI, HTTPException
from harness.studio import store,api
from harness.agents.creative_editor import CreativeDirectorModel
import uvicorn
# Borrow executable paths only, never model credentials or URLs.
pid=subprocess.check_output(['systemctl','show','visualstation-local','--property=MainPID','--value'],text=True).strip()
for part in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0'):
    key,_,value=part.partition(b'=')
    if key.decode(errors='ignore') in ('CREATIVE_GSAP','CREATIVE_FFMPEG','CREATIVE_FFPROBE','CREATIVE_HYPERFRAMES'):os.environ[key.decode()]=value.decode()
root=Path(tempfile.mkdtemp(prefix='edit-suggestions-acceptance-'));store.DATA=root;api.DATA=root
fixtures=root/'fixtures';fixtures.mkdir()
for name,hz in [('red',440),('blue',880)]:
 subprocess.run([os.environ['CREATIVE_FFMPEG'],'-v','error','-f','lavfi','-i',f'color={name}:s=320x180:r=24:d=3','-f','lavfi','-i',f'sine=frequency={hz}:sample_rate=48000:duration=3','-shortest','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(fixtures/(name+'.mp4'))],check=True)
app=FastAPI();calls=[];speech_calls=[];retake_calls=[]
retake_fixture=os.getenv('EDIT_RETAKE_FIXTURE')=='1'
if retake_fixture:
 os.environ['CREATIVE_RETAKE_INPUT_DIR']=str(root/'retake-inputs')
 os.environ['CREATIVE_RETAKE_POLL_SECONDS']='.1'
 subprocess.run([os.environ['CREATIVE_FFMPEG'],'-v','error','-f','lavfi','-i','color=blue:s=1280x720:r=30:d=3','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=3','-shortest','-c:v','libx264','-preset','ultrafast','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(fixtures/'retake.mp4')],check=True)
 from fastapi import Header, Request
 from fastapi.responses import FileResponse
 from harness.models.kling_retake import validate_request
 @app.post('/v1/videos')
 async def retake_submit(request:Request,authorization:str|None=Header(None),idempotency_key:str|None=Header(None)):
  assert authorization=='Bearer fixture' and idempotency_key.startswith('retake-')
  body=await request.json();assert body.pop('provider')=='kling';validate_request(body)
  retake_calls.append(idempotency_key)
  return {'id':'fixture-retake','status':'processing'}
 @app.get('/v1/videos/fixture-retake')
 def retake_status():return {'status':'completed'}
 @app.get('/v1/videos/fixture-retake/content')
 def retake_content():return FileResponse(fixtures/'retake.mp4',media_type='video/mp4')
speech_fixture=os.getenv('EDIT_SPEECH_FIXTURE')=='1'
if speech_fixture:
 from harness.models import creative_speech
 from harness.studio import edit_api
 def fixed_speech(wav,language):
  assert wav.is_file();speech_calls.append(1)
  return {'language':'en','language_probability':.99,'segments':[{'words':[
   {'start':.5,'end':.9,'text':'Hello','probability':.99},
   {'start':1.1,'end':1.6,'text':' jacket.','probability':.4}]}]}
 creative_speech.transcribe=fixed_speech
 edit_api.speech_settings=lambda:dict(available=True,model='acceptance-fixture',local=True)
@app.get('/acceptance/identity')
def identity():return {'fixture':'edit-retake-fixed-provider' if retake_fixture else 'edit-speech-fixed-model' if speech_fixture else 'edit-suggestions-fixed-model','fixtures':str(fixtures),'model_calls':len(calls),'speech_calls':len(speech_calls),'retake_calls':len(retake_calls),'paid_calls':False}
def db():return sqlite3.connect(root/'users.sqlite3')
with db() as c:
 c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,verified INTEGER,used INTEGER,quota INTEGER)');c.execute('INSERT INTO users VALUES(1,1,0,20)')
def auth(value):
 if value not in ('Bearer fixture','Bearer other'):raise HTTPException(401)
 return {'id':1 if value=='Bearer fixture' else 2,'quota':20,'used':0}
async def fixed_response(self,messages):
    content=messages[1]['content'];data=json.loads(content[0]['text']);spec=data['edit'];calls.append(1)
    assert len([x for x in content if x['type']=='image_url'])==8
    spec['clips'].reverse();spec['clips'][0]['transition']={'kind':'fade_black','duration':1};spec['clips'][-1]['transition']={'kind':'cut','duration':0}
    return {'spec':spec,'summary':'测试建议：先蓝后红，使用 1 秒淡黑。','reasons':[{'text':'固定模型测试，引用了真实采样帧；不构成视觉质量评价。','frames':['frame_1','frame_5']}]}
CreativeDirectorModel.complete=fixed_response
async def no_direct(*args):raise RuntimeError('No director calls allowed in fixture')
api.direct=no_direct
api.install(types.SimpleNamespace(app=app,db=db,require_session=auth,require_site_access=lambda _:None))
uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('EDIT_ACCEPTANCE_PORT','30130')),log_level='warning')
