#!/usr/bin/env python3
"""Resumable bounded visual analysis. No video generation and no automatic retries."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import multiprocessing
import pickle
import re
import sqlite3
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def configured_model():
    """Resolve the exact model name before any frame extraction or API call."""
    model=os.environ.get('CREATIVE_MODEL','cb-gpt-5.6-sol').strip()
    if not model: raise RuntimeError('creative_model_unconfigured')
    if not os.environ.get('CREATIVE_MODEL_URL','').strip(): raise RuntimeError('creative_model_url_unconfigured')
    key_file=os.environ.get('CREATIVE_MODEL_KEY_FILE','').strip()
    if not key_file or not Path(key_file).is_file(): raise RuntimeError('creative_model_key_file_unconfigured')
    return model


class LibraryReadTimeout(RuntimeError):
    pass


def validate_selection(ids):
    if (not isinstance(ids, (list, tuple)) or len(ids) > 1000 or
            any(not isinstance(i, str) or not re.fullmatch(r'[a-f0-9]{24}', i) for i in ids) or
            len(set(ids)) != len(ids)):
        raise RuntimeError('invalid_analysis_selection')
    return tuple(ids)


def load_selection(path):
    if path is None:
        return None
    try:
        entries = json.loads(Path(path).read_text())
        if not isinstance(entries, list):
            raise ValueError
        return validate_selection([entry['id'] for entry in entries])
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError('invalid_analysis_selection') from None


def _read_rows_worker(output_path, selected=None):
    try:
        from harness.library import store
        # store.connection() bootstraps schema and changes journal_mode,
        # taking a write lock on the FUSE-backed database. Analysis is
        # read-only and must never contend with collectors.
        db = store.ROOT / 'library.sqlite3'
        c = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=2)
        c.row_factory = sqlite3.Row
        with open(output_path, 'wb') as handle:
            query = 'SELECT i.*,a.path,a.sha256,a.duration FROM items i JOIN assets a ON a.item=i.id'
            if selected is not None:
                # Scheduled batches already have an exact selection. Fetch only
                # those indexed rows instead of scanning all media on FUSE.
                for offset in range(0, len(selected), 200):
                    ids = selected[offset:offset + 200]
                    placeholders = ','.join('?' for _ in ids)
                    found = {r['id']: dict(r) for r in c.execute(
                        query + ' WHERE i.id IN (' + placeholders + ')', ids)}
                    if len(found) != len(ids):
                        raise RuntimeError('analysis_selection_unavailable')
                    rows = [found[i] for i in ids]
                    pickle.dump(('chunk', rows), handle, protocol=pickle.HIGHEST_PROTOCOL)
                    handle.flush()
            else:
                offset = 0
                while True:
                    rows = [dict(r) for r in c.execute(query + ' ORDER BY i.id LIMIT 500 OFFSET ?', (offset,))]
                    if not rows: break
                    pickle.dump(('chunk', rows), handle, protocol=pickle.HIGHEST_PROTOCOL)
                    handle.flush()
                    offset += len(rows)
            pickle.dump(('done', None), handle, protocol=pickle.HIGHEST_PROTOCOL)
        c.close()
        # A Queue deadlocks when the parent joins before draining a payload
        # larger than the multiprocessing pipe buffer.  The library has
        # thousands of rows, so use a local short-lived handoff file instead.
        # Error state is written as a single record below.
    except BaseException as exc:
        with open(output_path, 'wb') as handle:
            code = 'analysis_selection_unavailable' if str(exc) == 'analysis_selection_unavailable' else type(exc).__name__
            pickle.dump(('error', code), handle, protocol=pickle.HIGHEST_PROTOCOL)


def read_library_rows(timeout_seconds=30, selected=None):
    """Read the library in a killable process so a FUSE stall cannot hang Runner."""
    if selected is not None:
        selected = validate_selection(selected)
        if not selected:
            return []  # An empty selection never authorizes a full-library scan.
    fd, output_path = tempfile.mkstemp(prefix='advertise-agent-library-', suffix='.pickle')
    os.close(fd)
    try:
        # Forking after the long-lived service has touched dop-fuse can leave
        # the child with inherited FUSE state that never completes reads.
        # Spawn a clean interpreter for the bounded probe instead.
        process=multiprocessing.get_context('spawn').Process(target=_read_rows_worker,args=(output_path,selected))
        try:
            process.start()
        except (AttributeError, TypeError) as exc:
            # Test doubles and local callables cannot be pickled by spawn;
            # retain the bounded timeout contract with fork as a fallback.
            if 'pickle' not in str(exc).lower() and 'local object' not in str(exc).lower():
                raise
            process=multiprocessing.get_context('fork').Process(target=_read_rows_worker,args=(output_path,selected))
            process.start()
        process.join(max(1,int(timeout_seconds)))
        if process.is_alive():
            process.terminate(); process.join(2)
            raise LibraryReadTimeout('library_read_timeout')
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError('library_read_no_result')
        rows=[]
        with open(output_path, 'rb') as handle:
            while True:
                state,value=pickle.load(handle)
                if state == 'chunk': rows.extend(value)
                elif state == 'done': break
                else: break
    finally:
        try: os.unlink(output_path)
        except FileNotFoundError: pass
    if state=='error': raise RuntimeError(value)
    return rows

async def main(args):
    model=configured_model()
    selected=load_selection(args.selection)
    rows=read_library_rows(args.startup_timeout, selected=selected)
    from harness.library import store, learning
    from harness.models.ad_analysis import analyze
    done=0;failures=0
    for item in rows:
        if learning.get_analysis(item['id']):continue
        folder=store.ROOT/'learning/evidence'/item['id'];folder.mkdir(parents=True,exist_ok=True)
        attempt=folder/'analysis-attempt.json'
        if attempt.exists():
            receipt=json.loads(attempt.read_text())
            resumable = receipt.get('state') == 'failed' and args.retry_failed
            if receipt.get('state') == 'started' and args.resume_stale_started:
                resumable = time.time() - float(receipt.get('started_at', 0) or 0) >= args.resume_stale_started
            if not resumable:continue
            history=folder/'analysis-attempt-history.jsonl'
            with history.open('a') as handle:handle.write(json.dumps(receipt)+'\n')
        if done+failures>=args.limit:break
        item['metadata']=json.loads(item.pop('data'))
        frames=[{'time':round(item['duration']*f,3),'path':folder/f'{i:02}.jpg'} for i,f in enumerate([.02,.10,.18,.26,.34,.42,.5,.58,.66,.74,.84,.96])]
        try:
            source=(store.ROOT/item['path']).resolve()
            if not source.is_relative_to((store.ROOT/'assets').resolve()):raise ValueError('invalid_source')
            # Each image remains tied to the source digest; no credentials/provider responses saved.
            evidence_file=folder/'evidence.json'
            if evidence_file.exists() and json.loads(evidence_file.read_text())['media_sha256']!=item['sha256']:raise ValueError('source_changed')
            for frame in frames:
                if not frame['path'].exists():
                    subprocess.run(['/opt/visualstation/creative-runtime/bin/ffmpeg','-nostdin','-v','error','-ss',str(frame['time']),'-i',str(source),'-vf','scale=640:-2','-frames:v','1',str(frame['path'])],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            evidence_file.write_text(json.dumps({'item':item['id'],'media_sha256':item['sha256'],'frames':[{'time':f['time'],'path':f['path'].name} for f in frames]}))
            attempt.write_text(json.dumps({'state':'started','model':model,'started_at':time.time(),'automatic_retry':False}))
            # Bound one model call so a stalled upstream request cannot hold
            # the whole batch indefinitely. A timeout is a recorded failure;
            # it is never retried here with changed parameters or another model.
            result=await asyncio.wait_for(analyze(item,frames), timeout=240)
            if isinstance(result,dict):
                candidate={k:result.get(k) for k in ('media_role','confidence','principle','mechanism','beats','grill_questions','transfer_rules','avoid')}
                (folder/'candidate.json').write_text(json.dumps(candidate,ensure_ascii=False))
            clean=learning.validate(result,item['duration'],[f['time'] for f in frames])
            version=learning.save_analysis(item['id'],item['sha256'],item['revision'],model,clean,[f['time'] for f in frames])
            attempt.write_text(json.dumps({'state':'completed','version':version,'automatic_retry':False}))
            done+=1;print(json.dumps({'item':item['id'],'state':'completed','version':version}),flush=True)
        except Exception as e:
            failures+=1;attempt.write_text(json.dumps({'state':'failed','error_code':type(e).__name__,'automatic_retry':False}))
            print(json.dumps({'item':item['id'],'state':'failed','error_code':type(e).__name__}),flush=True)
    print(json.dumps({'completed':done,'failed':failures,'video_generation':False}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=12);parser.add_argument('--selection');parser.add_argument('--retry-failed',action='store_true');parser.add_argument('--resume-stale-started',type=int,default=0,help='resume an interrupted analysis with the same model after this many seconds');parser.add_argument('--startup-timeout',type=int,default=30)
    args=parser.parse_args()
    if not 1<=args.limit<=1000:parser.error('limit must be 1–1000')
    if not 1<=args.startup_timeout<=300:parser.error('startup-timeout must be 1–300')
    if args.resume_stale_started < 0:parser.error('resume-stale-started must be non-negative')
    try:
        asyncio.run(main(args))
    except (LibraryReadTimeout, RuntimeError) as exc:
        # Startup failures happen before any paid/model call. Keep the
        # scheduler output machine-readable and explicitly non-retryable.
        print(json.dumps({'state':'failed','error_code':str(exc) or type(exc).__name__,
                          'phase':'startup','automatic_retry':False,
                          'video_generation':False},ensure_ascii=False), flush=True)
        raise SystemExit(2)
