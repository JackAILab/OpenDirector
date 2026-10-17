"""Shared-disk reference records, separate from generation trajectories and accounts."""
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from harness.library.taxonomy import classified_metadata
from harness.library.browse_groups import LABELS as GROUP_LABELS, group_ids, groups_for, options as group_options

ROOT = Path(os.getenv('AD_LIBRARY_ROOT', '/assets/library'))
DIMENSIONS = ('hook', 'message', 'product', 'story', 'craft', 'sound', 'action')
STATES = ('pending', 'selected', 'revisit', 'rejected')
CACHEABLE_ITEM_WHERE = "(COALESCE(json_extract(data,'$.media_status'),'')!='source_link' OR COALESCE(json_extract(data,'$.creative_structure.public_video_url'),'')!='')"

# Schema setup changes the database journal and performs many metadata
# lookups. Repeating it for every ingest on a shared FUSE filesystem can
# block for minutes even though the database itself is healthy. Keep the
# one-time setup scoped by data root; a new process still initializes its
# configured root once, while regular connections only enable foreign keys.
_SCHEMA_ROOTS = set()
_SCHEMA_LOCK = threading.Lock()


def canonical_url(value):
    parts=urlsplit(value)
    if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('需要有效的公开来源链接')
    if parts.port not in (None,80,443):raise ValueError('来源链接端口不受支持')
    # Remove tracking, retain actual identifiers such as a video ID.
    query=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True)
           if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')]
    if any(k.lower() in ('token','signature','x-amz-signature','access_token','key') for k,_ in query):
        raise ValueError('请使用永久公开链接，而非带认证或临时签名的链接')
    return urlunsplit((parts.scheme,parts.netloc.lower(),parts.path or '/',urlencode(sorted(query)),''))


@contextmanager
def connection(*, timeout=30):
    ROOT.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(ROOT/'library.sqlite3',timeout=timeout)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    root_key=os.path.abspath(os.fspath(ROOT))
    if root_key not in _SCHEMA_ROOTS:
        # Keep journal beside the database; no shared-memory WAL assumptions
        # on network disks. Serialize first-use setup within this process.
        with _SCHEMA_LOCK:
            if root_key not in _SCHEMA_ROOTS:
                c.execute('PRAGMA journal_mode=DELETE')
                c.executescript('''
    CREATE TABLE IF NOT EXISTS items(
      id TEXT PRIMARY KEY, source_url TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
      brand TEXT NOT NULL DEFAULT '', industry TEXT NOT NULL DEFAULT '',
      ad_type TEXT NOT NULL DEFAULT '', data TEXT NOT NULL,
      revision INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS item_recent ON items(created DESC,id);
    CREATE INDEX IF NOT EXISTS item_industry ON items(industry);
    CREATE INDEX IF NOT EXISTS item_ad_type ON items(ad_type);
    CREATE INDEX IF NOT EXISTS item_type_recent ON items(ad_type,created DESC,id,industry);
    CREATE TABLE IF NOT EXISTS reviews(
      seq INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL REFERENCES items(id),
      reviewer INTEGER NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL,
      scores TEXT NOT NULL, tags TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL,
      UNIQUE(item,reviewer,version));
    CREATE INDEX IF NOT EXISTS review_lookup ON reviews(item,reviewer,version DESC);
    CREATE TABLE IF NOT EXISTS collection_runs(
      id TEXT PRIMARY KEY, source TEXT NOT NULL, started REAL NOT NULL, finished REAL,
      state TEXT NOT NULL, discovered INTEGER NOT NULL DEFAULT 0,
      inserted INTEGER NOT NULL DEFAULT 0, error_code TEXT NOT NULL DEFAULT '');
    CREATE INDEX IF NOT EXISTS collection_recent ON collection_runs(started DESC);
    CREATE TABLE IF NOT EXISTS media_jobs(item TEXT PRIMARY KEY REFERENCES items(id), state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, error_code TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS media_job_update ON media_jobs(updated,state);
    CREATE TABLE IF NOT EXISTS assets(item TEXT PRIMARY KEY REFERENCES items(id), path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, duration REAL NOT NULL, audio INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS asset_checksum ON assets(sha256,item);
    CREATE INDEX IF NOT EXISTS asset_item_checksum ON assets(item,sha256);
    CREATE TABLE IF NOT EXISTS media_reuses(
      item TEXT PRIMARY KEY REFERENCES items(id), source_item TEXT NOT NULL REFERENCES items(id),
      sha256 TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS backups(
      id TEXT PRIMARY KEY, created REAL NOT NULL, manifest TEXT NOT NULL,
      state TEXT NOT NULL, remote_revision TEXT);
    CREATE INDEX IF NOT EXISTS backup_summary_recent ON backups(created DESC,id,state,remote_revision);
    CREATE INDEX IF NOT EXISTS backup_summary_active ON backups(created DESC,id,state,remote_revision)
      WHERE state IN ('uploading','verifying');
    CREATE INDEX IF NOT EXISTS backup_summary_in_progress ON backups(created DESC,id,state,remote_revision)
      WHERE state IN ('preparing','uploading','verifying');
    ''')
                c.execute('CREATE INDEX IF NOT EXISTS item_cache_candidate ON items(created,id) WHERE '+CACHEABLE_ITEM_WHERE)
                _SCHEMA_ROOTS.add(root_key)
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback();raise
    finally:c.close()


