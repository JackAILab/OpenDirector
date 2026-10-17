"""Authenticated quota gateway for a MiniMax H3 SGLang deployment."""
from __future__ import annotations

import asyncio, hashlib, hmac, json, os, re, secrets, smtplib, sqlite3, time
from email.message import EmailMessage
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("H3_GATEWAY_DB", "/code/minimax-h3-gateway/data.sqlite3"))
UPSTREAM = os.getenv("H3_SGLANG_URL", "http://127.0.0.1:30010").rstrip("/")
ADMIN_KEY = os.getenv("H3_ADMIN_KEY", "")
EXTERNAL_H3_URL = os.getenv("H3_EXTERNAL_URL", "").rstrip("/")
EXTERNAL_H3_KEY_FILE = os.getenv("H3_EXTERNAL_KEY_FILE", "")
DEFAULT_QUOTA = int(os.getenv("H3_DEFAULT_QUOTA", "0"))
LOCAL_DEV_MODE = os.getenv("H3_LOCAL_DEV_MODE", "0") == "1"
EMAIL_VERIFICATION_REQUIRED = os.getenv("H3_EMAIL_VERIFICATION_REQUIRED", "1") == "1"
LOCAL_PROVIDER = os.getenv("H3_LOCAL_PROVIDER", "demo")
PRIMARY_PROVIDER = os.getenv("H3_PRIMARY_PROVIDER", "")
if PRIMARY_PROVIDER and PRIMARY_PROVIDER not in {"kling", "minimax-h3"}:
    raise RuntimeError("H3_PRIMARY_PROVIDER must be kling or minimax-h3")
SITE_PASSWORD = os.getenv("H3_SITE_PASSWORD", "")
SITE_SESSION_SECRET = os.getenv("H3_SITE_SESSION_SECRET", "") or SITE_PASSWORD
PUBLIC_DIR = Path(__file__).with_name("public")
ARTIFACT_DIR = Path(os.environ["H3_ARTIFACT_DIR"]) if os.getenv("H3_ARTIFACT_DIR") else None
MODEL_LOG_DIR = Path(os.getenv("H3_MODEL_LOG_DIR", "")) if os.getenv("H3_MODEL_LOG_DIR") else None
CODE_TTL = 15 * 60
MAX_ACTIVE_JOBS = max(1, int(os.getenv("H3_MAX_ACTIVE_JOBS", "2")))
MAX_ACTIVE_PER_USER = max(1, int(os.getenv("H3_MAX_ACTIVE_PER_USER", "1")))
_worker_lock = asyncio.Lock()
_worker_cursor = 0

app = FastAPI(title="MiniMax H3 API", version="1.0.0")


def primary_provider() -> str:
    # Preserve legacy local setups while allowing real providers in production.
    return PRIMARY_PROVIDER or (LOCAL_PROVIDER if LOCAL_DEV_MODE else "minimax-h3")


@app.middleware("http")
async def independent_site_gate(request: Request, call_next):
    # Health stays probeable by the tunnel/orchestrator. Interactive and API
    # documentation surfaces require the standalone site password; API calls
    # made with a previously issued H3 key remain usable without a browser.
    if request.url.path in {"/docs", "/redoc", "/openapi.json"} and not site_authorized(request):
        return JSONResponse({"detail": "Site access password required"}, status_code=403)
    return await call_next(request)


def site_cookie_value() -> str:
    if not SITE_SESSION_SECRET:
        return ""
    return hmac.new(SITE_SESSION_SECRET.encode(), b"visualstation-site", hashlib.sha256).hexdigest()


def site_authorized(request: Request) -> bool:
    if not SITE_PASSWORD:
        return True
    return hmac.compare_digest(request.cookies.get("h3_site_access", ""), site_cookie_value())


def require_site_access(request: Request) -> None:
    if not site_authorized(request):
        raise HTTPException(403, "Site access password required")


class SiteAccessIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@app.get("/account", include_in_schema=False)
def site_home(request: Request):
    # The installed creative studio owns the account presentation; this gateway
    # continues to own sessions, verification, roles and billing APIs.
    studio_root = os.getenv("CREATIVE_STUDIO_ROOT")
    if studio_root:
        portal = Path(studio_root) / "tools/agent_studio/discover.html"
        if portal.is_file():
            return FileResponse(portal, media_type="text/html", headers={"Cache-Control": "no-store"})
    if not PUBLIC_DIR.joinpath("index.html").is_file():
        return JSONResponse({"service": "MiniMax H3 API", "model": "MiniMax-H3"})
    response = FileResponse(PUBLIC_DIR / "index.html", media_type="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/site/access", include_in_schema=False)
def site_access(body: SiteAccessIn, request: Request):
    if not SITE_PASSWORD:
        return {"ok": True, "configured": False}
    if not hmac.compare_digest(body.password, SITE_PASSWORD):
        raise HTTPException(401, "Invalid site password")
    response = JSONResponse({"ok": True, "configured": True})
    response.set_cookie("h3_site_access", site_cookie_value(), max_age=60 * 60 * 24 * 30,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return response


@app.post("/site/logout", include_in_schema=False)
def site_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("h3_site_access", path="/")
    return response


@app.get("/site/config", include_in_schema=False)
def site_config(request: Request):
    require_site_access(request)
    primary = primary_provider()
    return {"model": "Kling" if primary == "kling" else "MiniMax-H3", "default_quota": DEFAULT_QUOTA,
            "registration": "email_verification" if EMAIL_VERIFICATION_REQUIRED else "direct", "site_password_configured": bool(SITE_PASSWORD),
            "local_dev": LOCAL_DEV_MODE, "local_provider": primary, "primary_provider": primary,
            "providers": list(dict.fromkeys([primary] + (["minimax-h3"] if external_workers() else [])))}

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

class RegisterIn(BaseModel):
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=7, max_length=200)
    password_confirm: str = Field(min_length=7, max_length=200)

