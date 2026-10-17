#!/usr/bin/env python3
"""Cache bounded public source videos for the authenticated review dashboard."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from urllib.parse import urljoin,urlsplit
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.library.browse_groups import is_explicit_non_ad
from harness.models.reference_download import validate_url, download_mp4
from harness.tools.reference_media_cache import PartialCache, balanced_media_ids, media_source_family
FFMPEG='/opt/visualstation/creative-runtime/bin/ffmpeg'
FFPROBE='/opt/visualstation/creative-runtime/bin/ffprobe'
MAX_FILE=320*1024*1024
MAX_LIBRARY=50*1024*1024*1024
MIN_FREE=1024*1024*1024+3*MAX_FILE
# Keep transport chunks uncoalesced so the deadline runs after each read,
# including a slow source that has not delivered a full application block.
DOWNLOAD_TIMEOUT=600


def file_limit_mib(value):
    try:size=int(value)
    except (ValueError,TypeError):raise argparse.ArgumentTypeError('单文件上限必须为1–1024 MiB的整数') from None
    if not 1<=size<=1024:raise argparse.ArgumentTypeError('单文件上限必须为1–1024 MiB的整数')
    return size


def download_timeout_seconds(value):
    try:seconds=int(value)
    except (ValueError,TypeError):raise argparse.ArgumentTypeError('下载时限必须为60–1800秒的整数') from None
    if not 60<=seconds<=1800:raise argparse.ArgumentTypeError('下载时限必须为60–1800秒的整数')
    return seconds


def library_budget():
    configured=os.getenv('AD_LIBRARY_MAX_GIB','')
    if not configured:return MAX_LIBRARY
    if not re.fullmatch(r'[1-9][0-9]{0,2}',configured) or int(configured)>200:
        raise ValueError('invalid_library_budget')
    return int(configured)*1024*1024*1024


def direct_media(client,url,directory,*,resume=False):
    return download_mp4(client,url,directory,max_bytes=MAX_FILE,
                        timeout=DOWNLOAD_TIMEOUT,resume=resume,clock=time.monotonic)


def playlist(client,url,depth=0):
    validate_url(url)
    if depth>4:raise ValueError('playlist_depth')
    if not urlsplit(url).path.endswith('.m3u8'):return url
    r=client.get(url);r.raise_for_status()
    if len(r.content)>2*1024*1024 or not r.text.startswith('#EXTM3U'):raise ValueError('invalid_playlist')
    if '#EXT-X-KEY:' in r.text:raise ValueError('encrypted_media_not_cached')
    children=[urljoin(url,l.strip()) for l in r.text.splitlines() if l.strip() and not l.startswith('#')]
    for child in children:validate_url(child)
    if '#EXT-X-STREAM-INF:' in r.text:
        if not children:raise ValueError('empty_playlist')
        variants=[]
        info=None
        for line in r.text.splitlines():
            if line.startswith('#EXT-X-STREAM-INF:'):
                resolution=re.search(r'RESOLUTION=(\d+)x(\d+)',line)
                bandwidth=re.search(r'(?:[:,])BANDWIDTH=(\d+)',line)
                info=(min(int(resolution[1]),int(resolution[2])),int(bandwidth[1]) if bandwidth else 0) if resolution else None
            elif line and not line.startswith('#') and info:
                variants.append((*info,urljoin(url,line.strip())));info=None
        # Bound the short edge so portrait references receive the same review quality.
        choices=sorted((v for v in variants if v[0]<=900),reverse=True)
        if not choices:
            choices=sorted(variants,reverse=True)
        for _,bandwidth,selected in choices:
            if bandwidth:
                probe=client.get(selected).raise_for_status().text
                if len(probe)>2*1024*1024 or not probe.startswith('#EXTM3U'):raise ValueError('invalid_playlist')
                durations=re.findall(r'#EXTINF:([\d.]+)',probe)
                seconds=sum(float(v) for v in durations)
                # Peak bandwidth is only a preflight estimate; the actual byte gate stays authoritative.
                if durations and bandwidth*seconds/8*1.03>MAX_FILE:continue
            return playlist(client,selected,depth+1)
        if choices:raise ValueError('media_limit')
        return playlist(client,children[0],depth+1)
    # Reject URI attributes pointing outside the same approved hosts, including init fragments.
    for uri in re.findall(r'URI="([^"]+)"',r.text):validate_url(urljoin(url,uri))
    return url


def local_playlist(client,url,directory):
    """Download validated public HLS fragments before invoking local-only FFmpeg."""
    text=client.get(url).raise_for_status().text
    if len(text)>2*1024*1024 or not text.startswith('#EXTM3U'):raise ValueError('invalid_playlist')
    if '#EXT-X-KEY:' in text:raise ValueError('encrypted_media_not_cached')
    if '#EXT-X-ENDLIST' not in text:raise ValueError('live_playlist_not_cached')
    total=0;cache={};deadline=time.monotonic()+DOWNLOAD_TIMEOUT
    def fetch(value):
        nonlocal total
        if time.monotonic()>deadline:raise ValueError('download_timeout')
        target=validate_url(urljoin(url,value))
        if target in cache:return cache[target]
        name=f'fragment-{len(cache):05d}.bin';destination=directory/name
        with client.stream('GET',target) as response:
            response.raise_for_status()
            with destination.open('xb') as output:
                for block in response.iter_bytes():
                    total+=len(block)
                    if total>MAX_FILE:raise ValueError('media_limit')
                    if time.monotonic()>deadline:raise ValueError('download_timeout')
                    output.write(block)
        cache[target]=name;return name
    lines=[]
    for line in text.splitlines():
        if line and not line.startswith('#'):line=fetch(line.strip())
        elif 'URI="' in line:line=re.sub(r'URI="([^"]+)"',lambda m:'URI="'+fetch(m[1])+'"',line)
        lines.append(line)
    local=directory/'source.m3u8';local.write_text('\n'.join(lines)+'\n')
    return local


def _item_identity(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{24}',value):
        raise ValueError('invalid_reference_identity')
    return value


def select_candidates(c, limit, retry_limited=False, *, only_item=None):
    """Balance source coverage, loading full payloads only for the small batch."""
    cooldown=time.time()-6*3600
    if only_item is not None:_item_identity(only_item)
    resume_ids=PartialCache(store.ROOT).ready_ids(MAX_FILE)
    resume_clause=("i.id IN ("+",".join("?" for _ in resume_ids)+")") if resume_ids else "0"
    # The partial index already tests the JSON predicate. Read lightweight
    # identities first; full payloads are expensive on the shared filesystem.
    item_filter=' AND i.id=?' if only_item is not None else ''
    item_index=' INDEXED BY item_cache_candidate' if only_item is None else ''
    candidates = c.execute('''
        SELECT i.id,i.created,
          CASE WHEN m.state='interrupted' THEN 0
            WHEN (? AND m.state='failed' AND m.error_code='media_limit') THEN 1
            WHEN '''+resume_clause+''' THEN 1
            ELSE 2 END AS priority,
          COALESCE(m.attempts,0) AS attempts
        FROM items i'''+item_index+'''
        LEFT JOIN assets a ON a.item=i.id
        LEFT JOIN media_jobs m ON m.item=i.id
        WHERE a.item IS NULL AND '''+store.CACHEABLE_ITEM_WHERE+'''
          AND COALESCE(m.error_code,'')!='source_locator_missing'
          AND (m.item IS NULL OR m.state!='failed' OR m.updated<?
            OR (? AND m.error_code='media_limit')
            OR (m.error_code='unsupported_media_locator' AND m.updated<?))'''+item_filter+'''
        ORDER BY priority,attempts,i.created,i.id''',
        (int(retry_limited),*resume_ids,cooldown,int(retry_limited),cooldown,
         *((only_item,) if only_item is not None else ()))).fetchall()
    if not candidates:
        return []
    if only_item is not None:
        # Explicit selection never falls through to unrelated references. All
        # eligibility/cooldown/registered-asset gates above still apply.
        return c.execute('SELECT id,data FROM items WHERE id=?',(only_item,)).fetchall()
    # This covering index avoids reading every large items.data payload just
    # to establish a source group. Each statement finishes before the next.
    source_types = c.execute('SELECT id,ad_type FROM items INDEXED BY item_type_recent').fetchall()
    source_by_item = {row['id']: media_source_family(row['ad_type']) for row in source_types}
    deferred = {row['id'] for row in source_types if is_explicit_non_ad(row['ad_type'])}
    # Preserve the reference records and explicit --item access. Automatic
    # advertising batches should not spend slots on known music/personal work.
    candidates = [row for row in candidates if row['id'] not in deferred]
    if not candidates:
        return []
    activity = c.execute('SELECT item,updated FROM media_jobs WHERE attempts>0').fetchall()
    chosen = balanced_media_ids(candidates, source_by_item, activity, limit)
    placeholders = ','.join('?' for _ in chosen)
    rows = {row['id']: row for row in c.execute(
        'SELECT id,data FROM items WHERE id IN ('+placeholders+')', chosen).fetchall()}
    return [rows[identity] for identity in chosen]


def recover_candidates(limit, retry_limited=False, *, only_item=None):
    """Called with the worker lock held: interrupted work precedes new downloads."""
    if only_item is not None:_item_identity(only_item)
    with store.connection() as c:
        c.execute("UPDATE media_jobs SET state='interrupted',error_code='worker_restarted',updated=? WHERE state='downloading'",(time.time(),))
        c.execute("UPDATE collection_runs SET state='interrupted',finished=?,error_code='worker_restarted' WHERE source='本地视频缓存' AND state='running'",(time.time(),))
    # Commit recovery before the read phase; a slow candidate scan must not
    # retain a write reservation against collectors or human annotations.
    with store.connection() as c:
        rows=(select_candidates(c,limit,retry_limited,only_item=only_item)
              if only_item is not None else select_candidates(c,limit,retry_limited))
        used=store.registered_media_bytes(c)
    return rows,used


def record_asset(run_id,asset):
    """Commit once, with bounded retries for a busy local database only.

    A retry opens a new transaction after rollback. It never repeats a
    download, probe or model call, and an existing asset is not overwritten.
    """
    for attempt in range(3):
        try:
            with store.connection() as c:
                inserted=c.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?,?,?,?)',asset).rowcount
                c.execute("UPDATE media_jobs SET state='completed',error_code='',updated=? WHERE item=?",(time.time(),asset[0]))
                if inserted:c.execute('UPDATE collection_runs SET inserted=inserted+1 WHERE id=?',(run_id,))
            return bool(inserted)
        except sqlite3.OperationalError as error:
            code=getattr(error,'sqlite_errorcode',0)
            if not isinstance(code,int) or (code & 0xff) not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED) or attempt==2:
                raise
            time.sleep(attempt+1)


def _cache_one(row, run_id, partials, partial_budget, partial_lock, protected):
    """One download/probe/commit, with its own database connections and files."""
    fragments=None;downloaded=False
    identity=row['id'];folder=store.ROOT/'assets'/identity
    temp=folder/('review-'+secrets.token_hex(5)+'.part.mp4')
    result={'cached':0,'failed':0,'bytes':0}
    try:
        folder.mkdir(parents=True,exist_ok=True)
        with store.connection() as c:c.execute("INSERT INTO media_jobs(item,state,attempts,updated) VALUES(?,'downloading',1,?) ON CONFLICT(item) DO UPDATE SET state='downloading',attempts=media_jobs.attempts+1,updated=excluded.updated",(identity,time.time()))
        source_path=folder/'source.json'
        if not source_path.is_file():
            payload=json.loads(row['data'])
            public_url=payload.get('creative_structure',{}).get('public_video_url','')
            if public_url:
                source_path.write_text(json.dumps({'media_url':public_url},ensure_ascii=False),encoding='utf-8')
        if not source_path.is_file():
            raise ValueError('source_locator_missing')
        source=json.loads(source_path.read_text())
        fragments=tempfile.TemporaryDirectory(prefix='hls-',dir=folder)
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            url=playlist(client,source['media_url'])
            if urlsplit(url).path.endswith('.m3u8'):
                local=local_playlist(client,url,Path(fragments.name))
            else:
                with partial_lock:
                    resume_dir=partials.reserve(identity,MAX_FILE,partial_budget(),protected=protected)
                local=direct_media(client,url,resume_dir or Path(fragments.name),resume=resume_dir is not None)
            downloaded=True
        options=['-allowed_extensions','ALL'] if local.suffix=='.m3u8' else []
        command=[FFMPEG,'-nostdin','-v','error','-protocol_whitelist','file,crypto,data',*options,'-i',str(local),'-map','0:v:0','-map','0:a:0?','-c','copy','-movflags','+faststart',str(temp)]
        with open(os.devnull,'wb') as null:
            process=subprocess.Popen(command,stdout=null,stderr=null)
            try:
                end=time.monotonic()+300
                while process.poll() is None:
                    if time.monotonic()>end or (temp.exists() and temp.stat().st_size>MAX_FILE):raise ValueError('media_limit')
                    time.sleep(1)
                if process.returncode:raise ValueError('media_download_failed')
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=15)
        meta=json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(temp)],timeout=30))
        video=next(s for s in meta['streams'] if s['codec_type']=='video');duration=float(meta['format']['duration'])
        if duration<=0 or temp.stat().st_size>MAX_FILE:raise ValueError('invalid_media')
        sha=hashlib.sha256(temp.read_bytes()).hexdigest();destination=folder/(sha+'.mp4')
        if destination.exists():temp.unlink()
        else:temp.replace(destination)
        poster=folder/'poster.jpg'
        if not poster.exists():subprocess.run([FFMPEG,'-nostdin','-v','error','-ss',str(min(3,duration/2)),'-i',str(destination),'-vf','scale=640:-2','-frames:v','1',str(poster)],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        size=destination.stat().st_size
        if record_asset(run_id,(identity,str(destination.relative_to(store.ROOT)),sha,size,duration,int(any(s['codec_type']=='audio' for s in meta['streams'])),video['width'],video['height'],time.time())):
            result.update(cached=1,bytes=size)
    except Exception as e:
        result['failed']=1
        code=str(e) if isinstance(e,ValueError) and str(e) in ('media_limit','download_timeout','incomplete_media','invalid_media_range','invalid_partial_identity','invalid_media','invalid_playlist','unsupported_media_format','media_download_failed','unsupported_media_locator','encrypted_media_not_cached','live_playlist_not_cached','source_locator_missing') else type(e).__name__
        with store.connection() as c:c.execute("UPDATE media_jobs SET state='failed',error_code=?,updated=? WHERE item=?",(code,time.time(),identity))
    finally:
        # Cleanup cannot undo a successful asset commit or hide its receipt.
        try:temp.unlink(missing_ok=True)
        except OSError:pass
        if fragments:
            try:fragments.cleanup()
            except OSError:pass
        if downloaded:
            with partial_lock:
                try:partials.discard(identity)
                except OSError:pass
    return result


def run(limit, retry_limited=False, *, only_item=None, parallelism=1):
    if type(parallelism) is not int or not 1 <= parallelism <= 2:
        raise ValueError('invalid_media_parallelism')
    if only_item is not None:_item_identity(only_item)
    budget=library_budget()
    store.ROOT.mkdir(parents=True,exist_ok=True)
    with (store.ROOT/'.media.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'already_running'}
        rows,used=(recover_candidates(limit,retry_limited,only_item=only_item)
                   if only_item is not None else recover_candidates(limit,retry_limited))
        if only_item is not None and not rows:
            return {'state':'no_eligible_candidate','cached':0,'failed':0}
        partials=PartialCache(store.ROOT)
        slots=min(parallelism,max(1,len(rows)))
        min_free=MIN_FREE+(slots-1)*2*MAX_FILE
        if used+MAX_FILE>budget:return {'state':'storage_limit'}
        if shutil.disk_usage(store.ROOT).free<min_free:return {'state':'disk_space_limit'}
        run_id=secrets.token_hex(12);done=0;errors=0;stop_reason=''
        with store.connection() as c:c.execute('INSERT INTO collection_runs(id,source,started,state,discovered) VALUES(?,?,?,?,?)',(run_id,'本地视频缓存',time.time(),'running',len(rows)))
        partial_lock=threading.RLock();protected=set()
        partial_budget=lambda:budget-used-2*MAX_FILE*slots
        if slots==1:
            for row in rows:
                if used+MAX_FILE>budget:
                    stop_reason='storage_limit';break
                if shutil.disk_usage(store.ROOT).free<min_free:
                    stop_reason='disk_space_limit';break
                result=_cache_one(row,run_id,partials,partial_budget,partial_lock,protected)
                used+=result['bytes'];done+=result['cached'];errors+=result['failed']
        else:
            pending=list(rows);active={}
            with ThreadPoolExecutor(max_workers=slots) as pool:
                while pending or active:
                    while pending and len(active)<slots:
                        reason=('storage_limit' if used+MAX_FILE*(len(active)+1)>budget
                                else 'disk_space_limit' if shutil.disk_usage(store.ROOT).free<min_free else '')
                        if reason:
                            # A finishing worker may release temporary space.
                            # Drain active work before deciding the final stop.
                            if not active:stop_reason=reason
                            break
                        row=pending.pop(0)
                        with partial_lock:protected.add(row['id'])
                        future=pool.submit(_cache_one,row,run_id,partials,partial_budget,partial_lock,protected)
                        active[future]=row['id']
                    if not active:break
                    finished,_=wait(active,return_when=FIRST_COMPLETED)
                    for future in finished:
                        identity=active.pop(future)
                        try:result=future.result()
                        except Exception:
                            # A database/filesystem failure must not cancel the
                            # other worker or expose provider exception text.
                            result={'bytes':0,'cached':0,'failed':1}
                        with partial_lock:
                            used+=result['bytes'];protected.discard(identity)
                        done+=result['cached'];errors+=result['failed']
        with store.connection() as c:c.execute('UPDATE collection_runs SET finished=?,state=?,inserted=?,error_code=? WHERE id=?',(time.time(),'partial' if errors or stop_reason else 'completed',done,'media_unavailable_or_limit' if errors else stop_reason,run_id))
        return {'state':'partial' if errors else stop_reason or 'completed','cached':done,'failed':errors}

def main(argv=None):
    global MAX_FILE, MIN_FREE, DOWNLOAD_TIMEOUT
    configured=os.getenv('AD_LIBRARY_MEDIA_PARALLELISM','1')
    default_parallelism=int(configured) if configured in ('1','2') else 1
    p=argparse.ArgumentParser()
    selection=p.add_mutually_exclusive_group()
    selection.add_argument('--limit',type=int,default=4)
    selection.add_argument('--item',type=_item_identity,help='Cache only this existing reference ID; never select another item')
    p.add_argument('--retry-limited',action='store_true',help='Explicitly reconsider media_limit failures after changing cache policy')
    p.add_argument('--max-file-mib',type=file_limit_mib,default=320,help='Explicit per-file limit, 1–1024 MiB; default 320')
    p.add_argument('--download-timeout-seconds',type=download_timeout_seconds,default=600,help='Per-download deadline, 60–1800 seconds; default 600')
    p.add_argument('--parallelism',type=int,choices=(1,2),default=default_parallelism,help='Bounded concurrent downloads inside the same worker lock; default from AD_LIBRARY_MEDIA_PARALLELISM or 1')
    a=p.parse_args(argv)
    MAX_FILE=a.max_file_mib*1024*1024
    MIN_FREE=1024*1024*1024+3*MAX_FILE
    DOWNLOAD_TIMEOUT=a.download_timeout_seconds
    options={}
    if a.item is not None:options['only_item']=a.item
    if a.parallelism!=1:options['parallelism']=a.parallelism
    result=run(1 if a.item is not None else max(1,min(a.limit,12)),a.retry_limited,**options)
    print(json.dumps(result))
    # Existing batch services still run their reuse/review-queue post-hooks
    # after a partial download batch. A targeted maintenance job can fail on
    # its single requested item without changing that established behavior.
    return 1 if a.item is not None and result.get('state') in ('partial','failed') else 0


if __name__=='__main__':
    sys.exit(main())