def registered_media_bytes(db):
    """Count registered file paths once, keeping separate physical copies.

    A shared file may serve several source records. Equal hashes at different
    paths still occupy disk independently. Conflicting byte metadata uses the
    larger size; backup content verification remains authoritative.
    """
    return db.execute('''SELECT COALESCE(SUM(bytes),0) FROM
        (SELECT path,MAX(bytes) AS bytes FROM assets GROUP BY path)''').fetchone()[0]


def ingest(record):
    """Collector may update evidence, but can never manufacture a human preference."""
    url=canonical_url(record['source_url'])
    title=str(record.get('title','')).strip()
    if not title or len(title)>300:raise ValueError('标题不能为空，且不能超过300字')
    allowed=('brand','industry','ad_type','format','language','duration','audio','summary',
             'quality_evidence','source_name','published','embed_url','thumbnail_url',
             'media_status','media_role','rights','creative_structure','tags')
    data={k:record[k] for k in allowed if k in record}
    for key in ('embed_url','thumbnail_url'):
        if data.get(key):data[key]=canonical_url(data[key])
    data=classified_metadata(url,data)
    data['training_eligible']=False
    payload=json.dumps(data,ensure_ascii=False,sort_keys=True)
    if len(payload)>32000:raise ValueError('参考记录过大')
    identity=hashlib.sha256(url.encode()).hexdigest()[:24];now=time.time()
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM items WHERE id=?',(identity,)).fetchone()
        if old and old['data']==payload and old['title']==title:return identity,False
        c.execute('''INSERT INTO items(id,source_url,title,brand,industry,ad_type,data,created,updated)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,
          brand=excluded.brand,industry=excluded.industry,ad_type=excluded.ad_type,
          data=excluded.data,revision=items.revision+1,updated=excluded.updated''',
          (identity,url,title,str(data.get('brand',''))[:200],str(data.get('industry',''))[:100],
           str(data.get('ad_type',''))[:100],payload,now,now))
    return identity,not bool(old)


def project(row,review=None,asset=None):
    item={**json.loads(row['data']),**{k:row[k] for k in ('id','title','source_url','brand','industry','ad_type','revision','created','updated')}}
    item['ad_groups']=groups_for(item['ad_type'])
    item['review']={'version':0,'state':'pending','scores':{},'tags':[],'note':''}
    if review:
        item['review']={k:review[k] for k in ('version','state','note','created')}
        item['review'].update(scores=json.loads(review['scores']),tags=json.loads(review['tags']))
    item['training_eligible']=False
    if asset:
        item.update(media_status='local',duration=asset['duration'],audio=bool(asset['audio']),width=asset['width'],height=asset['height'],media_url='/creative/api/library/'+row['id']+'/media',thumbnail_url='/creative/api/library/'+row['id']+'/poster')
    return item


def media_group_sql(identity='i.id'):
    # Only verified file identities can be grouped. Missing/legacy hashes and
    # source-only references retain an independent identity.
    if identity not in ('i.id','a.item'):raise ValueError('invalid_media_identity')
    return ("CASE WHEN length(a.sha256)=64 AND a.sha256 NOT GLOB '*[^0-9a-f]*' "
            "THEN a.sha256 ELSE 'unverified:'||"+identity+" END")