class VerifyIn(BaseModel):
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)
    code: str = Field(pattern=r"^[0-9]{6}$")

class LoginIn(BaseModel):
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)

class GrantIn(BaseModel):
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)
    quota: int = Field(ge=-1, le=2_147_483_647)

class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    quota: int = Field(default=-1, ge=-1, le=1_000_000)

class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=7, max_length=200)
    new_password_confirm: str = Field(min_length=7, max_length=200)

class ResendIn(BaseModel):
    email: str = Field(max_length=320, pattern=EMAIL_PATTERN)

@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0, quota INTEGER NOT NULL DEFAULT 0,
        used INTEGER NOT NULL DEFAULT 0, api_key_hash TEXT, created_at INTEGER NOT NULL,
        role TEXT NOT NULL DEFAULT 'user');
      CREATE TABLE IF NOT EXISTS jobs(
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS job_details(
        job_id TEXT PRIMARY KEY, title TEXT NOT NULL, provider TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS job_upstreams(
        job_id TEXT PRIMARY KEY, upstream TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS submissions(
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, state TEXT NOT NULL,
        upstream_id TEXT, created_at INTEGER NOT NULL, upstream TEXT);
      CREATE TABLE IF NOT EXISTS request_keys(
        user_id INTEGER NOT NULL, key TEXT NOT NULL, body_hash TEXT NOT NULL,
        submission_id TEXT NOT NULL, PRIMARY KEY(user_id,key));
      CREATE TABLE IF NOT EXISTS submission_responses(
        submission_id TEXT PRIMARY KEY, status INTEGER NOT NULL,
        body BLOB NOT NULL, content_type TEXT);
      CREATE TABLE IF NOT EXISTS api_keys(
        key_hash TEXT PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL);
      CREATE TABLE IF NOT EXISTS browser_sessions(
        key_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS access_tokens(
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL,
        key_hash TEXT UNIQUE NOT NULL, key_prefix TEXT NOT NULL,
        quota INTEGER NOT NULL DEFAULT -1, used INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL, last_used_at INTEGER, revoked_at INTEGER);
      CREATE INDEX IF NOT EXISTS idx_access_tokens_user ON access_tokens(user_id,created_at);
      CREATE TABLE IF NOT EXISTS usage_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        token_id TEXT, submission_id TEXT, job_id TEXT,
        delta INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_usage_events_user_time ON usage_events(user_id,created_at DESC,id DESC);
      CREATE TABLE IF NOT EXISTS rate_limits(
        bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS codes(email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL);
    """)
    # Keep upgrades compatible with databases created by the single-worker
    # gateway. SQLite cannot add a column inside CREATE TABLE IF NOT EXISTS.
    for table, column in (("submissions", "upstream"),):
        columns = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    columns = {row[1] for row in c.execute("PRAGMA table_info(users)")}
    if "role" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    try:
        with c:
            yield c
    finally:
        c.close()

def digest(value: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    out = hashlib.scrypt(value.encode(), salt=salt, n=2**14, r=8, p=1).hex()
    return f"{salt.hex()}${out}"

def check(value: str, encoded: str) -> bool:
    try:
        salt_hex, expected = encoded.split("$", 1)
        got = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(got, expected)
    except Exception:
        return False

def send_code(email: str, code: str) -> None:
    if LOCAL_DEV_MODE:
        print(f"[local-dev] verification code for {email}: {code}", flush=True)
        return
    host = os.getenv("SMTP_HOST")
    if not host:
        raise HTTPException(503, "Email service is not configured")
    msg = EmailMessage(); msg["Subject"] = "MiniMax H3 verification code"; msg["From"] = os.environ["SMTP_FROM"]; msg["To"] = email
    msg.set_content(f"Your MiniMax H3 verification code is {code}. It expires in 15 minutes.")
    with smtplib.SMTP_SSL(host, int(os.getenv("SMTP_PORT", "465")), timeout=15) as s:
        if os.getenv("SMTP_USER"): s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)

def user_from_key(key: str | None) -> sqlite3.Row:
    if not key or not key.startswith("h3_") or len(key) != 46:
        raise HTTPException(401, "Invalid API key")
    with db() as c:
        row = c.execute("SELECT users.* FROM users JOIN api_keys ON users.id=api_keys.user_id WHERE key_hash=? AND verified=1",
                        (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
        if not row:
            row = c.execute("SELECT users.* FROM users JOIN browser_sessions ON users.id=browser_sessions.user_id "
                            "WHERE browser_sessions.key_hash=? AND expires_at>? AND verified=1",
                            (hashlib.sha256(key.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            row = c.execute("SELECT users.* FROM users JOIN access_tokens ON users.id=access_tokens.user_id "
                            "WHERE access_tokens.key_hash=? AND access_tokens.revoked_at IS NULL AND users.verified=1",
                            (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
    if row: return row
    raise HTTPException(401, "Invalid API key")

def require_session(authorization: str | None) -> sqlite3.Row:
    key = bearer(authorization)
    row = user_from_key(key)
    with db() as c:
        found = c.execute("SELECT 1 FROM api_keys WHERE key_hash=? AND user_id=?",
                          (hashlib.sha256(key.encode()).hexdigest(), row["id"])).fetchone()
        if not found:
            found = c.execute("SELECT 1 FROM browser_sessions WHERE key_hash=? AND user_id=? AND expires_at>?",
                              (hashlib.sha256(key.encode()).hexdigest(), row["id"], int(time.time()))).fetchone()
    if not found:
        raise HTTPException(403, "Use your browser session to manage account settings")
    return row

def require_admin(authorization: str | None) -> sqlite3.Row:
    row = require_session(authorization)
    if row["role"] != "admin":
        raise HTTPException(403, "管理员权限 required")
    return row

def throttle(action: str, email: str, request: Request, limit: int, seconds: int):
    now = int(time.time())
    peer = request.client.host if request.client else "unknown"
    # Never trust a caller-supplied X-Forwarded-For header here.
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("DELETE FROM rate_limits WHERE expires_at<=?", (now,))
        for kind, value, maximum in (("email", email, limit), ("ip", peer, limit * 5)):
            bucket = action + ":" + kind + ":" + hashlib.sha256(value.encode()).hexdigest()
            row = c.execute("SELECT count,expires_at FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
            if row and row["count"] >= maximum:
                raise HTTPException(429, "Too many attempts", headers={"Retry-After": str(row["expires_at"]-now)})
            c.execute("INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
                      (bucket, now + seconds))

def bearer(authorization: str | None) -> str | None:
    return authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None

def token_context(c: sqlite3.Connection, key: str | None, user_id: int) -> sqlite3.Row | None:
    """Resolve an API token inside the billing transaction.

    Browser session keys have no per-token limit. Recheck revocation under the
    write lock so a revoked token cannot be charged as a browser session.
    """
    if not key or not key.startswith("h3_"):
        return None  # Test fixtures use short stand-in keys.
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    token = c.execute("SELECT * FROM access_tokens WHERE key_hash=? AND user_id=? AND revoked_at IS NULL",
                      (key_hash,user_id)).fetchone()
    if token:
        return token
    session = c.execute("SELECT 1 FROM api_keys WHERE key_hash=? AND user_id=?", (key_hash,user_id)).fetchone()
    if not session:
        session = c.execute("SELECT 1 FROM browser_sessions WHERE key_hash=? AND user_id=? AND expires_at>?",
                            (key_hash,user_id,int(time.time()))).fetchone()
    if not session:
        raise HTTPException(401, "Invalid API key")
    return None

def external_workers() -> list[dict]:
    """Private deployment registry. Credential values never enter API responses."""
    source = os.getenv('H3_EXTERNAL_WORKERS_FILE')
    if not source:
        return ([{'name':'primary','url':EXTERNAL_H3_URL,'key_file':EXTERNAL_H3_KEY_FILE,'enabled':True}]
                if EXTERNAL_H3_URL else [])
    try:
        workers=json.loads(Path(source).read_text())
        if not isinstance(workers,list): raise ValueError()
        seen=set()
        for item in workers:
            if not isinstance(item,dict) or not isinstance(item.get('url'),str) or not item['url'].startswith(('http://','https://')):
                raise ValueError()
            item['url']=item['url'].rstrip('/')
            if item['url'] in seen or not isinstance(item.get('key_file'),str): raise ValueError()
            seen.add(item['url'])
        return workers
    except (OSError,ValueError,TypeError):
        raise HTTPException(503,'H3 worker registry unavailable')


def upstream_headers(url: str) -> dict[str, str]:
    workers=external_workers()
    # Retain old-worker credentials for jobs created before the pool was enabled.
    if EXTERNAL_H3_URL and not any(w['url']==EXTERNAL_H3_URL for w in workers):
        workers.append({'url':EXTERNAL_H3_URL,'key_file':EXTERNAL_H3_KEY_FILE})
    for worker in workers:
        if worker['url']!=url: continue
        try: key=Path(worker['key_file']).read_text().strip()
        except OSError: raise HTTPException(503,'H3 connection credential unavailable')
        if not key: raise HTTPException(503,'H3 connection credential unavailable')
        return {'Authorization':'Bearer '+key}
    return {}


async def select_external_worker() -> str:
    workers=[w for w in external_workers() if w.get('enabled',True)]
    if not os.getenv('H3_EXTERNAL_WORKERS_FILE') and len(workers)==1:
        upstream_headers(workers[0]['url'])
        return workers[0]['url']
    with db() as c:
        occupied={row[0] for row in c.execute("SELECT DISTINCT upstream FROM submissions WHERE state IN ('pending','accepted','uncertain')")}
    for worker in workers:
        url=worker['url']
        if url in occupied: continue
        try:
            upstream_headers(url)
            async with httpx.AsyncClient(timeout=3,trust_env=False) as client:
                response=await client.get(url+'/healthz')
            if response.status_code==200: return url
        except (httpx.HTTPError,HTTPException): continue
    raise HTTPException(503,'H3 workers are unavailable or busy; no credits reserved')


def request_credits(body: dict, provider: str) -> int:
    if not os.getenv('CREATIVE_STUDIO_ROOT'):
        return 1
    from harness.models.video_catalog import quote
    try:
        return quote(provider, body.get('model'), body.get('target', {}).get('duration_seconds', 5))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, str(exc))


def worker_urls() -> tuple[str, ...]:
    configured = os.getenv("H3_SGLANG_URLS", "")
    urls = tuple(item.strip().rstrip("/") for item in configured.split(",") if item.strip())
    return urls or (UPSTREAM,)

async def select_worker() -> str:
    """Round-robin across configured workers without sharing request state."""
    global _worker_cursor
    urls = worker_urls()
    async with _worker_lock:
        selected = urls[_worker_cursor % len(urls)]
        _worker_cursor = (_worker_cursor + 1) % len(urls)
    return selected

@app.get("/healthz")
async def healthz():
    async def probe(url: str) -> tuple[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f"{url}/healthz" if url in external_urls else f"{url}/health")
            return url, response.status_code == 200
        except Exception:
            return url, False
    external_urls = tuple(w["url"] for w in external_workers() if w.get("enabled",True))
    probe_urls = (*worker_urls(), *external_urls)
    results = dict(await asyncio.gather(*(probe(url) for url in probe_urls)))
    healthy = [url for url, ok in results.items() if ok]
    primary = primary_provider()
    model = "Kling" if primary == "kling" else "MiniMax-H3"
    return JSONResponse({"ok": bool(healthy), "model": model, "provider": primary, "workers": {url: results[url] for url in results}},
                        status_code=200 if healthy else 503)

@app.post("/auth/register")
def register(body: RegisterIn, request: Request):
    require_site_access(request)
    if body.password != body.password_confirm:
        raise HTTPException(400, "两次输入的密码不一致")
    email = body.email.strip().lower()
    throttle("register", email, request, 3, 3600)
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        existing = c.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
        if existing and existing["verified"]:
            raise HTTPException(409, "Email already registered")
        if existing:
            # A previous SMTP failure leaves an unverified row behind. Allow
            # the user to retry registration and replace the pending password.
            c.execute("UPDATE users SET password_hash=?,verified=? WHERE email=?", (digest(body.password), 0 if EMAIL_VERIFICATION_REQUIRED else 1, email))
        else:
            c.execute("INSERT INTO users(email,password_hash,verified,quota,created_at) VALUES(?,?,?,?,?)", (email,digest(body.password),0 if EMAIL_VERIFICATION_REQUIRED else 1,DEFAULT_QUOTA,int(time.time())))
        if EMAIL_VERIFICATION_REQUIRED:
            code = f"{secrets.randbelow(1_000_000):06d}"; c.execute("INSERT OR REPLACE INTO codes VALUES(?,?,?)", (email,digest(code),int(time.time())+CODE_TTL))
        else:
            c.execute("DELETE FROM codes WHERE email=?", (email,))
    if not EMAIL_VERIFICATION_REQUIRED:
        return {"message":"Account created", "verification_required":False}
    try: send_code(email, code)
    except Exception:
        raise HTTPException(503, "Email delivery unavailable; retry with /auth/resend")
    result = {"message":"Verification code sent", "verification_required":True}
    if LOCAL_DEV_MODE:
        result["dev_code"] = code
    return result

@app.post("/auth/resend")
def resend(body: ResendIn, request: Request):
    require_site_access(request)
    if not EMAIL_VERIFICATION_REQUIRED:
        raise HTTPException(400, "Email verification is currently disabled")
    email = body.email.strip().lower()
    throttle("resend", email, request, 3, 900)
    code = f"{secrets.randbelow(1_000_000):06d}"
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
        if not row or row["verified"]:
            return {"message": "If verification is pending, a code will be sent"}
        c.execute("INSERT OR REPLACE INTO codes VALUES(?,?,?)", (email, digest(code), int(time.time())+CODE_TTL))
    try:
        send_code(email, code)
    except Exception:
        raise HTTPException(503, "Email delivery unavailable")
    result = {"message": "If verification is pending, a code will be sent"}
    if LOCAL_DEV_MODE:
        result["dev_code"] = code
    return result

@app.post("/auth/verify")
def verify(body: VerifyIn, request: Request):
    require_site_access(request)
    email = body.email.strip().lower()
    throttle("verify", email, request, 5, CODE_TTL)
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM codes WHERE email=?", (email,)).fetchone()
        if not row or row["expires_at"] < time.time() or not check(body.code, row["code_hash"]): raise HTTPException(400,"Invalid or expired code")
        c.execute("UPDATE users SET verified=1 WHERE email=?", (email,)); c.execute("DELETE FROM codes WHERE email=?", (email,))
    return {"message":"Email verified"}

@app.post("/auth/login")
def login(body: LoginIn, request: Request):
    require_site_access(request)
    email = body.email.strip().lower()
    throttle("login", email, request, 10, 900)
    with db() as c: row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not check(body.password,row["password_hash"]): raise HTTPException(401,"Invalid credentials")
    if not row["verified"]: raise HTTPException(403,"Email not verified")
    key = "h3_" + secrets.token_urlsafe(32)
    with db() as c:
        c.execute("INSERT INTO browser_sessions VALUES(?,?,?)",
                  (hashlib.sha256(key.encode()).hexdigest(), row["id"], int(time.time()) + 30 * 86400))
    return {"api_key":key,"quota_remaining":None if row["quota"] < 0 else row["quota"]-row["used"]}

@app.post("/auth/revoke")
def revoke(authorization: str | None = Header(default=None)):
    row = require_session(authorization)
    with db() as c:
        digest = hashlib.sha256(bearer(authorization).encode()).hexdigest()
        c.execute("DELETE FROM api_keys WHERE user_id=? AND key_hash=?", (row["id"], digest))
        c.execute("DELETE FROM browser_sessions WHERE user_id=? AND key_hash=?", (row["id"], digest))
    return {"message": "API key revoked"}

@app.get("/me")
async def me(authorization: str | None = Header(default=None)):
    row=user_from_key(bearer(authorization)); unlimited = row["quota"] < 0
    return {"email":row["email"],"role":row["role"],"quota":None if unlimited else row["quota"],"used":row["used"],"remaining":None if unlimited else row["quota"]-row["used"],"unlimited":unlimited}

@app.post("/profile/password")
async def change_password(body: PasswordChangeIn, authorization: str | None = Header(default=None)):
    row = require_session(authorization)
    if body.new_password != body.new_password_confirm:
        raise HTTPException(400, "两次输入的密码不一致")
    if not check(body.current_password, row["password_hash"]):
        raise HTTPException(401, "当前密码不正确")
    with db() as c:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (digest(body.new_password), row["id"]))
    return {"message":"密码已更新"}

@app.get("/tokens")
async def list_tokens(authorization: str | None = Header(default=None)):
    row = require_session(authorization)
    with db() as c:
        tokens = c.execute(
            "SELECT id,name,key_prefix,quota,used,created_at,last_used_at,revoked_at "
            "FROM access_tokens WHERE user_id=? ORDER BY created_at DESC,id DESC", (row["id"],)
        ).fetchall()
    return {"tokens": [dict(item) for item in tokens]}

@app.post("/tokens")
async def create_token(body: TokenCreateIn, authorization: str | None = Header(default=None)):
    row = require_session(authorization)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Token name is required")
    token = "h3_" + secrets.token_urlsafe(32)
    token_id = secrets.token_hex(12)
    now = int(time.time())
    with db() as c:
        count = c.execute("SELECT COUNT(*) FROM access_tokens WHERE user_id=? AND revoked_at IS NULL", (row["id"],)).fetchone()[0]
        if count >= 20:
            raise HTTPException(429, "Too many active API tokens")
        c.execute("INSERT INTO access_tokens(id,user_id,name,key_hash,key_prefix,quota,created_at) VALUES(?,?,?,?,?,?,?)",
                  (token_id,row["id"],name,hashlib.sha256(token.encode()).hexdigest(),token[:12],body.quota,now))
    return {"id":token_id,"name":name,"quota":body.quota,"token":token,"created_at":now}

@app.post("/tokens/{token_id}/revoke")
async def revoke_token(token_id: str, authorization: str | None = Header(default=None)):
    row = require_session(authorization)
    with db() as c:
        changed = c.execute("UPDATE access_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                            (int(time.time()), token_id, row["id"]))
        if changed.rowcount != 1:
            raise HTTPException(404, "Token not found")
    return {"ok":True}

@app.get("/usage")
async def usage(email: str | None = None, authorization: str | None = Header(default=None)):
    caller = user_from_key(bearer(authorization))
    if email and email.strip().lower() != caller["email"]:
        require_admin(authorization)
    await refresh_active_jobs()
    with db() as c:
        target = c.execute("SELECT id,email,quota,used FROM users WHERE email=?",
                           ((email or caller["email"]).strip().lower(),)).fetchone()
        if not target:
            raise HTTPException(404, "User not found")
        items = c.execute(
            "SELECT e.id,e.token_id,e.submission_id,e.job_id,e.delta,e.reason,e.created_at,"
            "t.name AS token_name,s.state AS submission_state "
            "FROM usage_events e LEFT JOIN access_tokens t ON t.id=e.token_id "
            "LEFT JOIN submissions s ON s.id=e.submission_id "
            "WHERE e.user_id=? ORDER BY e.created_at DESC,e.id DESC LIMIT 100", (target["id"],)
        ).fetchall()
        tracked = c.execute("SELECT COALESCE(SUM(-delta),0) FROM usage_events WHERE user_id=?", (target["id"],)).fetchone()[0]
        daily = c.execute(
            "SELECT date(created_at,'unixepoch') AS day, SUM(-delta) AS credits "
            "FROM usage_events WHERE user_id=? AND created_at>=? "
            "GROUP BY day ORDER BY day DESC LIMIT 30", (target["id"], int(time.time())-30*86400)
        ).fetchall()
    unlimited = target["quota"] < 0
    return {"email":target["email"],"quota":None if unlimited else target["quota"],
            "used":target["used"],"remaining":None if unlimited else target["quota"]-target["used"],
            "unlimited":unlimited,"unitemized_used":max(0,target["used"]-tracked),
            "events":[dict(item) for item in items],"daily":[dict(item) for item in daily]}

@app.get("/jobs")
async def jobs(authorization: str | None = Header(default=None)):
    row = user_from_key(bearer(authorization))
    await refresh_active_jobs()
    with db() as c:
        records = c.execute(
            "SELECT j.id,j.created_at,d.title,d.provider,"
            "(SELECT state FROM submissions s WHERE s.upstream_id=j.id AND s.user_id=j.user_id ORDER BY s.created_at DESC LIMIT 1) AS state "
            "FROM jobs j LEFT JOIN job_details d ON d.job_id=j.id "
            "WHERE j.user_id=? ORDER BY j.created_at DESC LIMIT 20",
            (row["id"],),
        ).fetchall()
    return {"jobs": [dict(item) for item in records]}

@app.post("/admin/grant")
async def grant(body: GrantIn, x_admin_key: str | None = Header(default=None)):
    if not ADMIN_KEY or not hmac.compare_digest(x_admin_key or "", ADMIN_KEY): raise HTTPException(403,"Forbidden")
    with db() as c:
        cur=c.execute("UPDATE users SET quota=? WHERE email=?",(body.quota,body.email.strip().lower()))
        if cur.rowcount != 1: raise HTTPException(404,"User not found")
    return {"email":body.email,"quota":body.quota}

@app.get("/admin/users")
async def admin_users(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as c:
        rows = c.execute("SELECT email,verified,quota,used,role,created_at FROM users ORDER BY created_at DESC").fetchall()
    return {"users":[dict(row) for row in rows]}

@app.post("/admin/users/quota")
async def admin_user_quota(body: GrantIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as c:
        cur = c.execute("UPDATE users SET quota=? WHERE email=?", (body.quota, body.email.strip().lower()))
        if cur.rowcount != 1:
            raise HTTPException(404, "用户不存在")
    return {"email":body.email.strip().lower(),"quota":body.quota}

def finalize_submission(c: sqlite3.Connection, submission_id: str, status: str) -> None:
    terminal = "completed" if status == "completed" else "failed"
    changed = c.execute("UPDATE submissions SET state=? WHERE id=? AND state='accepted'", (terminal, submission_id))
    if changed.rowcount != 1 or terminal == "completed":
        return
    submission = c.execute("SELECT user_id FROM submissions WHERE id=?", (submission_id,)).fetchone()
    charge = c.execute("SELECT token_id,job_id,delta FROM usage_events WHERE submission_id=? AND delta<0 ORDER BY id DESC LIMIT 1",
                       (submission_id,)).fetchone()
    credits = -charge["delta"] if charge else 1
    c.execute("UPDATE users SET used=MAX(0,used-?) WHERE id=?", (credits,submission["user_id"]))
    if charge and charge["token_id"]:
        c.execute("UPDATE access_tokens SET used=MAX(0,used-?) WHERE id=?", (credits,charge["token_id"]))
    if charge:
        c.execute("INSERT INTO usage_events(user_id,token_id,submission_id,job_id,delta,reason,created_at) "
                  "VALUES(?,?,?,?,?,'failed_refund',?)",
                  (submission["user_id"], charge["token_id"], submission_id, charge["job_id"], credits, int(time.time())))


async def refresh_active_jobs():
    """Release capacity only when upstream positively reports a terminal state.

    Durable reservations survive process restarts. Missing jobs and transport
    failures need reconciliation and must not silently release GPU capacity.
    """
    with db() as c:
        active = c.execute("SELECT id,upstream_id,upstream FROM submissions WHERE state='accepted'").fetchall()
    if not active:
        return
    async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
        for submission in active:
            try:
                upstream = submission["upstream"] or UPSTREAM
                response = await client.request("GET", f"{upstream}/v1/videos/{submission['upstream_id']}", headers=upstream_headers(upstream))
                if response.status_code == 404:
                    status = "deleted"
                elif not response.is_success:
                    continue
                else:
                    status = response.json().get("status")
                if status not in ("completed", "failed", "cancelled", "canceled", "deleted"):
                    continue
            except (httpx.HTTPError, ValueError, AttributeError):
                continue
            with db() as c:
                finalize_submission(c, submission["id"], status)


def public_upstream_response(response: httpx.Response) -> tuple[bytes, str | None]:
    """Remove backend filesystem details before returning JSON to callers."""
    content_type = response.headers.get("content-type")
    if not content_type or "json" not in content_type.lower():
        return response.content, content_type
    try:
        body = response.json()
    except ValueError:
        return response.content, content_type

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()
                    if key not in {"file_path", "file_paths", "output_path", "output_paths"}}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    import json
    return json.dumps(scrub(body), separators=(",", ":")).encode(), content_type


def scrub_saved_response(body: bytes, content_type: str | None) -> bytes:
    if not content_type or "json" not in content_type.lower():
        return body
    try:
        value = json.loads(body)
        def scrub(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: scrub(item) for key, item in value.items()
                        if key not in {"file_path", "file_paths", "output_path", "output_paths"}}
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value
        return json.dumps(scrub(value), separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return body


def model_log_progress(job_id: str) -> dict[str, Any] | None:
    """Read the active H3 sampling counter until the model exposes native progress.

    A job-specific output path in the model log anchors the subsequent tqdm
    entries. Never use the latest global counter for an unrelated job.
    """
    if not MODEL_LOG_DIR or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", job_id):
        return None
    try:
        logs = sorted(MODEL_LOG_DIR.glob("fl2va-memory-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for path in logs:
            if not path.is_file() or path.stat().st_size > 4_000_000:
                continue
            raw = path.read_text(errors="replace")
            marker = f"/{job_id}.mp4"
            start = raw.rfind(marker)
            if start < 0:
                continue
            section = raw[start:]
            # Stop at the next job's request metadata, if another request starts.
            next_job = re.search(r"output_file_path:\s+[^\r\n]+\.mp4", section[len(marker):])
            if next_job:
                section = section[:len(marker) + next_job.start()]
            samples = re.findall(r"minimax_h3 denoise:\s*\d+%[^\r\n]*?\s(\d+)/(\d+)\s*\[", section)
            if samples:
                done, total = map(int, samples[-1])
                if 0 <= done <= total and total > 0:
                    encoding = "[MiniMaxH3DenoisingStage] finished" in section
                    return {"status": "in_progress", "progress": 97 if encoding else min(95, round(done / total * 95)),
                            "stage": "encoding" if encoding else "denoising", "steps_completed": done, "steps_total": total,
                            "progress_source": "model_log"}
            if "[MiniMaxH3DenoisingStage] started" in section:
                return {"status": "in_progress", "progress": 0, "stage": "denoising",
                        "steps_completed": 0, "progress_source": "model_log"}
            return {"status": "in_progress", "progress": 0, "stage": "preparing",
                    "progress_source": "model_log"}
    except OSError:
        return None
    return None


def status_with_live_progress(body: bytes, content_type: str | None, video_id: str) -> bytes:
    if not content_type or "json" not in content_type.lower():
        return body
    try:
        value = json.loads(body)
        if not isinstance(value, dict) or value.get("status") not in {"queued", "in_progress", "running", "processing"}:
            return body
        progress = model_log_progress(video_id)
        if progress:
            value.update(progress)
            return json.dumps(value, separators=(",", ":")).encode()
    except (ValueError, TypeError):
        pass
    return body


def completed_artifact(video_id: str, user_id: int) -> Path | None:
    """Read only a completed, owned artifact from an explicitly mounted archive."""
    if ARTIFACT_DIR is None or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", video_id):
        return None
    with db() as c:
        completed = c.execute(
            "SELECT 1 FROM jobs j JOIN submissions s ON s.upstream_id=j.id "
            "AND s.user_id=j.user_id WHERE j.id=? AND j.user_id=? AND s.state='completed'",
            (video_id, user_id),
        ).fetchone()
    if not completed:
        return None
    try:
        root = ARTIFACT_DIR.resolve(strict=True)
        path = (root / (video_id + ".mp4")).resolve(strict=True)
        if path.parent == root and path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        pass
    return None


async def proxy(request: Request, path: str, authorization: str | None):
    auth_key = bearer(authorization)
    row = user_from_key(auth_key)
    submission_id = None
    upstream = None
    token_id = None
    if request.method == "POST":
        key = request.headers.get("idempotency-key", "")
        if not key or len(key) > 128 or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
            raise HTTPException(400, "Idempotency-Key required (1-128 printable ASCII characters)")
        payload_buffer = bytearray()
        async for chunk in request.stream():
            if len(payload_buffer) + len(chunk) > 1_048_576:
                raise HTTPException(413, "Request too large")
            payload_buffer.extend(chunk)
        payload = bytes(payload_buffer)
        body_hash = hashlib.sha256(payload).hexdigest()
        submission_id = secrets.token_hex(16)
        # An accepted request remains replayable even when every worker is down.
        with db() as c:
            previous = c.execute("SELECT * FROM request_keys WHERE user_id=? AND key=?", (row["id"], key)).fetchone()
            if previous:
                if previous["body_hash"] != body_hash:
                    raise HTTPException(409, "Idempotency-Key already used with a different request")
                saved = c.execute("SELECT * FROM submission_responses WHERE submission_id=?", (previous["submission_id"],)).fetchone()
                if saved:
                    return Response(content=scrub_saved_response(saved["body"], saved["content_type"]),
                                    status_code=saved["status"], media_type=saved["content_type"])
                raise HTTPException(409, {"message": "Submission pending or awaiting reconciliation", "submission_id": previous["submission_id"]})
        try:
            decoded = json.loads(payload)
        except ValueError:
            raise HTTPException(422, "Invalid JSON request")
        if not isinstance(decoded, dict):
            raise HTTPException(422, "Request must be an object")
        provider = decoded.pop("provider", None)
        default_provider = primary_provider()
        if provider == "minimax-h3" and external_workers():
            await refresh_active_jobs()
            upstream = await select_external_worker()
            upstream_headers(upstream)  # Fail before reserving credits.
        elif provider is None or provider == default_provider:
            upstream = await select_worker()
        else:
            raise HTTPException(422, "Requested provider is not configured")
        credits = request_credits(decoded, provider or default_provider)
        if (provider or default_provider)=="minimax-h3":
            decoded.pop("model",None)
        payload = json.dumps(decoded, separators=(",", ":")).encode()
        await refresh_active_jobs()
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            token = token_context(c, auth_key, row["id"])
            token_id = token["id"] if token else None
            previous = c.execute("SELECT * FROM request_keys WHERE user_id=? AND key=?", (row["id"], key)).fetchone()
            if previous:
                if previous["body_hash"] != body_hash:
                    raise HTTPException(409, "Idempotency-Key already used with a different request")
                saved = c.execute("SELECT * FROM submission_responses WHERE submission_id=?", (previous["submission_id"],)).fetchone()
                if saved:
                    return Response(content=scrub_saved_response(saved["body"], saved["content_type"]),
                                    status_code=saved["status"], media_type=saved["content_type"])
                raise HTTPException(409, {"message": "Submission pending or awaiting reconciliation", "submission_id": previous["submission_id"]})
            active = c.execute("SELECT COUNT(*),COALESCE(SUM(user_id=?),0) FROM submissions WHERE state IN ('pending','accepted','uncertain')",
                               (row["id"],)).fetchone()
            if provider == 'minimax-h3' and os.getenv('H3_EXTERNAL_WORKERS_FILE'):
                occupied=c.execute("SELECT 1 FROM submissions WHERE upstream=? AND state IN ('pending','accepted','uncertain')",(upstream,)).fetchone()
                if occupied: raise HTTPException(429,'Selected H3 worker became busy; no credits reserved')
            if active[0] >= MAX_ACTIVE_JOBS or active[1] >= MAX_ACTIVE_PER_USER:
                raise HTTPException(429, "Generation capacity busy; retry with the same Idempotency-Key",
                                    headers={"Retry-After": "15"})
            changed = c.execute(
                "UPDATE users SET used=used+? WHERE id=? AND verified=1 AND (quota<0 OR used+?<=quota)",
                (credits,row["id"],credits),
            )
            if changed.rowcount != 1:
                raise HTTPException(429, "Quota exhausted")
            if token:
                token_changed = c.execute("UPDATE access_tokens SET used=used+?,last_used_at=? "
                                          "WHERE id=? AND revoked_at IS NULL AND (quota<0 OR used+?<=quota)",
                                          (credits,int(time.time()),token_id,credits))
                if token_changed.rowcount != 1:
                    raise HTTPException(429, "API token quota exhausted")
            c.execute("INSERT INTO submissions(id,user_id,state,upstream_id,created_at,upstream) VALUES(?,?,?,NULL,?,?)",
                      (submission_id, row["id"], "pending", int(time.time()), upstream))
            c.execute("INSERT INTO request_keys VALUES(?,?,?,?)", (row["id"], key, body_hash, submission_id))
            c.execute("INSERT INTO usage_events(user_id,token_id,submission_id,delta,reason,created_at) "
                      "VALUES(?,?,?,?,'generation',?)", (row["id"],token_id,submission_id,-credits,int(time.time())))
    else:
        payload = b""
        video_id = path.split("/")[2]
        with db() as c:
            owned = c.execute("SELECT j.id, u.upstream FROM jobs j LEFT JOIN job_upstreams u ON u.job_id=j.id WHERE j.id=? AND j.user_id=?",
                              (video_id, row["id"])).fetchone()
        if not owned:
            raise HTTPException(404, "Video not found")
        artifact = completed_artifact(video_id, row["id"])
        if artifact is not None and path.count("/") == 2:
            return JSONResponse({"id": video_id, "status": "completed", "progress": 100})
        upstream = owned["upstream"] or UPSTREAM
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10), trust_env=False) as client:
            r = await client.request(request.method, f"{upstream}/{path}", content=payload,
                                     headers={"content-type": request.headers.get("content-type", "application/json"),
                                              **upstream_headers(upstream),
                                              **({"Idempotency-Key": submission_id} if submission_id else {})})
    except httpx.HTTPError:
        # A transport failure may occur after upstream acceptance. Retain the
        # reservation for reconciliation rather than silently double-spending it.
        if submission_id:
            with db() as c:
                c.execute("UPDATE submissions SET state='uncertain' WHERE id=?", (submission_id,))
        raise HTTPException(503, {"message": "Upstream unavailable", "submission_id": submission_id})
    if submission_id:
        if r.is_success:
            try:
                video_id = r.json()["id"]
                if not isinstance(video_id, str) or not video_id:
                    raise ValueError("Invalid id")
            except (ValueError, KeyError, TypeError):
                with db() as c:
                    c.execute("UPDATE submissions SET state='uncertain' WHERE id=?", (submission_id,))
                raise HTTPException(502, {"message": "Invalid upstream response", "submission_id": submission_id})
            with db() as c:
                c.execute("INSERT INTO jobs VALUES(?,?,?)", (video_id, row["id"], int(time.time())))
                title = decoded.get("prompt", "")
                title = " ".join(title.split())[:120] if isinstance(title, str) else ""
                c.execute("INSERT INTO job_details VALUES(?,?,?)", (video_id, title, provider or default_provider))
                c.execute("INSERT OR REPLACE INTO job_upstreams(job_id,upstream) VALUES(?,?)",
                          (video_id, upstream))
                c.execute("UPDATE submissions SET state='accepted',upstream_id=? WHERE id=?", (video_id, submission_id))
                c.execute("UPDATE usage_events SET job_id=? WHERE submission_id=? AND delta<0", (video_id,submission_id))
                body, content_type = public_upstream_response(r)
                c.execute("INSERT INTO submission_responses VALUES(?,?,?,?)", (submission_id, r.status_code, body, content_type))
        elif 400 <= r.status_code < 500:
            with db() as c:
                c.execute("UPDATE users SET used=used-? WHERE id=?", (credits,row["id"]))
                if token_id:
                    c.execute("UPDATE access_tokens SET used=MAX(0,used-?) WHERE id=?", (credits,token_id))
                c.execute("UPDATE submissions SET state='rejected' WHERE id=?", (submission_id,))
                c.execute("INSERT INTO usage_events(user_id,token_id,submission_id,delta,reason,created_at) "
                          "VALUES(?,?,?,?,'rejected_refund',?)", (row["id"],token_id,submission_id,credits,int(time.time())))
                body, content_type = public_upstream_response(r)
                c.execute("INSERT INTO submission_responses VALUES(?,?,?,?)", (submission_id, r.status_code, body, content_type))
        else:
            with db() as c:
                c.execute("UPDATE submissions SET state='uncertain' WHERE id=?", (submission_id,))
    if not submission_id and path.count("/") == 2 and r.is_success:
        try:
            current_status = r.json().get("status")
        except (ValueError, AttributeError):
            current_status = None
        if current_status in {"completed", "failed", "cancelled", "canceled", "deleted"}:
            with db() as c:
                item = c.execute("SELECT id FROM submissions WHERE upstream_id=? AND user_id=? AND state='accepted'",
                                 (video_id,row["id"])).fetchone()
                if item:
                    finalize_submission(c,item["id"],current_status)
    body, content_type = public_upstream_response(r)
    if not submission_id and path.count("/") == 2 and r.is_success:
        body = status_with_live_progress(body, content_type, video_id)
    return Response(content=body, status_code=r.status_code, media_type=content_type)

@app.post("/v1/videos")
async def create_video(request: Request, authorization: str | None = Header(default=None)): return await proxy(request,"v1/videos",authorization)
@app.get("/v1/videos/{video_id}")
async def video_status(video_id: str, request: Request, authorization: str | None = Header(default=None)): return await proxy(request, f"v1/videos/{video_id}", authorization)
class VideoStreamResponse(StreamingResponse):
    """Release upstream connections on completion, disconnect, or send failure."""
    def __init__(self, upstream, client):
        self.upstream = upstream
        self.client = client
        allowed = {"content-type", "content-length", "content-range", "accept-ranges", "content-encoding"}
        super().__init__(upstream.aiter_raw(), status_code=upstream.status_code,
                         headers={k: v for k, v in upstream.headers.items() if k in allowed})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.upstream.aclose()
            finally:
                await self.client.aclose()


@app.get("/v1/videos/{video_id}/content")
async def video_content(video_id: str, request: Request, authorization: str | None = Header(default=None)):
    row = user_from_key(bearer(authorization))
    with db() as c:
        owned = c.execute("SELECT j.id, u.upstream FROM jobs j LEFT JOIN job_upstreams u ON u.job_id=j.id WHERE j.id=? AND j.user_id=?", (video_id, row["id"])).fetchone()
    if not owned:
        raise HTTPException(404, "Video not found")
    artifact = completed_artifact(video_id, row["id"])
    if artifact is not None:
        return FileResponse(artifact, media_type="video/mp4", filename=video_id + ".mp4")
    upstream_url = owned["upstream"] or UPSTREAM
    client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10), trust_env=False)
    try:
        headers = {"accept-encoding": "identity", **upstream_headers(upstream_url)}
        if "range" in request.headers:
            headers["range"] = request.headers["range"]
        upstream = await client.send(client.build_request("GET", f"{upstream_url}/v1/videos/{video_id}/content", headers=headers), stream=True)
    except BaseException as exc:
        await client.aclose()
        if isinstance(exc, httpx.HTTPError):
            raise HTTPException(503, "Upstream unavailable") from exc
        raise
    return VideoStreamResponse(upstream, client)


# Optional local Agent workspace: provider adapters and the production runner
# remain owned by AdvertiseAgent; this gateway owns authentication and credits.
if os.getenv("CREATIVE_STUDIO_ROOT"):
    import sys
    sys.path.insert(0, os.environ["CREATIVE_STUDIO_ROOT"])
    from harness.studio.api import install as install_creative_studio
    install_creative_studio(sys.modules[__name__])
    @app.get("/", include_in_schema=False)
    def creative_home():
        return FileResponse(Path(os.environ["CREATIVE_STUDIO_ROOT"]) / "tools/agent_studio/discover.html", headers={"Cache-Control":"no-store"})
else:
    app.add_api_route("/", site_home, methods=["GET"], include_in_schema=False)
