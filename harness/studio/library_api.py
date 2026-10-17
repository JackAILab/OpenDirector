"""Authenticated human preferences over an independently collected reference library."""
from fastapi import Header, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StrictInt
from typing import Literal
from functools import lru_cache
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import time
from harness.library import store as library
from harness.library.backup_progress import read_progress
from harness.studio import store


_QUEUE_CACHE = None
_STATUS_CACHE = {}


def _database_busy(error, *, saving=False):
    # Extended result codes retain their primary code in the low byte.
    if (getattr(error,'sqlite_errorcode',0) & 255) not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):
        raise error
    message=('资料库正忙，本次标注未保存。填写内容仍在当前页面，请稍后再保存。'
             if saving else '资料库正在更新，请稍后重新加载。')
    raise HTTPException(503,message,headers={'Retry-After':'3','Cache-Control':'private, no-store'}) from None


@lru_cache(maxsize=128)
def _backup_metadata(root, identity):
    """Cache safe fields from finalized manifests, never mutable job state.

    Full snapshots have large manifests on shared storage. Re-reading their
    overflow pages for every status request can dominate the whole response.
    Preparation summaries bypass this cache; after preparation, manifest
    contents stay fixed and state remains a fresh indexed query.
    """
    with closing(sqlite3.connect(f'file:{Path(root)/"library.sqlite3"}?mode=ro', uri=True, timeout=2)) as db:
        row=db.execute('''SELECT
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.scope') END,
            CASE WHEN json_valid(manifest) THEN
                CASE WHEN json_type(manifest,'$.items')='integer'
                THEN json_extract(manifest,'$.items') END END
            FROM backups WHERE id=?''', (identity,)).fetchone()
    return {'scope':row[0] if row else None,'items':row[1] if row else None}


def _backup_projection(row):
    # Preparation summaries gain their count after the consistent database
    # copy. Cache only the final manifest, so an early unknown count cannot
    # survive the transition to upload or verification.
    read = _backup_metadata.__wrapped__ if row['state']=='preparing' else _backup_metadata
    return {**dict(row),**read(str(library.ROOT),row['id']),
            'progress':read_progress(library.ROOT,row['id'],row['state'])}


def _is_production_library():
    configured = Path(os.getenv(
        'AD_LIBRARY_ROOT',
        '/assets/library'))
    try:
        return library.ROOT.resolve() == configured.resolve()
    except OSError:
        return False


def _queue_observed_at(value):
    """Use the producer's time, never the HTTP read time of an older snapshot."""
    if not isinstance(value,str) or len(value)>64:
        return None
    try:
        observed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if observed.tzinfo is None:return None
        stamp=observed.timestamp()
        return stamp if 0<stamp<=time.time()+60 else None
    except (ValueError,OverflowError,OSError):
        return None