def list_items(reviewer,search='',industry='',ad_type='',state='',limit=100,offset=0,local_only=False,duration_band='',unique_media=False,ad_group=''):
    if ad_group and ad_group not in GROUP_LABELS:raise ValueError('无效的广告类型分组')
    clauses=[];args=[]
    bands={'short':'a.duration>0 AND a.duration<=30','standard':'a.duration>30 AND a.duration<=60','extended':'a.duration>60 AND a.duration<=180','long':'a.duration>180'}
    if duration_band:
        if duration_band=='unknown':clauses.append('NOT EXISTS (SELECT 1 FROM assets a WHERE a.item=i.id AND a.duration>0)')
        elif duration_band in bands:clauses.append('EXISTS (SELECT 1 FROM assets a WHERE a.item=i.id AND '+bands[duration_band]+')')
        else:raise ValueError('无效的片长筛选')
    if local_only:clauses.append('EXISTS (SELECT 1 FROM assets a WHERE a.item=i.id)')
    for column,value in (('industry',industry),('ad_type',ad_type)):
        if value:clauses.append('i.'+column+'=?');args.append(value)
    if search:
        clauses.append('(i.title LIKE ? OR i.brand LIKE ? OR i.data LIKE ?)')
        args.extend(['%'+search[:200]+'%']*3)
    if state:
        if state not in STATES:raise ValueError('无效的筛选状态')
        clauses.append("COALESCE(r.state,'pending')=?");args.append(state)
    # The primary-key scan would fetch `created` from large JSON overflow
    # records on shared storage. Ranking needs only the compact recent index.
    # A type group can use item_ad_type to select a small subset. Forcing the
    # recent index here would read every record's category from shared storage.
    join=(' FROM items i INDEXED BY item_recent' if unique_media and not ad_group else ' FROM items i')+''' LEFT JOIN reviews r ON r.seq=(SELECT seq FROM reviews
      WHERE item=i.id AND reviewer=? ORDER BY version DESC LIMIT 1)'''
    with connection(timeout=3) as c:
        facets={k:[r[0] for r in c.execute('SELECT DISTINCT '+k+' FROM items WHERE '+k+"<>'' ORDER BY "+k)] for k in ('industry','ad_type')}
        # Read small indexed category values, not every item's JSON payload.
        # Keep the legacy exact-category filter and all stored evidence intact.
        categories=[*facets['ad_type'], '']
        facets['ad_groups']=group_options(categories if c.execute("SELECT 1 FROM items WHERE ad_type='' LIMIT 1").fetchone() else facets['ad_type'])
        if ad_group:
            matched=[value for value in categories if ad_group in group_ids(value)]
            clauses.append('i.ad_type IN ('+','.join('?' for _ in matched)+')' if matched else '0')
            args.extend(matched)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        # Preferences affect the count only when the user filters by state.
        # Otherwise keep counting on the item indexes without per-row joins.
        count_join = join if state else ' FROM items i'
        count_args = [reviewer,*args] if state else args
        if unique_media:
            # Apply all user filters before choosing a representative. A newer
            # record outside the chosen industry/preference must not hide a
            # matching older source. Rank only small identifiers, not payloads.
            grouped='''WITH filtered AS (
                SELECT i.id,i.created,r.seq AS review_seq,'''+media_group_sql()+''' AS media_key'''+join+'''
                LEFT JOIN assets a INDEXED BY asset_item_checksum ON a.item=i.id'''+where+'''),
                ranked AS (SELECT *,ROW_NUMBER() OVER (
                    PARTITION BY media_key ORDER BY created DESC,id) AS media_rank FROM filtered) '''
            # Freeze the small page of IDs before joining full source payloads.
            # Joining first makes SQLite read thousands of JSON records merely
            # to sort and discard all but 24, which is slow on shared storage.
            rows=c.execute(grouped+''', page AS (
                SELECT id,created,review_seq,COUNT(*) OVER() AS total_count FROM ranked
                WHERE media_rank=1 ORDER BY created DESC,id LIMIT ? OFFSET ?)
                SELECT i.*,page.review_seq,page.total_count FROM page JOIN items i ON i.id=page.id
                ORDER BY page.created DESC,page.id''',
                [reviewer,*args,max(1,min(limit,200)),max(0,offset)]).fetchall()
            count=rows[0]['total_count'] if rows else c.execute(
                grouped+'SELECT COUNT(*) FROM ranked WHERE media_rank=1',[reviewer,*args]).fetchone()[0]
        else:
            if local_only and not any((search,industry,ad_type,state,duration_band,ad_group)):
                # Assets reference existing items and have one row per item.
                # The default playable view can count this compact index
                # directly instead of probing it once for every source row.
                count=c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
            elif not where:
                # SQLite's unfiltered COUNT(*) uses its b-tree count opcode.
                # COUNT(id) visits every entry; on the shared production disk
                # 8,963 rows took 3.34s versus 0.25s for this exact count.
                count=c.execute('SELECT COUNT(*) FROM items').fetchone()[0]
            else:
                count=c.execute('SELECT COUNT(i.id)'+count_join+where,count_args).fetchone()[0]
            page_args=[reviewer,*args,max(1,min(limit,200)),max(0,offset)]
            if ad_group:
                # Sorting several award categories must not load their full
                # evidence JSON before the page of identifiers is selected.
                rows=c.execute('''WITH page AS (
                    SELECT i.id,i.created,r.seq AS review_seq'''+join+where+'''
                    ORDER BY i.created DESC,i.id LIMIT ? OFFSET ?)
                    SELECT i.*,page.review_seq FROM page JOIN items i ON i.id=page.id
                    ORDER BY page.created DESC,page.id''',page_args).fetchall()
            else:
                rows=c.execute('SELECT i.*,r.seq AS review_seq'+join+where+' ORDER BY i.created DESC,i.id LIMIT ? OFFSET ?',page_args).fetchall()
        result=[project(row,c.execute('SELECT * FROM reviews WHERE seq=?',(row['review_seq'],)).fetchone() if row['review_seq'] else None,c.execute('SELECT * FROM assets WHERE item=?',(row['id'],)).fetchone()) for row in rows]
    return {'items':result,'total':count,'facets':facets}


