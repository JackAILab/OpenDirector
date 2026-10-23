"""Create local-only secrets once, without overwriting existing configuration."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[2]
f=root/'.env'
if f.exists():
    print('.env already exists; kept unchanged.')
else:
    password=secrets.token_urlsafe(18)
    f.write_text('ADMIN_EMAIL=admin@example.com\nADMIN_PASSWORD='+password+'\nH3_ADMIN_KEY='+secrets.token_hex(32)+'\nH3_SITE_SESSION_SECRET='+secrets.token_hex(32)+'\nCREATIVE_MODEL_URL=\nCREATIVE_MODEL=\n')
    f.chmod(0o600)
    print('Created .env (0600). Read ADMIN_PASSWORD locally; change ADMIN_EMAIL before startup.')
(root/'secrets').mkdir(exist_ok=True,mode=0o700)
(root/'secrets/director-key').touch(mode=0o600,exist_ok=True)

(root/'secrets/kling').mkdir(exist_ok=True,mode=0o700)