def _review_queue_summary():
    """Return bounded queue metrics without making the request scan the library.

    The learning refresh job materializes a privacy-safe queue artifact. The
    dashboard only needs its aggregate counts, so read that snapshot first.
    A small SQL fallback keeps local tests and a first boot useful when no
    artifact exists; it deliberately returns ``unavailable`` on storage
    contention instead of blocking a creative request.
    """
    global _QUEUE_CACHE
    root = Path(os.getenv('AD_LIBRARY_LEARNING_ARTIFACT_ROOT', '/var/lib/visualstation-local/creative/learning'))
    # An artifact belongs to the configured production library only. Tests
    # and alternate roots must derive their own empty/local queue instead of
    # accidentally displaying production counts.
    use_artifact = _is_production_library()
    try:
        candidates = list(root.glob('ad-analysis-review-queue-*.json')) if use_artifact else []
        if candidates:
            path = max(candidates, key=lambda p: p.stat().st_mtime_ns)
            mtime = path.stat().st_mtime_ns
            if _QUEUE_CACHE and _QUEUE_CACHE[:2] == (str(path), mtime):
                return _QUEUE_CACHE[2]
            with path.open(encoding='utf-8') as f:
                data = json.load(f)
            summary = {key: data.get(key) for key in (
                'state', 'total_pending', 'analysis_pending',
                'semantic_review_pending')}
            summary['training_eligible'] = False
            summary['observed_at'] = _queue_observed_at(data.get('generated_at'))
            if summary.get('state') in ('ready', 'unavailable'):
                _QUEUE_CACHE = (str(path), mtime, summary)
                return summary
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass

    # Fallback is intentionally bounded and read-only. Avoid importing the
    # large learning module on the request path: its provider registry makes
    # first import slow on the shared filesystem.
    try:
        library_path = library.ROOT / 'library.sqlite3'
        with closing(sqlite3.connect(f'file:{library_path}?mode=ro', uri=True, timeout=1)) as db:
            assets = db.execute('SELECT item,sha256,audio FROM assets').fetchall()
        current_media = {item:digest for item,digest,_ in assets}
        analyses_path = library.ROOT / 'learning' / 'analyses.sqlite3'
        latest = {}
        if analyses_path.is_file():
            with closing(sqlite3.connect(f'file:{analyses_path}?mode=ro', uri=True, timeout=1)) as db:
                for item, digest, version, payload in db.execute(
                    'SELECT item,media_sha256,version,data FROM analyses'):
                    if current_media.get(item)!=digest:
                        continue
                    current = latest.get(item)
                    if current is None or version > current[0]:
                        latest[item] = (version, digest, payload)
        analysis_pending = 0
        semantic_pending = 0
        for item, digest, audio in assets:
            row = latest.get(item)
            if row is None or row[1] != digest:
                analysis_pending += 1
                continue
            try:
                data = json.loads(row[2])
            except (TypeError, ValueError):
                analysis_pending += 1
                continue
            missing_audio = data.get('audio_semantics_reviewed') is not True
            missing_motion = data.get('full_motion_reviewed') is not True
            if missing_audio or missing_motion:
                semantic_pending += 1
        return {'state': 'ready', 'total_pending': analysis_pending + semantic_pending,
                'analysis_pending': analysis_pending,
                'semantic_review_pending': semantic_pending,
                'observed_at': time.time(),
                'training_eligible': False}
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return {'state': 'unavailable', 'total_pending': None,
                'analysis_pending': None, 'semantic_review_pending': None,
                'observed_at': None,
                'training_eligible': False}

class Review(BaseModel):
    version:int=Field(ge=0)
    state:Literal['pending','selected','revisit','rejected']
    scores:dict[str,StrictInt]=Field(default_factory=dict)
    tags:list[str]=Field(default_factory=list,max_length=12)
    note:str=Field(default='',max_length=3000)


class UseReference(BaseModel):
    product:str=Field(min_length=2,max_length=1000)