def same_video_sources(identity,reviewer,limit=20):
    """Related source records based only on equal checked file bytes.

    Keep all preference histories separate. Never infer equality from a
    matching title/brand or expose another viewer's labels and notes.
    """
    with connection() as c:
        if not c.execute('SELECT 1 FROM items WHERE id=?',(identity,)).fetchone():raise KeyError(identity)
        asset=c.execute('SELECT sha256 FROM assets WHERE item=?',(identity,)).fetchone()
        if not asset or not re.fullmatch(r'[0-9a-f]{64}',asset['sha256'] or ''):
            return {'total':0,'items':[]}
        total=c.execute('SELECT COUNT(*) FROM assets WHERE sha256=?',(asset['sha256'],)).fetchone()[0]
        rows=c.execute('''SELECT i.id,i.title,i.source_url,i.data,
            COALESCE((SELECT state FROM reviews WHERE item=i.id AND reviewer=?
                ORDER BY version DESC LIMIT 1),'pending') AS review_state
            FROM assets a JOIN items i ON i.id=a.item WHERE a.sha256=?
            ORDER BY i.created DESC,i.id LIMIT ?''',(reviewer,asset['sha256'],max(1,min(limit,20)))).fetchall()
        items=[]
        for row in rows:
            data=json.loads(row['data'])
            items.append({**{key:row[key] for key in ('id','title','source_url','review_state')},
                          'source_name':data.get('source_name','来源待确认')})
        return {'total':total,'items':items}


def get_item(identity,reviewer):
    with connection() as c:
        row=c.execute('SELECT * FROM items WHERE id=?',(identity,)).fetchone()
        if not row:raise KeyError(identity)
        review=c.execute('SELECT * FROM reviews WHERE item=? AND reviewer=? ORDER BY version DESC LIMIT 1',(identity,reviewer)).fetchone()
        return project(row,review,c.execute('SELECT * FROM assets WHERE item=?',(identity,)).fetchone())


def review_history(identity,reviewer):
    with connection() as c:
        if not c.execute('SELECT 1 FROM items WHERE id=?',(identity,)).fetchone():raise KeyError(identity)
        return [{**{k:r[k] for k in ('version','state','note','created')},
                 'scores':json.loads(r['scores']),'tags':json.loads(r['tags'])}
                for r in c.execute('SELECT * FROM reviews WHERE item=? AND reviewer=? ORDER BY version DESC LIMIT 100',(identity,reviewer))]


def review_item(identity,reviewer,version,state,scores,tags,note):
    if state not in STATES:raise ValueError('无效的标注状态')
    if not isinstance(scores,dict) or any(k not in DIMENSIONS or type(v) is not int or not 1<=v<=5 for k,v in scores.items()):raise ValueError('评分应为1至5分')
    if not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or not 1<=len(t)<=50 for t in tags):raise ValueError('标签不合法')
    if not isinstance(note,str) or len(note)>3000:raise ValueError('标注说明过长')
    with connection(timeout=3) as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM items WHERE id=?',(identity,)).fetchone():raise KeyError(identity)
        current=c.execute('SELECT MAX(version) FROM reviews WHERE item=? AND reviewer=?',(identity,reviewer)).fetchone()[0] or 0
        if current!=version:raise RuntimeError('标注已在其他窗口更新，请刷新后再保存')
        c.execute('INSERT INTO reviews(item,reviewer,version,state,scores,tags,note,created) VALUES(?,?,?,?,?,?,?,?)',
                  (identity,reviewer,current+1,state,json.dumps(scores),json.dumps(tags,ensure_ascii=False),note,time.time()))
        # Build the response inside the same transaction. A failed commit
        # rolls back the annotation; a successful commit cannot be followed
        # by a second, contended read falsely reporting that saving failed.
        row=c.execute('SELECT * FROM items WHERE id=?',(identity,)).fetchone()
        review=c.execute('SELECT * FROM reviews WHERE item=? AND reviewer=? AND version=?',
                         (identity,reviewer,current+1)).fetchone()
        asset=c.execute('SELECT * FROM assets WHERE item=?',(identity,)).fetchone()
        return project(row,review,asset)
