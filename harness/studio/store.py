import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from fastapi import HTTPException
from harness.models.video_catalog import project_quote

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('CREATIVE_DATA_DIR', '/var/lib/visualstation-local/creative'))
LOCKS = {}
RUNNING = {}


def connection():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    c = sqlite3.connect(DATA/'projects.sqlite3', timeout=20)
    c.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, owner INTEGER, data TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, time REAL, stage TEXT, code TEXT, shot TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS provider_callback_events(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT NOT NULL,
        digest TEXT NOT NULL,
        target TEXT NOT NULL,
        status TEXT NOT NULL,
        projection TEXT NOT NULL,
        received_at REAL NOT NULL,
        job_digest TEXT NOT NULL,
        UNIQUE(project, digest)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS scene_asset_callback_events(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT NOT NULL,
        digest TEXT NOT NULL,
        intent TEXT NOT NULL,
        task TEXT NOT NULL,
        status TEXT NOT NULL,
        projection TEXT NOT NULL,
        received_at REAL NOT NULL,
        UNIQUE(project, digest)
    )''')
    return c


def load(pid, owner):
    with connection() as c: row = c.execute('SELECT data FROM projects WHERE id=? AND owner=?', (pid, owner)).fetchone()
    if not row: raise HTTPException(404, '找不到创作项目')
    return json.loads(row[0])


def save(p, owner):
    p['updated_at'] = time.time()
    with connection() as c:
        c.execute('INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (p['id'],owner,json.dumps(p,ensure_ascii=False)))


def _provider_target(p, job_id):
    film = p.get('film') if isinstance(p.get('film'), dict) else None
    if film and film.get('job_id') == job_id:
        return film, 'film'
    for shot in p.get('shots', []):
        if isinstance(shot, dict) and shot.get('job_id') == job_id:
            return shot, str(shot.get('id', 'shot'))[:48]
    for retake in (p.get('edit_retakes', {}) or {}).values():
        if isinstance(retake, dict) and retake.get('provider_job_id') == job_id:
            return retake, 'retake'
    return None, ''


def apply_provider_callback(pid, owner, job_id, digest, status, projection, observation, received_at):
    """Atomically apply a safe callback projection and its cross-process dedupe record."""
    with connection() as c:
        # The API lock only covers this process; IMMEDIATE serializes the
        # read/check/write sequence when two workers receive the same digest.
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT data FROM projects WHERE id=? AND owner=?', (pid, owner)).fetchone()
        if not row:
            raise HTTPException(404, '找不到回调对应的项目')
        p = json.loads(row[0])
        audit = c.execute(
            'SELECT target,status,projection,received_at FROM provider_callback_events WHERE project=? AND digest=?',
            (pid, digest)).fetchone()
        target, target_kind = _provider_target(p, job_id)
        if audit:
            prior_target, prior_status, prior_projection, prior_received = audit
            prior_projection = json.loads(prior_projection)
            return p, prior_target, True, target, {
                'status': prior_status,
                'projection': prior_projection,
                'received_at': prior_received,
            }
        if target is None:
            raise HTTPException(404, '找不到回调对应的任务')
        target['provider_callback'] = {
            'digest': digest, 'status': status, 'projection': projection,
            'trajectory': observation, 'received_at': received_at, 'training_eligible': False,
        }
        if observation:
            target['provider_trajectory'] = observation
        target['provider_resolution'] = 'callback_observed_awaiting_poll'
        p['updated_at'] = time.time()
        c.execute('UPDATE projects SET data=? WHERE id=? AND owner=?',
                  (json.dumps(p, ensure_ascii=False), pid, owner))
        c.execute('''INSERT INTO provider_callback_events
                     (project,digest,target,status,projection,received_at,job_digest)
                     VALUES(?,?,?,?,?,?,?)''',
                  (pid, digest, target_kind, status, json.dumps(projection, ensure_ascii=False),
                   received_at, hashlib.sha256(job_id.encode()).hexdigest()[:16]))
        return p, target_kind, False, target, None


def provider_callback_audit(pid, limit=24):
    with connection() as c:
        rows = c.execute('''SELECT seq,digest,target,status,projection,received_at
                            FROM provider_callback_events WHERE project=?
                            ORDER BY seq DESC LIMIT ?''', (pid, int(limit))).fetchall()
    result = []
    for seq, digest, target, status, projection, received_at in rows:
        result.append({'seq': seq, 'digest': digest, 'target': target, 'status': status,
                       'projection': json.loads(projection), 'received_at': received_at})
    return result


def apply_scene_asset_callback(pid, owner, intent_id, task_id, digest, status,
                               projection, received_at, result_asset_id=None):
    """Apply a bounded 3D asset callback and deduplicate by raw digest.

    The callback can only advance an existing, explicitly quoted asset intent;
    it cannot create a task, charge credits, or attach an unknown asset.
    """
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT data FROM projects WHERE id=? AND owner=?', (pid, owner)).fetchone()
        if not row:
            raise HTTPException(404, '找不到回调对应的项目')
        p = json.loads(row[0])
        audit = c.execute(
            'SELECT intent,task,status,projection,received_at FROM scene_asset_callback_events WHERE project=? AND digest=?',
            (pid, digest)).fetchone()
        if audit:
            prior_intent, prior_task, prior_status, prior_projection, prior_received = audit
            return p, True, {
                'intent_id': prior_intent, 'task_id': prior_task, 'status': prior_status,
                'projection': json.loads(prior_projection), 'received_at': prior_received,
            }
        intent = p.get('scene_asset_intent') if isinstance(p.get('scene_asset_intent'), dict) else None
        quote = p.get('scene_asset_quote') if isinstance(p.get('scene_asset_quote'), dict) else None
        if not intent or intent.get('id') != intent_id or not quote or quote.get('asset_intent_id') != intent_id:
            raise HTTPException(404, '找不到回调对应的 3D 资产任务')
        current_task = str(quote.get('provider_task_id') or intent.get('provider_task_id') or '')
        if current_task and current_task != task_id:
            raise HTTPException(409, '3D 资产任务标识已变化')
        if result_asset_id and result_asset_id not in p.get('scene_assets', {}):
            raise HTTPException(422, '回调引用的 GLB 资产不属于当前项目')
        quote['provider_task_id'] = task_id
        quote['provider_status'] = status
        if 'progress' in projection:
            quote['provider_progress'] = projection['progress']
        if result_asset_id:
            quote['result_asset_id'] = result_asset_id
            quote['approval_state'] = 'completed' if status == 'completed' else quote.get('approval_state', 'approved')
        elif status in ('failed', 'error', 'cancelled', 'canceled', 'uncertain'):
            quote['approval_state'] = 'failed'
        intent['provider_task_id'] = task_id
        p['updated_at'] = time.time()
        c.execute('UPDATE projects SET data=? WHERE id=? AND owner=?',
                  (json.dumps(p, ensure_ascii=False), pid, owner))
        c.execute('''INSERT INTO scene_asset_callback_events
                     (project,digest,intent,task,status,projection,received_at)
                     VALUES(?,?,?,?,?,?,?)''',
                  (pid, digest, intent_id, task_id, status,
                   json.dumps(projection, ensure_ascii=False), received_at))
        return p, False, None


def scene_asset_callback_audit(pid, limit=24):
    with connection() as c:
        rows = c.execute('''SELECT seq,digest,intent,task,status,projection,received_at
                            FROM scene_asset_callback_events WHERE project=?
                            ORDER BY seq DESC LIMIT ?''', (pid, int(limit))).fetchall()
    return [dict(zip(('seq','digest','intent_id','task_id','status','projection','received_at'),
                     (seq, digest, intent, task, status, json.loads(projection), received_at)))
            for seq, digest, intent, task, status, projection, received_at in rows]


def event(p, stage, code, shot=''):
    with connection() as c:
        seq=c.execute('INSERT INTO events(project,time,stage,code,shot) VALUES(?,?,?,?,?)',(p['id'],time.time(),stage,code,shot)).lastrowid
        row=c.execute('SELECT owner FROM projects WHERE id=?',(p['id'],)).fetchone()
    if row:
        try:
            from harness.learning.episodes import record_transition
            record_transition(p,row[0],seq,stage,code)
        except Exception:
            # Learning storage is ancillary: never fail or retry a production action.
            with connection() as c:
                c.execute('INSERT INTO events(project,time,stage,code,shot) VALUES(?,?,?,?,?)',
                    (p['id'],time.time(),'learning','transition_capture_failed',''))


def production_recovery_queue(p, limit=16):
    """Project unresolved production work into read-only recovery guidance.

    This is intentionally a UI-safe projection.  It contains no provider job
    handles, payloads, paths, credentials, or coordinates.  Every action is
    either a refresh/verification request or an explicit human review; none
    authorizes a new paid submission.
    """
    try:
        max_items = max(0, min(16, int(limit)))
    except (TypeError, ValueError):
        max_items = 16
    resolution_map = {
        'callback_observed_awaiting_poll': ('refresh_provider', False, '已收到回调，等待轮询确认'),
        'polling': ('refresh_provider', False, '供应商处理中，刷新只查询已有任务'),
        'provider_terminal_confirmed': ('verify_asset', False, '供应商已结束，等待素材技术核验'),
        'source_checking': ('verify_asset', False, '正在检查已下载素材'),
        'provider_terminal_uncertain': ('manual_review', True, '结果待核对，请人工确认后再决定下一步'),
        'provider_terminal_failed': ('manual_review', True, '供应商失败，请人工调整方案后再提交'),
    }
    queue = []
    seen = set()

    def add(kind, target_id, item, fallback_state=''):
        if len(queue) >= max_items or not isinstance(item, dict):
            return
        resolution = item.get('provider_resolution')
        mapped = resolution_map.get(resolution)
        if mapped is None and not (p.get('interrupted') and kind == 'film'):
            return
        action, requires_manual, message = mapped or (
            'refresh_existing', False, '服务中断，刷新只查询已有任务')
        key = (kind, str(target_id or ''))
        if key in seen:
            return
        seen.add(key)
        queue.append({
            'id': str(target_id or kind)[:64],
            'kind': kind,
            'state': str(item.get('state') or fallback_state)[:32],
            'resolution': str(resolution or 'interrupted')[:48],
            'action': action,
            'requires_manual': requires_manual,
            'can_resume': False,
            'message': message,
        })

    film = p.get('film') if isinstance(p.get('film'), dict) else None
    if film:
        add('film', 'film', film, p.get('state', ''))
    for shot in p.get('shots', []) if isinstance(p.get('shots'), list) else []:
        if isinstance(shot, dict):
            add('shot', shot.get('id', 'shot'), shot, shot.get('state', ''))
    retakes = p.get('edit_retakes', {})
    if isinstance(retakes, dict):
        for jid, retake in retakes.items():
            if isinstance(retake, dict):
                add('retake', retake.get('id') or jid, retake, retake.get('state', ''))
    if p.get('interrupted') and not any(item['action'] == 'refresh_existing' for item in queue):
        queue.insert(0, {
            'id': str(p.get('id', 'project'))[:64],
            'kind': 'project',
            'state': str(p.get('state') or 'interrupted')[:32],
            'resolution': 'interrupted',
            'action': 'refresh_existing',
            'requires_manual': False,
            'can_resume': False,
            'message': '服务中断，刷新只查询已有任务，不会重新提交',
        })
    return queue[:max_items]


def present(p, *, runtime_active=None):
    # Use the runtime observation from the same read as the project snapshot.
    # A worker may finish while expensive UI projections are being assembled.
    active = p['id'] in RUNNING if runtime_active is None else runtime_active
    p = dict(p)
    p['canvas_capabilities'] = {'groups': True}
    with connection() as c:
        rows = c.execute('SELECT seq,time,stage,code,shot FROM events WHERE project=? ORDER BY seq', (p['id'],)).fetchall()
    p['events'] = [dict(zip(('seq','time','stage','code','shot'), row)) for row in rows]
    p['provider_callback_audit'] = provider_callback_audit(p['id'])
    p['quote'] = project_quote(p)
    from harness.tools.canvas_lineage import lineage, layout_observation
    p['canvas_lineage'] = lineage(p)
    p['canvas_layout_observation'] = layout_observation(p)
    from harness.tools.creative_video import input_manifest
    p['input_manifest']=input_manifest(p)
    p['video_inputs_needs_review']=bool(p.get('video_inputs',{}).get('references') and p.get('video_inputs_product')!=p.get('brief',{}).get('product',''))
    p['reference_needs_review']=bool(not p.get('video_inputs') and p.get('reference') and (p.get('reference_needs_review') or p.get('reference_product')!=p.get('brief',{}).get('product','')))
    if p.get('generation_mode')=='single_native' and p.get('shots'):
        from harness.tools.creative_video import film_prompt
        try: p['production_prompt']=film_prompt(p)
        except RuntimeError: p['production_prompt']=''
    if p.get('image_task',{}).get('state')=='running' and not active:
        p['image_task']=dict(p['image_task'],state='needs_review',error='服务重启后图片结果待核对，不会重复提交。')
    if p['state']=='planning' and not active:
        p['state']='planning_failed'
        p['error']='规划服务曾中断，上下文已保存，请按现有信息重新规划。'
    p['interrupted'] = p['state'] in ('running','rendering') and not active
    p['production_recovery_queue'] = production_recovery_queue(p)
    return p


def lock(pid): return LOCKS.setdefault(pid, asyncio.Lock())


def archive_render(p):
    """Keep previous deliverables reachable before changing their timeline."""
    # A render intent is bound to the current project revision and must not
    # survive an input, model, skill, or timeline change.
    p.pop('scene_render_intent', None)
    p.pop('scene_render_review', None)
    if not p.get('artifact'): return
    versions=p.setdefault('versions',[])
    if any(v['artifact']==p['artifact'] for v in versions): return
    versions.append({'id':'v'+str(p['revision']), 'revision':p['revision'],
                     'reference':p.get('reference'), 'input_manifest':p.get('film',{}).get('inputs'),
                     'artifact':p['artifact'], 'shots':json.loads(json.dumps(p['shots'])),
                     'qa':dict(p.get('qa',{})),
                     'reviews':[dict(r) for r in p.get('reviews',[]) if r['artifact']==p['artifact']], 'created_at':time.time()})