def install(gateway):
    app=gateway.app
    def viewer(request,authorization):
        gateway.require_site_access(request)
        return gateway.require_session(authorization)['id'] if authorization else 0

    @app.get('/creative/library',include_in_schema=False)
    def page():return FileResponse(store.ROOT/'tools/agent_studio/library.html',headers={'Cache-Control':'no-store'})

    @app.get('/creative/api/library')
    def items(request:Request,authorization:str|None=Header(None),q:str='',industry:str='',ad_type:str='',state:str='',limit:int=Query(60,ge=1,le=200),offset:int=Query(0,ge=0),local_only:bool=False,duration_band:Literal['','short','standard','extended','long','unknown']='',unique_media:bool=False,ad_group:str=''):
        uid=viewer(request,authorization)
        try:return library.list_items(uid,q,industry,ad_type,state,limit,offset,local_only,duration_band,unique_media,ad_group)
        except ValueError as e:raise HTTPException(422,str(e))
        except sqlite3.OperationalError as e:_database_busy(e)

    @app.get('/creative/api/library/status')
    def status(request:Request,authorization:str|None=Header(None)):
        uid=viewer(request,authorization)
        # Queue counts are intentionally aggregated only; the dashboard must
        # show measured review debt without exposing analysis text or paths.
        review_queue=_review_queue_summary()
        global _STATUS_CACHE
        production = _is_production_library()
        cached = _STATUS_CACHE.get(uid)
        if production and cached and time.monotonic() - cached[0] < 30:
            metrics = dict(cached[1])
            metrics['can_review'] = bool(uid)
            metrics['review_queue'] = review_queue
            return metrics
        with library.connection() as c:
            # COUNT over a non-null primary key can use the compact covering
            # index on the shared filesystem; COUNT(*) needlessly scans the
            # large JSON rows.
            total=c.execute('SELECT COUNT(id) FROM items').fetchone()[0]
            playable=c.execute('SELECT COUNT(item) FROM assets').fetchone()[0]
            distinct_playable=c.execute('SELECT COUNT(DISTINCT '+library.media_group_sql('a.item')+') FROM assets a').fetchone()[0]
            reviewed=c.execute('SELECT COUNT(DISTINCT item) FROM reviews WHERE reviewer=?',(uid,)).fetchone()[0]
            # Read the normalized field instead of relying on json.dumps spacing.
            # Older rows may omit the field, so json_extract naturally treats them as
            # non-source-link items while preserving the overview metric.
            # json_extract over every large evidence payload is expensive on
            # the shared filesystem. The production dashboard gets this
            # optional metric from the next materialized refresh; keeping the
            # request bounded is more important than blocking the studio.
            source_link=None if _is_production_library() else c.execute(
                "SELECT COUNT(*) FROM items WHERE json_extract(data,'$.media_status')='source_link'").fetchone()[0]
            human_selected=c.execute('''SELECT COUNT(*) FROM reviews r
                WHERE r.reviewer=? AND r.state='selected' AND r.seq=(
                  SELECT latest.seq FROM reviews latest
                  WHERE latest.item=r.item AND latest.reviewer=r.reviewer
                  ORDER BY latest.version DESC LIMIT 1)''',(uid,)).fetchone()[0]
            runs=[dict(r) for r in c.execute('SELECT id,source,started,finished,state,discovered,inserted,error_code FROM collection_runs ORDER BY started DESC LIMIT 8')]
            # A slow media batch can predate many newer source receipts. Read
            # it separately, with failures from the same SQL read snapshot.
            # Only one media worker owns the queue. Once a run is terminal,
            # later retries can change those rows, so historical failure counts
            # stay unknown instead of being reconstructed from current jobs.
            media=c.execute('''SELECT id,source,started,finished,state,discovered,inserted,error_code,
                CASE WHEN state='running' THEN
                    (SELECT COUNT(*) FROM media_jobs WHERE state='failed' AND updated>=collection_runs.started)
                END AS failed
                FROM collection_runs WHERE source='本地视频缓存'
                ORDER BY started DESC LIMIT 1''').fetchone()
            media_cache=dict(media) if media else None
            # Project only the backup scope. The manifest contains private
            # file paths and review data and must never reach the dashboard.
            backup_columns = 'SELECT id,created,state,remote_revision FROM backups '
            # Indexed summaries avoid scanning historical manifest payloads.
            # Resuming an older full snapshot does not change its creation
            # date; query it separately so newer metadata backups cannot hide it.
            backups=[_backup_projection(r) for r in c.execute(
                backup_columns + 'ORDER BY created DESC LIMIT 3')]
            active=c.execute(backup_columns +
                "WHERE state IN ('preparing','uploading','verifying') ORDER BY created DESC LIMIT 1").fetchone()
            active_backup=_backup_projection(active) if active else None
        metrics={'total':total,'playable':playable,'distinct_playable':distinct_playable,'source_link':source_link,'reviewed':reviewed,
                 'selected':human_selected,'runs':runs,'media_cache':media_cache,'backups':backups,'active_backup':active_backup,
                 'review_queue':{'state':review_queue.get('state'),
                                 'total_pending':review_queue.get('total_pending'),
                                 'analysis_pending':review_queue.get('analysis_pending'),
                                 'semantic_review_pending':review_queue.get('semantic_review_pending'),
                                 'observed_at':review_queue.get('observed_at'),
                                 'training_eligible':False},
                 'can_review':bool(uid)}
        if production:
            _STATUS_CACHE[uid] = (time.monotonic(), dict(metrics))
        return metrics

    @app.get('/creative/api/library/review-starters')
    def review_starters(request:Request,authorization:str|None=Header(None)):
        viewer(request,authorization)
        from harness.library.review_starters import review_starters as starters
        return JSONResponse(starters(),headers={'Cache-Control':'private, no-store'})

    @app.get('/creative/api/library/{identity}')
    def item(identity:str,request:Request,authorization:str|None=Header(None)):
        try:return library.get_item(identity,viewer(request,authorization))
        except KeyError:raise HTTPException(404,'参考案例不存在')

    @app.get('/creative/api/library/{identity}/same-video')
    def same_video(identity:str,request:Request,authorization:str|None=Header(None)):
        uid=viewer(request,authorization)
        try:return library.same_video_sources(identity,uid)
        except KeyError:raise HTTPException(404,'参考案例不存在')

    @app.post('/creative/api/library/{identity}/review')
    def review(identity:str,body:Review,request:Request,authorization:str|None=Header(None)):
        uid=viewer(request,authorization)
        if not uid:raise HTTPException(401,'请登录账户后保存个人偏好')
        try:
            result = library.review_item(identity,uid,body.version,body.state,body.scores,body.tags,body.note)
            _STATUS_CACHE.pop(uid, None)
            return result
        except KeyError:raise HTTPException(404,'参考案例不存在')
        except ValueError as e:raise HTTPException(422,str(e))
        except RuntimeError as e:raise HTTPException(409,str(e))
        except sqlite3.OperationalError as e:_database_busy(e,saving=True)

    @app.get('/creative/api/library/{identity}/analysis')
    def strategy_analysis(identity:str,request:Request,authorization:str|None=Header(None)):
        viewer(request,authorization)
        from harness.library.learning import get_analysis
        try:result=get_analysis(identity,require_item=True)
        except KeyError:raise HTTPException(404,'参考案例不存在')
        except sqlite3.OperationalError as e:_database_busy(e)
        return JSONResponse({'state':'candidate' if result else 'pending','analysis':result,'training_eligible':False},
                            headers={'Cache-Control':'private, no-store'})

    @app.get('/creative/api/library/{identity}/history')
    def history(identity:str,request:Request,authorization:str|None=Header(None)):
        uid=viewer(request,authorization)
        if not uid:raise HTTPException(401,'请先登录账户')
        try:return {'history':library.review_history(identity,uid)}
        except KeyError:raise HTTPException(404,'参考案例不存在')

    @app.get('/creative/api/library/{identity}/{kind}')
    def media(identity:str,kind:str,request:Request):
        gateway.require_site_access(request)
        if kind not in ('media','poster'):raise HTTPException(404)
        with library.connection() as c:asset=c.execute('SELECT * FROM assets WHERE item=?',(identity,)).fetchone()
        if not asset:raise HTTPException(404,'本地视频尚未就绪')
        path=(library.ROOT/asset['path']).resolve()
        if not path.is_relative_to((library.ROOT/'assets').resolve()):raise HTTPException(404)
        if kind=='poster':path=path.parent/'poster.jpg'
        if not path.is_file():raise HTTPException(404,'本地媒体暂不可用')
        return FileResponse(path,media_type='video/mp4' if kind=='media' else 'image/jpeg',headers={'Cache-Control':'private, no-store'})

    @app.post('/creative/api/library/{identity}/use')
    def use(identity:str,body:UseReference,request:Request,authorization:str|None=Header(None)):
        import secrets
        from harness.tools.library_reference import attach
        uid=viewer(request,authorization)
        if not uid:raise HTTPException(401,'请先登录账户')
        try:item=library.get_item(identity,uid)
        except KeyError:raise HTTPException(404,'参考案例不存在')
        p={'id':secrets.token_hex(12),'state':'intake','revision':0,'generation_mode':'single_native',
           'duration':15,'aspect':'16:9','provider':'kling','model':'kling-video-v3_0',
           'approval_mode':'manual',
           'shots':[],'questions':[],'assumptions':[],'decisions':[],'brief':{},'training_eligible':False,
           'library_reference':identity,'messages':[{'role':'user','content':'新商品与目标：'+body.product+'。借鉴所选广告案例及我标注的偏好，先追问缺失商品事实，再规划15秒有声整片；原案例不是新商品事实来源，不复制其品牌、台词或具体承诺。'}]}
        try:count=attach(p,item)
        except ValueError as error:
            if str(error)=='reference_skill_media_changed':
                raise HTTPException(409,'该案例的视频与已发布Skill版本不一致，请先在Skill库核对后重新选择') from None
            raise HTTPException(503,'参考资料导入未完成，请稍后重试；未提交任何付费生成') from None
        except Exception:raise HTTPException(503,'参考资料导入未完成，请稍后重试；未提交任何付费生成')
        store.save(p,uid);store.event(p,'task','library_reference_used')
        return {'project':store.present(p),'reference_frames':count}
