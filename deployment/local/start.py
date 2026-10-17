"""One API process and one provider process; no generation at startup."""
import os,sys,time,subprocess,signal
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from gateway import app as gateway
email=os.environ.get('ADMIN_EMAIL','').strip().lower();password=os.environ.get('ADMIN_PASSWORD','')
if not email or len(password)<12:raise SystemExit('Configure ADMIN_EMAIL and ADMIN_PASSWORD (12+ characters) in .env')
with gateway.db() as c:
    existing=c.execute('SELECT id,role FROM users WHERE email=?',(email,)).fetchone()
    if not existing:
        c.execute('INSERT INTO users(email,password_hash,verified,quota,used,created_at,role) VALUES(?,?,1,-1,0,?,?)',(email,gateway.digest(password),int(time.time()),'admin'))
    elif existing['role']!='admin':raise SystemExit('Configured admin email belongs to a regular account; no automatic privilege change performed.')
children=[]
def stop(*args):
    for p in children:
        if p.poll() is None:p.terminate()
    for p in children:
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill()
    sys.exit(0)
for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
for module,port in [('harness.models.kling_studio:app',int(os.getenv('PROVIDER_PORT','30081'))),('gateway.app:app',int(os.getenv('STUDIO_PORT','30080')))]:
    children.append(subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','0.0.0.0' if module=='gateway.app:app' else '127.0.0.1','--port',str(port),'--workers','1'],cwd=root))
while all(p.poll() is None for p in children):time.sleep(1)
stop()
