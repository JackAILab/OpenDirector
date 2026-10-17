#!/usr/bin/env python3
"""Bounded incremental collection. Never generates or assigns human approval."""
import argparse
import fcntl
import json
import os
from datetime import datetime, timezone
import secrets
import sys
import time
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import dandad


def source_years(current_year=None):
    year=current_year or datetime.now(timezone.utc).year
    configured=os.getenv('AD_LIBRARY_YEARS','').strip()
    if configured:
        try:years=[int(v.strip()) for v in configured.split(',')]
        except ValueError:raise ValueError('invalid_source_years') from None
    else:
        years=[year-1,year-2,year,*range(year-3,year-16,-1)]
    if not 1<=len(years)<=24 or len(set(years))!=len(years) or any(not 1962<=v<=year for v in years):
        raise ValueError('invalid_source_years')
    return years


def following_year(year,years):
    return years[(years.index(year)+1)%len(years)]


def _run_unlocked(limit, year=None):
    store.ROOT.mkdir(parents=True,exist_ok=True)
    with (store.ROOT/'.collector.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'already_running'}
        with store.connection() as c:c.execute("UPDATE collection_runs SET state='interrupted',finished=?,error_code='worker_restarted' WHERE source='D&AD Film Awards' AND state='running'",(time.time(),))
        identity=secrets.token_hex(12);found=inserted=0
        with store.connection() as c:c.execute('INSERT INTO collection_runs(id,source,started,state) VALUES(?,?,?,?)',(identity,'D&AD Film Awards',time.time(),'running'))
        failures=[]
        try:
            years=source_years()
            if year is not None:
                if type(year) is not int or not 1962<=year<=datetime.now(timezone.utc).year:raise ValueError('invalid_source_years')
                years=[year]
            with httpx.Client(timeout=35,follow_redirects=False,headers={'User-Agent':'VisualAgent-ReferenceCollector/1.0'}) as client:
                robots=client.get(dandad.ORIGIN+'/robots.txt')
                if robots.status_code not in (200,404):raise ValueError('robots_unavailable')
                policy=RobotFileParser();policy.parse(robots.text.splitlines() if robots.status_code==200 else [])
                if robots.status_code==200 and not policy.can_fetch('VisualAgent-ReferenceCollector',dandad.ORIGIN+'/work/annual'):raise ValueError('robots_disallowed')
                cursor_path=store.ROOT/('collection_cursor.json' if year is None else f'collection_cursor_{year}.json')
                cursor=json.loads(cursor_path.read_text()) if cursor_path.exists() else {'year':years[0],'page':1}
                if cursor['year'] not in years:cursor={'year':years[0],'page':1}
                listing=dandad.ORIGIN+f"/work/d-ad-awards-archive?years={cursor['year']}&categories=film&page={cursor['page']}"
                if robots.status_code==200 and not policy.can_fetch('VisualAgent-ReferenceCollector',listing):raise ValueError('robots_disallowed')
                links,pages=dandad.discover_films(client,cursor['year'],cursor['page']);found=len(links)
                start=cursor.get('offset',0)
                batch=links[start:start+max(1,min(limit,80))]
                with store.connection() as c:c.execute('UPDATE collection_runs SET discovered=? WHERE id=?',(found,identity))
                for url in batch:
                    if robots.status_code==200 and not policy.can_fetch('VisualAgent-ReferenceCollector',url):continue
                    try:
                        record=dandad.fetch(client,url)
                        if record:
                            record['tags']=['Film广告类别',*record.get('tags',[])]
                            iid,new=store.ingest(record);inserted+=int(new)
                            # Source media locator is kept out of trajectories and cloud exports until policy is checked.
                            folder=store.ROOT/'assets'/iid;folder.mkdir(parents=True,exist_ok=True)
                            temporary_source=folder/'source.tmp'
                            temporary_source.write_text(json.dumps({'source_url':url,'media_url':record['media_url']},ensure_ascii=False))
                            temporary_source.replace(folder/'source.json')
                            # A rediscovered locator restores only this specific
                            # failure; preserve attempts and unrelated failures.
                            with store.connection() as c:
                                c.execute("UPDATE media_jobs SET state='pending',error_code='',updated=? WHERE item=? AND error_code='source_locator_missing'",(time.time(),iid))
                    except (httpx.HTTPError,ValueError,KeyError):failures.append('item_fetch_or_parse_failed')
                    with store.connection() as c:c.execute('UPDATE collection_runs SET inserted=? WHERE id=?',(inserted,identity))
                    time.sleep(1)
            attempts=cursor.get('attempts',0)+1 if failures else 0
            if not failures or attempts>=3:
                end=start+len(batch)
                if end<len(links):next_cursor={'year':cursor['year'],'page':cursor['page'],'offset':end}
                else:next_cursor={'year':cursor['year'],'page':cursor['page']+1} if cursor['page']<pages else {'year':following_year(cursor['year'],years),'page':1}
            else:next_cursor={**cursor,'attempts':attempts}
            temporary=cursor_path.with_suffix('.tmp');temporary.write_text(json.dumps(next_cursor));temporary.replace(cursor_path)
            state='partial' if failures else 'completed';error='item_fetch_or_parse_failed' if failures else ''
        except Exception as e:
            state='failed';error=str(e) if isinstance(e,ValueError) and str(e) in ('robots_unavailable','robots_disallowed','source_layout_changed','invalid_source_years') else 'source_unavailable'
        with store.connection() as c:c.execute('UPDATE collection_runs SET finished=?,state=?,discovered=?,inserted=?,error_code=? WHERE id=?',(time.time(),state,found,inserted,error,identity))
        return {'id':identity,'state':state,'discovered':found,'inserted':inserted,'error_code':error}

def run(limit, year=None):
    store.ROOT.mkdir(parents=True, exist_ok=True)
    # Scheduled metadata collection opts into the same overlap policy as the
    # other sources. Backup freezes its own consistent SQLite copy before
    # uploading; the collector lock in _run_unlocked still prevents duplicates.
    if os.getenv('AD_LIBRARY_METADATA_OVERLAP') == '1':
        return _run_unlocked(limit, year)
    # Standalone collection keeps the conservative default when overlap was
    # not explicitly enabled. The lock covers the entire backup operation.
    with (store.ROOT/'.backup.lock').open('a') as backup_lock:
        try:
            fcntl.flock(backup_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'deferred_backup_in_progress'}
        return _run_unlocked(limit, year)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=30);parser.add_argument('--year',type=int,help='Backfill one year using an independent cursor');args=parser.parse_args()
    result=run(args.limit,args.year);print(json.dumps(result));sys.exit(1 if result['state']=='failed' else 0)
